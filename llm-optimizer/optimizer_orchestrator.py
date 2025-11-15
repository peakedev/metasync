#!/usr/bin/env python3
import argparse
import logging
import os
import keyring
import time
import threading
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.init_runner import init_run_db
from workflows.combi_runner import batch_loop
from utilities.cosmos_connector import get_mongo_client, db_read, db_find_one, clear_collection


from workflows.operations_handler import process_operation
from opti_outqueue_handler import read_output_queue_operations
from opti_inqueue_handler import queue_has_items

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Project root detection (utilisé pour trouver les scripts workers)
project_root = Path(__file__).resolve().parent.parent

# -----------------------------
# Dataclasses pour config
# -----------------------------
@dataclass
class ModelConfig:
    model1: str
    model2: str
    model3: str
    model4: str

@dataclass
class RunConfig:
    test_id: str
    models: ModelConfig
    iterations: int = 2
    temperature: float = 1.0
    num_llm_workers: int = 2  # default number of parallel LLM workers

# -----------------------------
# Utilitaires
# -----------------------------
def clear_queue(mongo_client, db_name: str, collection_name: str):
    """Supprime tous les documents de la collection fournie (utilise clear_collection)."""
    logger.info(f"Clearing queue: {collection_name}")
    result = clear_collection(mongo_client, db_name, collection_name)
    if result.get("success"):
        logger.info(f"Cleared {collection_name}: deleted {result.get('deleted_count')}")
        return True
    else:
        logger.error(f"Failed to clear {collection_name}: {result.get('error')}")
        return False

# -----------------------------
# LLM worker launcher (external script)
# -----------------------------
def run_single_llm_worker(worker_id: int, results: list):

    try:
        # Get the path to the LLM worker
        llm_worker_path = project_root / "llm-workers" / "llm_queue_worker.py"

        if not llm_worker_path.exists():
            print(f"❌ Worker {worker_id}: LLM worker not found at: {llm_worker_path}")
            results[worker_id] = {"success": False, "error": "Worker not found"}
            return

        print(f"🚀 Worker {worker_id}: Starting LLM worker")

        # Run the LLM worker with exit_when_empty flag
        result = subprocess.run([
            sys.executable,
            str(llm_worker_path),
            "--exit-when-empty",
            "--log-level", "INFO",
            "--worker-id", str(worker_id)
        ], capture_output=False, text=True)

        if result.returncode == 0:
            print(f"✅ Worker {worker_id}: Completed successfully")
            results[worker_id] = {"success": True, "output": result.stdout}
        else:
            print(f"❌ Worker {worker_id}: Failed with exit code {result.returncode}")
            results[worker_id] = {"success": False, "error": result.stderr, "exit_code": result.returncode}

    except Exception as e:
        print(f"❌ Worker {worker_id}: Error running LLM worker: {e}")
        results[worker_id] = {"success": False, "error": str(e)}


def run_llm_workers(config: RunConfig):

    print(f"\n{'='*40}")
    print(f"🤖 RUNNING {config.num_llm_workers} LLM QUEUE WORKERS IN PARALLEL")
    print(f"{'='*40}")

    try:
        # Get the path to the LLM worker
        llm_worker_path = project_root / "llm-workers" / "llm_queue_worker.py"

        if not llm_worker_path.exists():
            print(f"❌ LLM worker not found at: {llm_worker_path}")
            return False

        print(f"🚀 Starting {config.num_llm_workers} parallel LLM workers")
        print(f"   Worker script: {llm_worker_path}")
        print(f"   Each worker will process items until the queue is empty")

        # Create results list to store worker outcomes
        results = [None] * config.num_llm_workers

        # Create and start worker threads
        threads = []
        for i in range(config.num_llm_workers):
            thread = threading.Thread(target=run_single_llm_worker, args=(i, results))
            threads.append(thread)
            thread.start()
            time.sleep(0.5)  # Small delay between starting workers

        # Wait for all workers to complete
        print(f"⏳ Waiting for all {config.num_llm_workers} workers to complete...")
        for thread in threads:
            thread.join()

        # Check results
        successful_workers = 0
        failed_workers = 0

        for i, result in enumerate(results):
            if result and result.get("success"):
                successful_workers += 1
            else:
                failed_workers += 1
                if result and "error" in result:
                    print(f"❌ Worker {i} failed: {result['error']}")

        print(f"\n📊 Worker Results:")
        print(f"   ✅ Successful workers: {successful_workers}")
        print(f"   ❌ Failed workers: {failed_workers}")

        # Consider it successful if at least one worker completed successfully
        if successful_workers > 0:
            print(f"✅ LLM processing completed successfully ({successful_workers}/{config.num_llm_workers} workers)")
            return True
        else:
            print(f"❌ All LLM workers failed")
            return False

    except Exception as e:
        print(f"❌ Error running LLM workers: {e}")
        return False

