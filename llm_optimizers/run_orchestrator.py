"""
Run Orchestrator - Background service that monitors jobs and advances runs
"""
import threading
import time
from typing import Optional, Dict, Any

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_read,
    db_update,
    get_document_by_id
)
from api.core.logging import get_logger
from api.models.run_models import RunStatus
from api.models.job_models import JobStatus
from api.services.run_service import get_run_service

logger = get_logger("llm_optimizers.run_orchestrator")


class RunOrchestrator:
    """Background service that orchestrates runs by monitoring jobs"""
    
    def __init__(self, poll_interval: int = 5):
        """
        Initialize the run orchestrator.
        
        Args:
            poll_interval: Polling interval in seconds for checking runs
        """
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.poll_interval = poll_interval
        self._cached_client = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(
            self._connection_string,
            self._cached_client
        )
        return self._cached_client
    
    def start(self):
        """Start the orchestrator in a background thread."""
        if self._is_running:
            logger.warning("Orchestrator already running")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_runs, daemon=True)
        self._thread.start()
        self._is_running = True
        logger.info("Run orchestrator started", poll_interval=self.poll_interval)
    
    def stop(self):
        """Stop the orchestrator gracefully."""
        if not self._is_running:
            return
        
        logger.info("Stopping run orchestrator...")
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=10.0)  # Wait up to 10 seconds
        
        self._is_running = False
        logger.info("Run orchestrator stopped")
    
    def _poll_runs(self):
        """Main polling loop - checks RUNNING runs and processes completed jobs."""
        logger.info("Run orchestrator polling started")
        
        while not self._stop_event.is_set():
            try:
                # Find all RUNNING runs
                query = {"status": RunStatus.RUNNING.value}
                runs = db_read(
                    self.mongo_client,
                    self.db_name,
                    "runs",
                    query=query
                )
                
                if runs:
                    logger.debug(f"Found {len(runs)} RUNNING runs to check")
                
                for run in runs:
                    if self._stop_event.is_set():
                        break
                    
                    try:
                        self._process_run(run)
                    except Exception as e:
                        run_id = str(run.get("_id"))
                        logger.error(
                            "Error processing run",
                            run_id=run_id,
                            error=str(e)
                        )
                
                # Sleep until next poll
                if not self._stop_event.wait(timeout=self.poll_interval):
                    continue  # Timeout, continue loop
                else:
                    break  # Stop event was set
            
            except Exception as e:
                logger.error("Error in orchestrator poll loop", error=str(e))
                # Sleep briefly before retrying
                if self._stop_event.wait(timeout=1.0):
                    break
        
        logger.info("Run orchestrator polling stopped")
    
    def _process_run(self, run: Dict[str, Any]):
        """
        Process a single RUNNING run - check job status and advance if complete.
        
        Args:
            run: Run document
        """
        run_id = str(run["_id"])
        current_job_id = run.get("currentJobId")
        
        if not current_job_id:
            # No current job - this shouldn't happen for RUNNING runs
            logger.warning("RUNNING run has no currentJobId", run_id=run_id)
            return
        
        # Check job status
        try:
            job = get_document_by_id(
                self.mongo_client,
                self.db_name,
                "jobs",
                current_job_id
            )
            
            if not job:
                logger.error("Current job not found", run_id=run_id, job_id=current_job_id)
                # Mark run as failed
                self._mark_run_failed(run_id, f"Job not found: {current_job_id}")
                return
            
            job_status = job.get("status")
            
            if job_status == JobStatus.PROCESSED.value:
                # Job completed successfully - record iteration and advance
                logger.info(
                    "Job completed for run",
                    run_id=run_id,
                    job_id=current_job_id
                )
                self._process_completed_job(run, job)
            
            elif job_status in [
                JobStatus.ERROR_PROCESSING.value,
                JobStatus.ERROR_CONSUMING.value
            ]:
                # Job failed - mark entire run as failed
                logger.error(
                    "Job failed for run",
                    run_id=run_id,
                    job_id=current_job_id,
                    job_status=job_status
                )
                error_data = job.get("errorData", {})
                error_message = error_data.get("errorMessage", "Job processing failed")
                self._mark_run_failed(run_id, error_message)
            
            # If job is still PENDING or PROCESSING, do nothing and wait
        
        except Exception as e:
            logger.error(
                "Error checking job for run",
                run_id=run_id,
                job_id=current_job_id,
                error=str(e)
            )
    
    def _process_completed_job(self, run: Dict[str, Any], job: Dict[str, Any]):
        """
        Process a completed job - record iteration result and advance run.
        
        Args:
            run: Run document
            job: Completed job document
        """
        run_id = str(run["_id"])
        current_model_index = run["currentModelIndex"]
        current_iteration = run["currentIteration"]
        
        # Extract processing metrics from job
        job_metrics = job.get("processingMetrics", {})
        iteration_metrics = None
        if job_metrics:
            iteration_metrics = {
                "inputTokens": job_metrics.get("inputTokens", 0),
                "outputTokens": job_metrics.get("outputTokens", 0),
                "totalTokens": job_metrics.get("totalTokens", 0),
                "duration": job_metrics.get("duration", 0.0),
                "inputCost": job_metrics.get("inputCost", 0.0),
                "outputCost": job_metrics.get("outputCost", 0.0),
                "totalCost": job_metrics.get("totalCost", 0.0),
                "currency": job_metrics.get("currency", "USD")
            }
        
        # Extract iteration result from job
        iteration_result = {
            "iteration": current_iteration,
            "jobId": str(job["_id"]),
            "workingPromptId": job.get("workingPrompts", job.get("prompts", []))[0] if job.get("workingPrompts", job.get("prompts")) else None,
            "status": job.get("status"),
            "evalResult": job.get("evalResult"),
            "suggestedPromptId": job.get("suggestedPromptId"),
            "processingMetrics": iteration_metrics
        }
        
        # Update run document to add this iteration result
        model_runs = run.get("modelRuns", [])
        if current_model_index < len(model_runs):
            # Append iteration to current model's iterations
            iterations = model_runs[current_model_index].get("iterations", [])
            iterations.append(iteration_result)
            model_runs[current_model_index]["iterations"] = iterations
            
            # Aggregate metrics for this model run
            model_metrics = self._aggregate_metrics([iter_res.get("processingMetrics") for iter_res in iterations if iter_res.get("processingMetrics")])
            if model_metrics:
                model_runs[current_model_index]["processingMetrics"] = model_metrics
            
            # Aggregate metrics for entire run (all models)
            all_iterations = []
            for model_run in model_runs:
                all_iterations.extend(model_run.get("iterations", []))
            
            run_metrics = self._aggregate_metrics([iter_res.get("processingMetrics") for iter_res in all_iterations if iter_res.get("processingMetrics")])
            
            # Update the run document
            update_data = {"modelRuns": model_runs}
            if run_metrics:
                update_data["processingMetrics"] = run_metrics
            
            db_update(
                self.mongo_client,
                self.db_name,
                "runs",
                run_id,
                update_data
            )
            
            logger.info(
                "Iteration result recorded",
                run_id=run_id,
                model_index=current_model_index,
                iteration=current_iteration
            )
        else:
            logger.error(
                "Invalid model index",
                run_id=run_id,
                model_index=current_model_index
            )
            self._mark_run_failed(run_id, f"Invalid model index: {current_model_index}")
            return
        
        # Advance run to next iteration/model
        try:
            run_service = get_run_service()
            run_service._advance_run(run_id)
        except Exception as e:
            logger.error(
                "Error advancing run",
                run_id=run_id,
                error=str(e)
            )
            self._mark_run_failed(run_id, f"Failed to advance run: {str(e)}")
    
    def _aggregate_metrics(self, metrics_list: list) -> Optional[Dict[str, Any]]:
        """
        Aggregate a list of processing metrics into a single metrics object.
        
        Args:
            metrics_list: List of processing metrics dictionaries
            
        Returns:
            Aggregated metrics or None if no metrics available
        """
        # Filter out None values
        valid_metrics = [m for m in metrics_list if m is not None]
        
        if not valid_metrics:
            return None
        
        # Aggregate
        aggregated = {
            "inputTokens": sum(m.get("inputTokens", 0) for m in valid_metrics),
            "outputTokens": sum(m.get("outputTokens", 0) for m in valid_metrics),
            "totalTokens": sum(m.get("totalTokens", 0) for m in valid_metrics),
            "duration": sum(m.get("duration", 0.0) for m in valid_metrics),
            "inputCost": sum(m.get("inputCost", 0.0) for m in valid_metrics),
            "outputCost": sum(m.get("outputCost", 0.0) for m in valid_metrics),
            "totalCost": sum(m.get("totalCost", 0.0) for m in valid_metrics),
            "currency": valid_metrics[0].get("currency", "USD")  # Use first currency
        }
        
        return aggregated
    
    def _mark_run_failed(self, run_id: str, error_message: str):
        """
        Mark a run as failed with error message.
        
        Args:
            run_id: Run document ID
            error_message: Error message to store
        """
        logger.error("Marking run as failed", run_id=run_id, reason=error_message)
        db_update(
            self.mongo_client,
            self.db_name,
            "runs",
            run_id,
            {
                "status": RunStatus.FAILED.value,
                "failureReason": error_message,
                "currentJobId": None
            }
        )
        logger.info("Run marked as failed", run_id=run_id, error=error_message)


# Singleton instance
_run_orchestrator: Optional[RunOrchestrator] = None


def get_run_orchestrator() -> RunOrchestrator:
    """Get or create the singleton run orchestrator instance"""
    global _run_orchestrator
    if _run_orchestrator is None:
        _run_orchestrator = RunOrchestrator()
    return _run_orchestrator

