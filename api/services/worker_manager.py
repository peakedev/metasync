"""
Worker Manager - Singleton managing worker threads and lifecycle
"""
import threading
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from config import config
from utilities.cosmos_connector import get_mongo_client
from api.services.worker_service import get_worker_service
from api.models.worker_models import WorkerStatus
from api.core.logging import get_logger

logger = get_logger("api.services.worker_manager")


class WorkerManager:
    """Singleton managing worker threads and lifecycle"""
    
    _instance: Optional['WorkerManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.worker_service = get_worker_service()
        self.worker_threads: Dict[str, threading.Thread] = {}
        self.worker_stop_events: Dict[str, threading.Event] = {}
        self.worker_instances: Dict[str, Any] = {}  # Store QueueWorker instances
        self.manager_lock = threading.Lock()
        self._initialized = True
        
        logger.info("WorkerManager initialized")
    
    def load_workers_from_db(self):
        """
        Load all workers from database and set them to stopped state.
        This is called on startup.
        """
        with self.manager_lock:
            try:
                # Load all workers from database
                workers = self.worker_service.list_workers(is_admin=True)
                
                # Set all to stopped state (in case any were running when server restarted)
                for worker in workers:
                    worker_id = worker["worker_id"]
                    current_status = worker.get("status")
                    
                    if current_status == WorkerStatus.RUNNING.value:
                        logger.info(f"Setting worker {worker_id} to stopped state (server restart)", worker_id=worker_id)
                        try:
                            self.worker_service.update_worker(
                                worker_id=worker_id,
                                status=WorkerStatus.STOPPED,
                                thread_info=None,
                                is_admin=True
                            )
                        except Exception as e:
                            logger.error(f"Error setting worker {worker_id} to stopped", error=str(e), worker_id=worker_id)
                
                logger.info(f"Loaded {len(workers)} workers from database (all set to stopped)", count=len(workers))
            except Exception as e:
                logger.error("Error loading workers from database", error=str(e))
    
    def start_worker(self, worker_id: str) -> bool:
        """
        Start a worker thread.
        
        Args:
            worker_id: Worker document ID
            
        Returns:
            True if worker started successfully, False otherwise
        """
        with self.manager_lock:
            # Check if worker is already running
            if worker_id in self.worker_threads:
                thread = self.worker_threads[worker_id]
                if thread.is_alive():
                    logger.warning(f"Worker {worker_id} is already running", worker_id=worker_id)
                    return False
            
            try:
                # Get worker from database
                worker = self.worker_service.get_worker_by_id(worker_id, is_admin=True)
                
                # Check if worker is already running in DB
                if worker.get("status") == WorkerStatus.RUNNING.value:
                    logger.warning(f"Worker {worker_id} is already marked as running in DB", worker_id=worker_id)
                    return False
                
                # Import QueueWorker here to avoid circular imports
                import sys
                from pathlib import Path
                project_root = Path(__file__).resolve().parent.parent.parent
                # Add both utilities and llm-workers to path for QueueWorker imports
                if str(project_root / "utilities") not in sys.path:
                    sys.path.insert(0, str(project_root / "utilities"))
                if str(project_root) not in sys.path:
                    sys.path.insert(0, str(project_root))
                if str(project_root / "llm-workers") not in sys.path:
                    sys.path.insert(0, str(project_root / "llm-workers"))
                from llm_queue_worker import QueueWorker
                
                # Get worker configuration
                worker_config = worker["config"]
                client_id = worker["clientId"]
                worker_identifier = worker["workerId"]
                
                # Create stop event
                stop_event = threading.Event()
                self.worker_stop_events[worker_id] = stop_event
                
                # Create QueueWorker instance
                queue_worker = QueueWorker(
                    worker_id=f"{worker_identifier}-{worker_id[:8]}",
                    client_id=client_id,
                    connection_string=config.db_connection_string,
                    db_name=config.db_name,
                    poll_interval=worker_config["pollInterval"],
                    max_items_per_batch=worker_config["maxItemsPerBatch"],
                    log_level="INFO",
                    model_filter=worker_config.get("modelFilter"),
                    operation_filter=worker_config.get("operationFilter"),
                    client_reference_filters=worker_config.get("clientReferenceFilters"),
                    stop_event=stop_event
                )
                
                self.worker_instances[worker_id] = queue_worker
                
                # Create and start thread
                thread = threading.Thread(
                    target=self._run_worker_thread,
                    args=(worker_id, queue_worker),
                    daemon=True,
                    name=f"Worker-{worker_identifier}"
                )
                
                self.worker_threads[worker_id] = thread
                
                # Update worker status in DB
                self.worker_service.update_worker(
                    worker_id=worker_id,
                    status=WorkerStatus.RUNNING,
                    thread_info={
                        "threadId": thread.ident,
                        "startedAt": datetime.now().isoformat()
                    },
                    is_admin=True
                )
                
                # Start the thread
                thread.start()
                
                logger.info(f"Worker {worker_id} started successfully", worker_id=worker_id, worker_identifier=worker_identifier)
                return True
                
            except Exception as e:
                import traceback
                error_traceback = traceback.format_exc()
                logger.error(f"Error starting worker {worker_id}", error=str(e), worker_id=worker_id, traceback=error_traceback)
                # Set status to error
                try:
                    self.worker_service.update_worker(
                        worker_id=worker_id,
                        status=WorkerStatus.ERROR,
                        thread_info=None,
                        is_admin=True
                    )
                except:
                    pass
                # Re-raise to get more details in the API response
                raise
    
    def stop_worker(self, worker_id: str) -> bool:
        """
        Stop a worker thread.
        
        Args:
            worker_id: Worker document ID
            
        Returns:
            True if worker stopped successfully, False otherwise
        """
        with self.manager_lock:
            # Check if worker is running
            if worker_id not in self.worker_threads:
                logger.warning(f"Worker {worker_id} is not running", worker_id=worker_id)
                # Update DB status if it's marked as running
                try:
                    worker = self.worker_service.get_worker_by_id(worker_id, is_admin=True)
                    if worker.get("status") == WorkerStatus.RUNNING.value:
                        self.worker_service.update_worker(
                            worker_id=worker_id,
                            status=WorkerStatus.STOPPED,
                            thread_info=None,
                            is_admin=True
                        )
                except:
                    pass
                return False
            
            try:
                # Signal worker to stop
                if worker_id in self.worker_stop_events:
                    stop_event = self.worker_stop_events[worker_id]
                    stop_event.set()
                
                # Wait for thread to finish (with timeout)
                thread = self.worker_threads[worker_id]
                thread.join(timeout=10)
                
                # Clean up
                if worker_id in self.worker_threads:
                    del self.worker_threads[worker_id]
                if worker_id in self.worker_stop_events:
                    del self.worker_stop_events[worker_id]
                if worker_id in self.worker_instances:
                    del self.worker_instances[worker_id]
                
                # Update worker status in DB
                self.worker_service.update_worker(
                    worker_id=worker_id,
                    status=WorkerStatus.STOPPED,
                    thread_info=None,
                    is_admin=True
                )
                
                logger.info(f"Worker {worker_id} stopped successfully", worker_id=worker_id)
                return True
                
            except Exception as e:
                logger.error(f"Error stopping worker {worker_id}", error=str(e), worker_id=worker_id)
                return False
    
    def _run_worker_thread(self, worker_id: str, queue_worker: Any):
        """
        Run the worker in a thread. Handles errors and updates status.
        
        Args:
            worker_id: Worker document ID
            queue_worker: QueueWorker instance
        """
        try:
            queue_worker.run_worker()
        except Exception as e:
            logger.error(f"Worker {worker_id} crashed", error=str(e), worker_id=worker_id)
            # Update status to error
            try:
                self.worker_service.update_worker(
                    worker_id=worker_id,
                    status=WorkerStatus.ERROR,
                    thread_info=None,
                    is_admin=True
                )
            except:
                pass
        finally:
            # Clean up
            with self.manager_lock:
                if worker_id in self.worker_threads:
                    del self.worker_threads[worker_id]
                if worker_id in self.worker_stop_events:
                    del self.worker_stop_events[worker_id]
                if worker_id in self.worker_instances:
                    del self.worker_instances[worker_id]
    
    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a worker (including thread status).
        
        Args:
            worker_id: Worker document ID
            
        Returns:
            Worker status dictionary or None if not found
        """
        with self.manager_lock:
            try:
                worker = self.worker_service.get_worker_by_id(worker_id, is_admin=True)
                
                # Check if thread is actually running
                thread_running = False
                if worker_id in self.worker_threads:
                    thread = self.worker_threads[worker_id]
                    thread_running = thread.is_alive()
                
                # If DB says running but thread is not, update DB
                if worker.get("status") == WorkerStatus.RUNNING.value and not thread_running:
                    logger.warning(f"Worker {worker_id} marked as running in DB but thread is not alive", worker_id=worker_id)
                    self.worker_service.update_worker(
                        worker_id=worker_id,
                        status=WorkerStatus.STOPPED,
                        thread_info=None,
                        is_admin=True
                    )
                    worker = self.worker_service.get_worker_by_id(worker_id, is_admin=True)
                
                return worker
            except Exception as e:
                logger.error(f"Error getting worker status {worker_id}", error=str(e), worker_id=worker_id)
                return None
    
    def list_workers(self) -> List[Dict[str, Any]]:
        """
        List all workers with their current status.
        
        Returns:
            List of worker dictionaries
        """
        with self.manager_lock:
            workers = self.worker_service.list_workers(is_admin=True)
            
            # Update status for each worker based on actual thread status
            for worker in workers:
                worker_id = worker["worker_id"]
                if worker_id in self.worker_threads:
                    thread = self.worker_threads[worker_id]
                    if thread.is_alive() and worker.get("status") != WorkerStatus.RUNNING.value:
                        # Thread is running but DB says otherwise - update DB
                        self.worker_service.update_worker(
                            worker_id=worker_id,
                            status=WorkerStatus.RUNNING,
                            is_admin=True
                        )
                        worker = self.worker_service.get_worker_by_id(worker_id, is_admin=True)
                    elif not thread.is_alive() and worker.get("status") == WorkerStatus.RUNNING.value:
                        # Thread is not running but DB says running - update DB
                        self.worker_service.update_worker(
                            worker_id=worker_id,
                            status=WorkerStatus.STOPPED,
                            thread_info=None,
                            is_admin=True
                        )
                        worker = self.worker_service.get_worker_by_id(worker_id, is_admin=True)
            
            return workers
    
    def stop_all_workers(self):
        """Stop all running workers. Called on shutdown."""
        with self.manager_lock:
            worker_ids = list(self.worker_threads.keys())
            logger.info(f"Stopping {len(worker_ids)} workers", count=len(worker_ids))
            
            # First, signal all workers to stop
            for worker_id in worker_ids:
                try:
                    if worker_id in self.worker_stop_events:
                        stop_event = self.worker_stop_events[worker_id]
                        stop_event.set()
                        logger.info(f"Stop signal sent to worker {worker_id}", worker_id=worker_id)
                except Exception as e:
                    logger.error(f"Error signaling worker {worker_id} to stop", error=str(e), worker_id=worker_id)
            
            # Then wait for threads to finish (with shorter timeout per worker)
            for worker_id in worker_ids:
                try:
                    if worker_id in self.worker_threads:
                        thread = self.worker_threads[worker_id]
                        thread.join(timeout=5)  # Reduced timeout per worker
                        
                        if thread.is_alive():
                            logger.warning(f"Worker {worker_id} thread did not stop within timeout", worker_id=worker_id)
                        else:
                            logger.info(f"Worker {worker_id} thread stopped", worker_id=worker_id)
                except Exception as e:
                    logger.error(f"Error waiting for worker {worker_id} thread", error=str(e), worker_id=worker_id)
            
            # Clean up all worker resources
            for worker_id in worker_ids:
                try:
                    if worker_id in self.worker_threads:
                        del self.worker_threads[worker_id]
                    if worker_id in self.worker_stop_events:
                        del self.worker_stop_events[worker_id]
                    if worker_id in self.worker_instances:
                        del self.worker_instances[worker_id]
                    
                    # Update worker status in DB
                    try:
                        self.worker_service.update_worker(
                            worker_id=worker_id,
                            status=WorkerStatus.STOPPED,
                            thread_info=None,
                            is_admin=True
                        )
                    except:
                        pass  # Ignore DB errors during shutdown
                except Exception as e:
                    logger.error(f"Error cleaning up worker {worker_id}", error=str(e), worker_id=worker_id)
            
            logger.info("All workers stopped")


# Singleton instance getter
def get_worker_manager() -> WorkerManager:
    """Get the singleton WorkerManager instance"""
    return WorkerManager()

