from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import logging
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------
# 🧩 CLIENT REFERENCE BUILDER
# ------------------------

def build_client_reference(
    mongo_client: MongoClient,
    db_name: str,
    test_id: str,
    run_id: str,
    iteration_index: int,
    models: Dict[str, str],
    input_text,
    max_iteration: int,
    operation: str = "process",
) -> Dict[str, Any]:
    """
    Build a client reference document for the orchestrator/worker chain.
    Contains all contextual information required for state transitions.
    """

    db = mongo_client[db_name]
    runs_collection = db["runs"]

    run_doc = runs_collection.find_one({"test_id": test_id})
    if not run_doc:
        raise ValueError(f"No document found with test_id={test_id}")

    # Locate the run object (combi)
    run_data = next(
        (r for r in run_doc.get("runs", []) if r.get("run") == run_id),
        None
    )
    if not run_data:
        raise ValueError(f"No run found with run_id={run_id}")

    # Attempt to extract existing iteration metadata if available
    previous_iteration = None
    iterations = run_data.get("iterations", [])
    if iteration_index > 0 and iteration_index <= len(iterations):
        previous_iteration = run_data["iterations"][iteration_index - 1]

    # ✅ Unified structure aligned with your StateMachine logic
    client_reference = {
        # --- Core identifiers ---
        "test_id": test_id,
        "run_id": run_id,
        "iteration": iteration_index,
        "max_iteration": max_iteration,
        "qid": f"{test_id}_{run_id}_{iteration_index}",

        # --- State machine ---
        "operation": operation,
        "status": "queued",
        "timestamp": datetime.now().isoformat(),

        # --- Model configuration ---
        "models": {
            "core_model": models.get("core_model"),
            "assessment_model": models.get("assessment_model"),
            "meta_model": models.get("meta_model"),
        },

        # --- Source metadata ---
        "collection": "runs",
        "db_id": str(run_doc["_id"]),
        "input_path": previous_iteration.get("input_path") if previous_iteration else None,

        # --- Links between iterations ---
        "previous_qid": (
            f"{test_id}_{run_id}_{iteration_index - 1}"
            if iteration_index > 0 else None
        ),
        "previous_prompt": (
            previous_iteration.get("last_input_prompt")
            if previous_iteration else None
        ),

        # --- Results placeholders ---
        "placeholders": {
            "previous_input_prompt": (
                previous_iteration.get("last_input_prompt")
                if previous_iteration else None
            ),
            "improved_input_prompt": None,
            "input_text": input_text,
            "output_json": None,
            "output_rendered": None,
            "assessment": None,
            "AVG_total_score": None,
            "new_metaprompt": None
        }
    }

    return client_reference


# ------------------------
# 📬 WRITE JOB TO QUEUE
# ------------------------

def write_queue(
    mongo_client: MongoClient,
    queue_id: str,
    data: Dict[str, Any],
    client_reference: Dict[str, Any],
    prompts_array: Optional[list],
    operation: str,
    model: str,
    temperature: float = 1.0,
    priority: int = 1,
) -> Dict[str, Any]:
    """
    Insert a job into the jobs collection for LLM workers.
    Each job is self-contained (contains prompts, model, requestData, and clientReference).
    """

    db = mongo_client["poc-llm-processor"]
    collection = db["jobs"]

    queue_object = {
        "_id": ObjectId(),
        "id": queue_id,
        "status": "PENDING",
        "operation": operation,
        "model": model,
        "temperature": temperature,
        "priority": priority,
        "requestData": data,
        "prompts": prompts_array or [],
        "clientReference": client_reference,
        "created_at": datetime.now().isoformat(),
    }

    # Upsert instead of insert to avoid duplicates
    result = collection.update_one({"_id": queue_id}, {"$set": queue_object}, upsert=True)

    if result.upserted_id or result.modified_count:
        logger.info(f"📬 Job queued successfully (id={queue_id}, op={operation})")
    else:
        logger.warning(f"⚠️ Queue write had no effect for id={queue_id}")

    return queue_object

def queue_has_items(mongo_client: MongoClient, db_name: str, collection_name: str = "jobs") -> bool:
    """
    Checks whether there are still pending items in a given queue.
    """
    collection = mongo_client[db_name][collection_name]
    count = collection.count_documents({"status": "PENDING"})
    logger.debug(f"🕓 Pending items in {collection_name}: {count}")
    print(f"total pending items in queue: {count}")
    return count > 0
