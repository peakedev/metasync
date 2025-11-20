"""
Run management service layer
Handles business logic for run CRUD operations, validation, and orchestration
"""
from typing import Optional, Dict, Any, List
from datetime import datetime

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_read,
    db_find_one,
    db_update,
    db_delete,
    get_document_by_id
)
from api.core.logging import get_logger, BusinessLogger
from api.models.run_models import RunStatus, ModelRun, IterationResult
from api.services.job_service import get_job_service

logger = get_logger("api.services.run_service")
business_logger = BusinessLogger()


class RunService:
    """Service for managing runs with validation and orchestration"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "runs"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def _validate_prompts_exist(self, prompt_ids: List[str]) -> None:
        """Validate that all prompt IDs exist in the prompts collection."""
        job_service = get_job_service()
        job_service._validate_prompts_exist(prompt_ids)
    
    def _validate_models_exist(self, model_names: List[str]) -> None:
        """Validate that all model names exist in the models collection."""
        job_service = get_job_service()
        for model_name in model_names:
            job_service._validate_model_exists(model_name)
    
    def create_run(
        self,
        client_id: str,
        initial_working_prompt_id: str,
        eval_prompt_id: str,
        eval_model: str,
        meta_prompt_id: str,
        meta_model: str,
        working_models: List[str],
        max_iterations: int,
        temperature: float,
        priority: int,
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new run with validation and seed the first job.
        
        Args:
            client_id: Client ID creating the run
            initial_working_prompt_id: Starting working prompt ID
            eval_prompt_id: Evaluation prompt ID (fixed)
            eval_model: Evaluation model name (fixed)
            meta_prompt_id: Meta-prompting prompt ID (fixed)
            meta_model: Meta-prompting model name (fixed)
            working_models: List of working model names to iterate through
            max_iterations: Maximum iterations per model
            temperature: Temperature (0-1)
            priority: Priority (1-1000)
            request_data: Input data for working prompts
            
        Returns:
            Created run dictionary
            
        Raises:
            ValueError: If validation fails
        """
        business_logger.log_operation("run_service", "create_run", client_id=client_id)
        
        # Validate all prompts exist
        logger.info("Validating prompts", client_id=client_id)
        self._validate_prompts_exist([
            initial_working_prompt_id,
            eval_prompt_id,
            meta_prompt_id
        ])
        logger.info("Prompts validation passed")
        
        # Validate all models exist
        logger.info("Validating models", client_id=client_id)
        all_models = working_models + [eval_model, meta_model]
        self._validate_models_exist(all_models)
        logger.info("Models validation passed")
        
        # Initialize model runs structure
        model_runs = []
        for model in working_models:
            model_runs.append({
                "model": model,
                "iterations": []
            })
        
        # Create run document
        run_doc = {
            "clientId": client_id,
            "status": RunStatus.PENDING.value,
            "initialWorkingPromptId": initial_working_prompt_id,
            "evalPromptId": eval_prompt_id,
            "evalModel": eval_model,
            "metaPromptId": meta_prompt_id,
            "metaModel": meta_model,
            "workingModels": working_models,
            "maxIterations": max_iterations,
            "temperature": temperature,
            "priority": priority,
            "requestData": request_data,
            "currentModelIndex": 0,
            "currentIteration": 0,
            "currentJobId": None,
            "modelRuns": model_runs
        }
        
        # Save to database
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_doc
        )
        
        if not db_id:
            business_logger.log_error("run_service", "create_run", "Failed to create run in database")
            raise RuntimeError("Failed to create run in database")
        
        logger.info("Run created successfully", run_id=db_id, client_id=client_id)
        
        # Get the created run
        run = self.get_run_by_id(db_id, client_id)
        
        # Seed the first job and update run status to RUNNING
        try:
            self._seed_next_job(run)
            logger.info("First job seeded successfully", run_id=db_id)
        except Exception as e:
            logger.error("Failed to seed first job", error=str(e), run_id=db_id)
            # Mark run as failed
            db_update(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                db_id,
                {"status": RunStatus.FAILED.value}
            )
            raise RuntimeError(f"Failed to seed first job: {str(e)}")
        
        # Return updated run
        return self.get_run_by_id(db_id, client_id)
    
    def _seed_next_job(self, run: Dict[str, Any]) -> str:
        """
        Create the next job for a run based on current state.
        
        Args:
            run: Run document
            
        Returns:
            Job ID of the created job
        """
        run_id = str(run["_id"])
        client_id = run["clientId"]
        current_model_index = run["currentModelIndex"]
        current_iteration = run["currentIteration"]
        working_models = run["workingModels"]
        max_iterations = run["maxIterations"]
        
        # Determine working prompt to use
        if current_iteration == 0:
            # First iteration: use initial working prompt
            working_prompt_id = run["initialWorkingPromptId"]
        else:
            # Subsequent iterations: use suggested prompt from previous iteration
            model_runs = run.get("modelRuns", [])
            if current_model_index < len(model_runs):
                iterations = model_runs[current_model_index].get("iterations", [])
                if iterations and len(iterations) > 0:
                    # Get the last iteration's suggested prompt
                    last_iteration = iterations[-1]
                    working_prompt_id = last_iteration.get("suggestedPromptId")
                    if not working_prompt_id:
                        raise ValueError(f"No suggested prompt found for iteration {current_iteration - 1}")
                else:
                    # Shouldn't happen, but fall back to initial prompt
                    working_prompt_id = run["initialWorkingPromptId"]
            else:
                raise ValueError(f"Invalid model index: {current_model_index}")
        
        # Get current working model
        working_model = working_models[current_model_index]
        
        # Create job using job service
        job_service = get_job_service()
        job = job_service.create_job(
            client_id=client_id,
            operation="optimize",
            prompts=None,
            working_prompts=[working_prompt_id],
            model=working_model,
            temperature=run["temperature"],
            priority=run["priority"],
            request_data=run["requestData"],
            client_reference={
                "runId": run_id,
                "modelIndex": current_model_index,
                "iteration": current_iteration
            },
            eval_prompt=run["evalPromptId"],
            eval_model=run["evalModel"],
            meta_prompt=run["metaPromptId"],
            meta_model=run["metaModel"]
        )
        
        job_id = job["jobId"]
        
        # Update run with current job ID and status
        db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id,
            {
                "currentJobId": job_id,
                "status": RunStatus.RUNNING.value
            }
        )
        
        logger.info(
            "Job created for run",
            run_id=run_id,
            job_id=job_id,
            model=working_model,
            iteration=current_iteration
        )
        
        return job_id
    
    def _advance_run(self, run_id: str) -> None:
        """
        Advance a run to the next iteration or model, or mark it complete.
        
        Args:
            run_id: Run document ID
        """
        run = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id
        )
        
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        current_model_index = run["currentModelIndex"]
        current_iteration = run["currentIteration"]
        max_iterations = run["maxIterations"]
        working_models = run["workingModels"]
        
        # Determine next state
        next_iteration = current_iteration + 1
        next_model_index = current_model_index
        
        if next_iteration >= max_iterations:
            # Move to next model
            next_model_index = current_model_index + 1
            next_iteration = 0
            
            if next_model_index >= len(working_models):
                # All models completed - mark run as complete
                db_update(
                    self.mongo_client,
                    self.db_name,
                    self.collection_name,
                    run_id,
                    {
                        "status": RunStatus.COMPLETED.value,
                        "currentJobId": None
                    }
                )
                logger.info("Run completed", run_id=run_id)
                return
        
        # Update run state
        db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id,
            {
                "currentModelIndex": next_model_index,
                "currentIteration": next_iteration,
                "currentJobId": None,
                "status": RunStatus.RUNNING.value
            }
        )
        
        # Seed next job
        updated_run = self.get_run_by_id(run_id, run["clientId"], is_admin=True)
        self._seed_next_job(updated_run)
        
        logger.info(
            "Run advanced",
            run_id=run_id,
            next_model_index=next_model_index,
            next_iteration=next_iteration
        )
    
    def list_runs(
        self,
        client_id: Optional[str] = None,
        is_admin: bool = False,
        status: Optional[RunStatus] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List runs with access control and optional filters.
        
        Args:
            client_id: Client ID (required if not admin)
            is_admin: Whether the requester is an admin
            status: Optional filter by status
            limit: Optional limit on number of results
            
        Returns:
            List of run dictionaries
        """
        business_logger.log_operation("run_service", "list_runs", client_id=client_id, is_admin=is_admin)
        
        # Build query
        if is_admin:
            query = {}
        else:
            if not client_id:
                raise ValueError("Client ID is required for non-admin users")
            query = {"clientId": client_id}
        
        # Add status filter
        if status is not None:
            query["status"] = status.value
        
        runs = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query,
            limit=limit
        )
        
        result = []
        for run in runs:
            # Additional defensive check
            if not is_admin:
                run_client_id = run.get("clientId")
                if run_client_id != client_id:
                    logger.warning(
                        "Run returned with incorrect clientId, filtering out",
                        run_id=str(run.get("_id")),
                        expected_client_id=client_id,
                        actual_client_id=run_client_id
                    )
                    continue
            
            result.append(self._format_run_response(run))
        
        logger.info("Listed runs", count=len(result), client_id=client_id, is_admin=is_admin)
        return result
    
    def get_run_by_id(
        self,
        run_id: str,
        client_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        """
        Get a run by ID with access control.
        
        Args:
            run_id: Run document ID
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Run dictionary
            
        Raises:
            ValueError: If run not found or access denied
        """
        business_logger.log_operation("run_service", "get_run_by_id", run_id=run_id, client_id=client_id)
        
        run = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id
        )
        
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        # Check access
        if not is_admin:
            if not client_id or run.get("clientId") != client_id:
                raise ValueError("Access denied: run not found or insufficient permissions")
        
        return self._format_run_response(run)
    
    def update_run_status(
        self,
        run_id: str,
        action: str,
        client_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        """
        Update run status based on action (pause, resume, cancel).
        
        Args:
            run_id: Run document ID
            action: Action to perform ('pause', 'resume', 'cancel')
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Updated run dictionary
            
        Raises:
            ValueError: If run not found, access denied, or invalid action
        """
        business_logger.log_operation("run_service", "update_run_status", run_id=run_id, action=action)
        
        # Get existing run
        run = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id
        )
        
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        # Check access
        if not is_admin:
            if not client_id or run.get("clientId") != client_id:
                raise ValueError("Access denied: run not found or insufficient permissions")
        
        current_status = RunStatus(run.get("status"))
        new_status = None
        
        # Validate action and determine new status
        if action == "pause":
            if current_status != RunStatus.RUNNING:
                raise ValueError(f"Cannot pause run with status {current_status.value}")
            new_status = RunStatus.PAUSED
        elif action == "resume":
            if current_status != RunStatus.PAUSED:
                raise ValueError(f"Cannot resume run with status {current_status.value}")
            new_status = RunStatus.RUNNING
        elif action == "cancel":
            if current_status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]:
                raise ValueError(f"Cannot cancel run with status {current_status.value}")
            new_status = RunStatus.CANCELLED
        else:
            raise ValueError(f"Invalid action: {action}. Must be 'pause', 'resume', or 'cancel'")
        
        # Update status
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id,
            {"status": new_status.value}
        )
        
        if not success:
            business_logger.log_error("run_service", "update_run_status", "Failed to update run status")
            raise RuntimeError("Failed to update run status")
        
        logger.info("Run status updated", run_id=run_id, old_status=current_status.value, new_status=new_status.value)
        
        # Return updated run
        return self.get_run_by_id(run_id, client_id, is_admin)
    
    def delete_run(
        self,
        run_id: str,
        client_id: Optional[str] = None,
        is_admin: bool = False
    ) -> bool:
        """
        Soft delete a run with access control.
        
        Args:
            run_id: Run document ID
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            True if deletion successful
            
        Raises:
            ValueError: If run not found or access denied
        """
        business_logger.log_operation("run_service", "delete_run", run_id=run_id, client_id=client_id)
        
        # Get existing run
        run = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id
        )
        
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        
        # Check access
        if not is_admin:
            if not client_id or run.get("clientId") != client_id:
                raise ValueError("Access denied: run not found or insufficient permissions")
        
        # Soft delete the run
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            run_id
        )
        
        if success:
            logger.info("Run deleted successfully", run_id=run_id)
        else:
            business_logger.log_error("run_service", "delete_run", "Failed to delete run")
            raise RuntimeError("Failed to delete run")
        
        return success
    
    def _format_run_response(self, run: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a run document for API response.
        
        Args:
            run: Raw run document from database
            
        Returns:
            Formatted run dictionary
        """
        return {
            "runId": str(run["_id"]),
            "clientId": run.get("clientId"),
            "status": run.get("status"),
            "initialWorkingPromptId": run.get("initialWorkingPromptId"),
            "evalPromptId": run.get("evalPromptId"),
            "evalModel": run.get("evalModel"),
            "metaPromptId": run.get("metaPromptId"),
            "metaModel": run.get("metaModel"),
            "workingModels": run.get("workingModels", []),
            "maxIterations": run.get("maxIterations"),
            "temperature": run.get("temperature"),
            "priority": run.get("priority"),
            "requestData": run.get("requestData", {}),
            "currentModelIndex": run.get("currentModelIndex", 0),
            "currentIteration": run.get("currentIteration", 0),
            "currentJobId": run.get("currentJobId"),
            "modelRuns": run.get("modelRuns", []),
            "_metadata": run.get("_metadata", {})
        }


# Singleton instance
_run_service: Optional[RunService] = None


def get_run_service() -> RunService:
    """Get or create the singleton run service instance"""
    global _run_service
    if _run_service is None:
        _run_service = RunService()
    return _run_service