# -----------------------------
# Orchestrator core: Processor
# -----------------------------
class Processor:
    def __init__(self, connection_string: str, db_name: str):
        self.db_name = db_name
        self.mongo_client = get_mongo_client(connection_string)
        self.db = self.mongo_client[self.db_name]
        self.files = self._load_files()

    def _load_files(self) -> Dict:
        """Charge ressources (input text, annexes, config) depuis la DB."""
        try:
            return {
                "text": db_find_one(self.mongo_client, self.db_name, "input", {"id": "test_main_opti"}, {"_id": 0, "id": 0}),
                "configs": db_read(self.mongo_client, self.db_name, "config")
            }
        except Exception as e:
            logger.exception("Failed to load files from DB")
            raise

    def validate_config(self, config: RunConfig) -> bool:
        """Valide que test_id existe en config et que les modèles correspondent exactement."""
        try:
            db_config = next((c for c in self.files["configs"] if c.get("test_id") == config.test_id), None)
            if not db_config:
                logger.error(f"Test ID '{config.test_id}' not found in config collection")
                return False

            config_models = db_config.get("models", {})
            expected = {
                "model1": config.models.model1,
                "model2": config.models.model2,
                "model3": config.models.model3,
                "model4": config.models.model4
            }
            for k, v in expected.items():
                if config_models.get(k) != v:
                    logger.error(f"Model mismatch for {k}. db: {config_models.get(k)} expected: {v}")
                    return False
            return True
        except Exception:
            logger.exception("Configuration validation failed")
            return False

    def run_initialization(self, config: RunConfig):
        """Initialise le run et lance batch_loop pour créer les iterations initiales."""
        if not self.validate_config(config):
            raise RuntimeError("Invalid configuration")

        db_config = db_find_one(self.mongo_client, self.db_name, "config", {"test_id": config.test_id}, {"_id": 0})
        test_id = init_run_db(self.mongo_client, self.db_name, db_config)
        logger.info(f"Initialized run with test_id: {test_id}")
        # Prepare input text structure
        input_text = self.files["text"]

        batch_loop(
            mongo_client=self.mongo_client,
            db_name=self.db_name,
            test_id=test_id,
            model1=config.models.model1,
            model2=config.models.model2,
            model3=config.models.model3,
            model4=config.models.model4,
            input_text=input_text,
            iterations=config.iterations,
            temperature=config.temperature
        )

        return test_id
# -----------------------------
# Main Orchestrator Logic
# -----------------------------
def llm_worker_loop(config, processor, stop_event):
    """
    Main loop for running LLM workers.
    Continuously checks the input queue and processes items until idle or stop_event is set.
    """
    idle_rounds = 0
    max_idle_rounds_before_exit = 4

    while not stop_event.is_set():
        has_items = queue_has_items(processor.mongo_client, "poc-llm-processor", "jobs")

        if has_items:
            idle_rounds = 0
            ok_workers = run_llm_workers(config)
            if not ok_workers:
                logger.warning("No LLM worker succeeded; continuing to next cycle")
        else:
            idle_rounds += 1
            logger.info(f"No items in jobs collection (idle round {idle_rounds}/{max_idle_rounds_before_exit})")
            if idle_rounds >= max_idle_rounds_before_exit:
                logger.info("No activity for several cycles — stopping LLM worker loop.")
                stop_event.set()
                break
            time.sleep(5)

    logger.info("LLM worker loop terminated.")


def output_reader_loop(processor, stop_event):
    """
    Parallel loop that continuously reads and processes operations from the output queue.
    Starts 2 minutes after the orchestrator launches.
    Runs until stop_event is set.
    """
    logger.info("Output reader waiting 30 seconds before starting...")
    time.sleep(60)  # Wait before reading output
    logger.info("Output reader started.")

    while not stop_event.is_set():
        try:
            operations = read_output_queue_operations(processor.mongo_client)
            if operations:
                logger.info(f"Processing {len(operations)} operations from jobs collection")
                for operation in operations:
                    process_operation(operation, processor.mongo_client)
            else:
                logger.debug("No processed items in jobs collection")

            time.sleep(30)  # Wait before next check
        except Exception as e:
            logger.exception(f"Error in output_reader_loop: {e}")
            time.sleep(5)

    logger.info("Output reader loop terminated.")


def main():
    parser = argparse.ArgumentParser(description="Processing Orchestrator")
    parser.add_argument("--test_id", required=True)
    parser.add_argument("--model1", required=True)
    parser.add_argument("--model2", required=True)
    parser.add_argument("--model3", required=True)
    parser.add_argument("--model4", required=True)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--num-workers", type=int, default=2)
    args = parser.parse_args()

    # ===== Load MongoDB connection string =====
    connection_string = os.getenv("MONGODB_CONNECTION_STRING") or keyring.get_password("mongodb", "client-app")
    if not connection_string:
        logger.error("MongoDB connection string not found (env or keyring)")
        sys.exit(1)

    db_name = os.getenv("TARGET_HOST", "client-poc")
    processor = Processor(connection_string, db_name)

    # Clear jobs collection
    clear_queue(processor.mongo_client, "poc-llm-processor", "jobs")

    # ===== Initialize configuration =====
    config = RunConfig(
        test_id=args.test_id,
        models=ModelConfig(
            model1=args.model1,
            model2=args.model2,
            model3=args.model3,
            model4=args.model4
        ),
        iterations=args.iterations,
        temperature=args.temperature,
        num_llm_workers=args.num_workers
    )

    # Initialize run and create first batch of iterations
    processor.run_initialization(config)

    # ===== Events for graceful shutdown =====
    stop_event = threading.Event()

    # Create and start threads
    llm_thread = threading.Thread(
        target=llm_worker_loop,
        args=(config, processor, stop_event),
        daemon=True,
        name="LLM-Worker-Loop"
    )
    output_thread = threading.Thread(
        target=output_reader_loop,
        args=(processor, stop_event),
        daemon=True,
        name="Output-Reader-Loop"
    )

    # Start both threads
    llm_thread.start()
    output_thread.start()

    try:
        # Wait until LLM thread finishes or user interrupts
        while llm_thread.is_alive():
            llm_thread.join(timeout=1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected — stopping orchestrator.")
        stop_event.set()
    except Exception:
        logger.exception("Unhandled exception in orchestrator.")
        stop_event.set()
    finally:
        # Ensure both threads stop cleanly
        stop_event.set()
        llm_thread.join(timeout=5)
        output_thread.join(timeout=5)
        logger.info("Orchestrator shut down gracefully.")


if __name__ == "__main__":
    main()
