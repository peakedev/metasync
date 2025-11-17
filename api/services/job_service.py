"""
Job management service layer
Handles business logic for job CRUD operations, validation, and access control
"""
from typing import Optional, Dict, Any, List

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_read,
    db_find_one,
    db_update,
    db_delete,
    get_document_by_id,
    safe_operation
)
from api.core.logging import get_logger, BusinessLogger
from api.models.job_models import JobStatus, JobCreateRequest

logger = get_logger("api.services.job_service")
business_logger = BusinessLogger()


class JobService:
    """Service for managing jobs with validation and access control"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "jobs"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def _validate_prompts_exist(self, prompt_ids: List[str]) -> None:
        """
        Validate that all prompt IDs exist in the prompts collection.
        
        Args:
            prompt_ids: List of prompt IDs to validate
            
        Raises:
            ValueError: If any prompt ID does not exist, with specific message indicating which prompt is missing
        """
        if not prompt_ids:
            raise ValueError("At least one prompt ID is required")
        
        for prompt_id in prompt_ids:
            try:
                prompt = get_document_by_id(
                    self.mongo_client,
                    self.db_name,
                    "prompts",
                    prompt_id
                )
                if not prompt:
                    logger.warning("Prompt not found", prompt_id=prompt_id)
                    raise ValueError(f"Prompt ID '{prompt_id}' does not exist in the prompts collection")
            except ValueError:
                # Re-raise ValueError as-is (it's our validation error)
                raise
            except Exception as e:
                logger.error("Error validating prompt", error=str(e), prompt_id=prompt_id)
                raise ValueError(f"Error validating prompt ID '{prompt_id}': {str(e)}")
    
    def _validate_model_exists(self, model_name: str) -> None:
        """
        Validate that the model exists in the models collection.
        
        Args:
            model_name: Model name to validate
            
        Raises:
            ValueError: If the model does not exist, with specific message
        """
        if not model_name:
            raise ValueError("Model name is required")
        
        try:
            model = db_find_one(
                self.mongo_client,
                self.db_name,
                "models",
                query={"name": model_name}
            )
            if not model:
                logger.warning("Model not found", model_name=model_name)
                raise ValueError(f"Model '{model_name}' does not exist in the models collection")
        except ValueError:
            # Re-raise ValueError as-is (it's our validation error)
            raise
        except Exception as e:
            logger.error("Error validating model", error=str(e), model_name=model_name)
            raise ValueError(f"Error validating model '{model_name}': {str(e)}")
    
    def _validate_status_transition(self, current_status: JobStatus, new_status: JobStatus) -> bool:
        """
        Validate that a status transition is allowed for clients.
        
        Allowed transitions:
        - PENDING → CANCELED
        - ERROR → CANCELED
        - CANCELED → PENDING
        - ERROR → PENDING
        - PROCESSED → ACKNOWLEDGED
        
        Args:
            current_status: Current job status
            new_status: Desired new status
            
        Returns:
            True if transition is allowed, False otherwise
        """
        allowed_transitions = {
            JobStatus.PENDING: [JobStatus.CANCELED],
            JobStatus.ERROR: [JobStatus.CANCELED, JobStatus.PENDING],
            JobStatus.CANCELED: [JobStatus.PENDING],
            JobStatus.PROCESSED: [JobStatus.ACKNOWLEDGED]
        }
        
        allowed = allowed_transitions.get(current_status, [])
        return new_status in allowed
    
    def _check_job_access(self, job: Dict[str, Any], client_id: Optional[str], is_admin: bool = False) -> bool:
        """
        Check if a client has access to a job.
        
        Args:
            job: Job document
            client_id: Client ID requesting access
            is_admin: Whether the requester is an admin
            
        Returns:
            True if access is allowed, False otherwise
        """
        if is_admin:
            return True
        
        if not client_id:
            return False
        
        job_client_id = job.get("clientId")
        return job_client_id == client_id
    
    def create_job(self, client_id: str, operation: str, prompts: List[str], model: str,
                   temperature: float, priority: int, request_data: Dict[str, Any],
                   job_id: Optional[str] = None, client_reference: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new job with validation.
        
        Args:
            client_id: Client ID creating the job
            operation: Operation type
            prompts: List of prompt IDs
            model: Model name
            temperature: Temperature (0-1)
            priority: Priority (1-1000)
            request_data: Request data to be sent to LLM (required)
            job_id: Optional client-provided job ID
            client_reference: Optional client reference data
            
        Returns:
            Created job dictionary
            
        Raises:
            ValueError: If validation fails
        """
        business_logger.log_operation("job_service", "create_job", client_id=client_id)
        
        # Validate prompts exist in the prompts collection
        logger.info("Validating prompts", prompt_ids=prompts, client_id=client_id)
        self._validate_prompts_exist(prompts)
        logger.info("Prompts validation passed", prompt_ids=prompts)
        
        # Validate model exists in the models collection
        logger.info("Validating model", model=model, client_id=client_id)
        self._validate_model_exists(model)
        logger.info("Model validation passed", model=model)
        
        # Check if job_id is provided and unique (if provided)
        if job_id:
            existing = db_find_one(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                query={"id": job_id, "clientId": client_id}
            )
            if existing:
                raise ValueError(f"Job ID '{job_id}' already exists for this client")
        
        # Create job document
        job_doc = {
            "clientId": client_id,
            "status": JobStatus.PENDING.value,
            "operation": operation,
            "prompts": prompts,
            "model": model,
            "temperature": temperature,
            "priority": priority,
            "requestData": request_data
        }
        
        if job_id:
            job_doc["id"] = job_id
        
        if client_reference:
            job_doc["clientReference"] = client_reference
        
        # Save to database
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_doc
        )
        
        if not db_id:
            business_logger.log_error("job_service", "create_job", "Failed to create job in database")
            raise RuntimeError("Failed to create job in database")
        
        logger.info("Job created successfully", job_id=db_id, client_id=client_id)
        
        # Return the created job
        return self.get_job_by_id(db_id, client_id)
    
    def create_jobs_batch(self, client_id: str, job_requests: List[JobCreateRequest]) -> List[Dict[str, Any]]:
        """
        Create multiple jobs at once with validation (all-or-nothing).
        
        Args:
            client_id: Client ID creating the jobs
            job_requests: List of job creation requests
            
        Returns:
            List of created job dictionaries
            
        Raises:
            ValueError: If validation fails for any job (entire batch fails)
        """
        business_logger.log_operation("job_service", "create_jobs_batch", client_id=client_id, job_count=len(job_requests))
        
        if not job_requests:
            raise ValueError("At least one job is required in the batch")
        
        # Validate all jobs first (all-or-nothing approach)
        logger.info("Validating batch of jobs", job_count=len(job_requests), client_id=client_id)
        
        # Check for duplicate job IDs within the batch
        job_ids_in_batch = {}
        for idx, job_request in enumerate(job_requests):
            if job_request.id:
                if job_request.id in job_ids_in_batch:
                    raise ValueError(f"Duplicate job ID '{job_request.id}' found in batch (jobs {job_ids_in_batch[job_request.id] + 1} and {idx + 1})")
                job_ids_in_batch[job_request.id] = idx
        
        # Validate each job
        for idx, job_request in enumerate(job_requests):
            try:
                # Validate prompts exist
                self._validate_prompts_exist(job_request.prompts)
                
                # Validate model exists
                self._validate_model_exists(job_request.model)
                
                # Check if job_id is provided and unique in database (if provided)
                if job_request.id:
                    existing = db_find_one(
                        self.mongo_client,
                        self.db_name,
                        self.collection_name,
                        query={"id": job_request.id, "clientId": client_id}
                    )
                    if existing:
                        raise ValueError(f"Job ID '{job_request.id}' already exists for this client (job {idx + 1} in batch)")
            except ValueError as e:
                logger.warning("Validation error in batch", error=str(e), job_index=idx, client_id=client_id)
                raise ValueError(f"Validation failed for job {idx + 1} in batch: {str(e)}")
        
        logger.info("All jobs in batch validated successfully", job_count=len(job_requests))
        
        # Create all jobs
        created_jobs = []
        created_db_ids = []
        
        try:
            for idx, job_request in enumerate(job_requests):
                # Create job document
                job_doc = {
                    "clientId": client_id,
                    "status": JobStatus.PENDING.value,
                    "operation": job_request.operation,
                    "prompts": job_request.prompts,
                    "model": job_request.model,
                    "temperature": job_request.temperature,
                    "priority": job_request.priority,
                    "requestData": job_request.requestData
                }
                
                if job_request.id:
                    job_doc["id"] = job_request.id
                
                if job_request.clientReference:
                    job_doc["clientReference"] = job_request.clientReference
                
                # Save to database
                db_id = db_create(
                    self.mongo_client,
                    self.db_name,
                    self.collection_name,
                    job_doc
                )
                
                if not db_id:
                    business_logger.log_error("job_service", "create_jobs_batch", f"Failed to create job {idx + 1} in database")
                    raise RuntimeError(f"Failed to create job {idx + 1} in database")
                
                created_db_ids.append(db_id)
                logger.info("Job created in batch", job_id=db_id, job_index=idx + 1, client_id=client_id)
            
            # Fetch all created jobs
            for db_id in created_db_ids:
                job = self.get_job_by_id(db_id, client_id)
                created_jobs.append(job)
            
            logger.info("Batch of jobs created successfully", job_count=len(created_jobs), client_id=client_id)
            return created_jobs
            
        except Exception as e:
            # If any job creation fails, we've already created some jobs
            # In a production system, you might want to rollback, but for now we'll just log
            logger.error("Error creating jobs batch", error=str(e), created_count=len(created_db_ids), client_id=client_id)
            raise RuntimeError(f"Failed to create jobs batch: {str(e)}")
    
    def list_jobs(
        self,
        client_id: Optional[str] = None,
        is_admin: bool = False,
        job_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
        operation: Optional[str] = None,
        model: Optional[str] = None,
        priority: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List jobs with access control and optional filters.
        
        Args:
            client_id: Client ID (required if not admin)
            is_admin: Whether the requester is an admin
            job_id: Optional filter by client-provided job ID
            status: Optional filter by job status
            operation: Optional filter by operation
            model: Optional filter by model
            priority: Optional filter by priority
            limit: Optional limit on number of results returned
            
        Returns:
            List of job dictionaries
        """
        business_logger.log_operation("job_service", "list_jobs", client_id=client_id, is_admin=is_admin)
        
        # Build query
        if is_admin:
            query = {}
        else:
            if not client_id:
                raise ValueError("Client ID is required for non-admin users")
            query = {"clientId": client_id}
        
        # Add filters
        if job_id is not None:
            query["id"] = job_id
        
        if status is not None:
            query["status"] = status.value
        
        if operation is not None:
            query["operation"] = operation
        
        if model is not None:
            query["model"] = model
        
        if priority is not None:
            query["priority"] = priority
        
        jobs = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query,
            limit=limit
        )
        
        result = []
        for job in jobs:
            # Additional defensive check: ensure non-admin users only see their own jobs
            if not is_admin:
                job_client_id = job.get("clientId")
                if job_client_id != client_id:
                    logger.warning(
                        "Job returned with incorrect clientId, filtering out",
                        job_id=str(job.get("_id")),
                        expected_client_id=client_id,
                        actual_client_id=job_client_id
                    )
                    continue
            
            result.append(self._format_job_response(job))
        
        logger.info("Listed jobs", count=len(result), client_id=client_id, is_admin=is_admin)
        return result
    
    def get_job_by_id(self, job_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> Dict[str, Any]:
        """
        Get a job by ID with access control.
        
        Args:
            job_id: Job document ID
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Job dictionary
            
        Raises:
            ValueError: If job not found or access denied
        """
        business_logger.log_operation("job_service", "get_job_by_id", job_id=job_id, client_id=client_id)
        
        job = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id
        )
        
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Check access
        if not self._check_job_access(job, client_id, is_admin):
            raise ValueError("Access denied: job not found or insufficient permissions")
        
        return self._format_job_response(job)
    
    def update_job_status(self, job_id: str, new_status: JobStatus, client_id: str) -> Dict[str, Any]:
        """
        Update job status with transition validation (for clients).
        
        Args:
            job_id: Job document ID
            new_status: New status
            client_id: Client ID (must own the job)
            
        Returns:
            Updated job dictionary
            
        Raises:
            ValueError: If job not found, access denied, or invalid transition
        """
        business_logger.log_operation("job_service", "update_job_status", job_id=job_id, client_id=client_id, new_status=new_status.value)
        
        # Get existing job
        job = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id
        )
        
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Check access
        if not self._check_job_access(job, client_id, is_admin=False):
            raise ValueError("Access denied: job not found or insufficient permissions")
        
        # Get current status
        current_status_str = job.get("status")
        try:
            current_status = JobStatus(current_status_str)
        except ValueError:
            logger.error("Invalid current status", job_id=job_id, status=current_status_str)
            raise ValueError(f"Invalid current job status: {current_status_str}")
        
        # Validate transition
        if not self._validate_status_transition(current_status, new_status):
            raise ValueError(f"Invalid status transition from {current_status.value} to {new_status.value}")
        
        # Update status
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id,
            {"status": new_status.value}
        )
        
        if not success:
            business_logger.log_error("job_service", "update_job_status", "Failed to update job status in database")
            raise RuntimeError("Failed to update job status in database")
        
        logger.info("Job status updated successfully", job_id=job_id, old_status=current_status.value, new_status=new_status.value)
        
        # Return updated job
        return self.get_job_by_id(job_id, client_id)
    
    def update_job(self, job_id: str, status: Optional[JobStatus] = None,
                   operation: Optional[str] = None, prompts: Optional[List[str]] = None,
                   model: Optional[str] = None, temperature: Optional[float] = None,
                   priority: Optional[int] = None, request_data: Optional[Dict[str, Any]] = None,
                   client_reference: Optional[Dict[str, Any]] = None,
                   client_id: Optional[str] = None, is_admin: bool = False) -> Dict[str, Any]:
        """
        Full update of a job (for workers/admin).
        
        Args:
            job_id: Job document ID
            status: Optional new status
            operation: Optional new operation
            prompts: Optional new prompts list
            model: Optional new model
            temperature: Optional new temperature
            priority: Optional new priority
            request_data: Optional new request data
            client_reference: Optional new client reference
            client_id: Optional client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Updated job dictionary
            
        Raises:
            ValueError: If job not found, access denied, or validation fails
        """
        business_logger.log_operation("job_service", "update_job", job_id=job_id, is_admin=is_admin)
        
        # Get existing job
        job = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id
        )
        
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Check access (admin can update any, client can only update their own)
        if not is_admin:
            if not client_id or not self._check_job_access(job, client_id, is_admin=False):
                raise ValueError("Access denied: job not found or insufficient permissions")
        
        # Build update document
        updates = {}
        
        if status is not None:
            updates["status"] = status.value
        
        if operation is not None:
            updates["operation"] = operation
        
        if prompts is not None:
            # Validate prompts exist in the prompts collection
            self._validate_prompts_exist(prompts)
            updates["prompts"] = prompts
        
        if model is not None:
            # Validate model exists in the models collection
            self._validate_model_exists(model)
            updates["model"] = model
        
        if temperature is not None:
            if temperature < 0.0 or temperature > 1.0:
                raise ValueError("Temperature must be between 0 and 1")
            updates["temperature"] = temperature
        
        if priority is not None:
            if priority < 1 or priority > 1000:
                raise ValueError("Priority must be between 1 and 1000")
            updates["priority"] = priority
        
        if request_data is not None:
            updates["requestData"] = request_data
        
        if client_reference is not None:
            updates["clientReference"] = client_reference
        
        if not updates:
            logger.warning("No updates provided", job_id=job_id)
            return self._format_job_response(job)
        
        # Update the job
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id,
            updates
        )
        
        if not success:
            business_logger.log_error("job_service", "update_job", "Failed to update job in database")
            raise RuntimeError("Failed to update job in database")
        
        logger.info("Job updated successfully", job_id=job_id)
        
        # Return updated job
        return self.get_job_by_id(job_id, client_id, is_admin)
    
    def delete_job(self, job_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> bool:
        """
        Soft delete a job with access control.
        
        Args:
            job_id: Job document ID
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            True if deletion successful
            
        Raises:
            ValueError: If job not found or access denied
        """
        business_logger.log_operation("job_service", "delete_job", job_id=job_id, client_id=client_id)
        
        # Get existing job
        job = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id
        )
        
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Check access
        if not self._check_job_access(job, client_id, is_admin):
            raise ValueError("Access denied: job not found or insufficient permissions")
        
        # Soft delete the job
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            job_id
        )
        
        if success:
            logger.info("Job deleted successfully", job_id=job_id)
        else:
            business_logger.log_error("job_service", "delete_job", "Failed to delete job in database")
            raise RuntimeError("Failed to delete job in database")
        
        return success
    
    def get_jobs_summary(
        self,
        client_id: str,
        operation: Optional[str] = None,
        model: Optional[str] = None,
        job_id: Optional[str] = None,
        client_reference_filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get summary of jobs with counts by status, with optional filtering.
        
        Args:
            client_id: Client ID (required, clients can only see their own jobs)
            operation: Optional filter by operation
            model: Optional filter by model
            job_id: Optional filter by client-provided job ID
            client_reference_filters: Optional dict of filters for clientReference fields
                e.g., {"randomProp": "hello"} will filter where clientReference.randomProp == "hello"
            
        Returns:
            Dictionary with counts by status, total count, and aggregated processingMetrics
        """
        business_logger.log_operation("job_service", "get_jobs_summary", client_id=client_id)
        
        # Build query - clients can only see their own jobs
        query = {"clientId": client_id}
        
        # Add filters
        if operation:
            query["operation"] = operation
        
        if model:
            query["model"] = model
        
        if job_id:
            query["id"] = job_id
        
        # Add clientReference filters (nested field filtering)
        if client_reference_filters:
            for key, value in client_reference_filters.items():
                query[f"clientReference.{key}"] = value
        
        # Use aggregation to count by status
        db = self.mongo_client[self.db_name]
        collection = db[self.collection_name]
        
        # Build aggregation pipeline
        pipeline = [
            {"$match": query},
            {"$match": {"_metadata.isDeleted": {"$ne": True}}},  # Exclude soft-deleted
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        try:
            # Execute aggregation with retry logic
            def aggregate_operation():
                return list(collection.aggregate(pipeline))
            
            results = safe_operation(aggregate_operation)
            
            # Initialize counts for all statuses
            summary = {
                JobStatus.PENDING.value: 0,
                JobStatus.PROCESSING.value: 0,
                JobStatus.PROCESSED.value: 0,
                JobStatus.ACKNOWLEDGED.value: 0,
                JobStatus.ERROR.value: 0,
                JobStatus.CANCELED.value: 0,
                "total": 0
            }
            
            # Populate counts from aggregation results
            for result in results:
                status = result.get("_id")
                count = result.get("count", 0)
                if status in summary:
                    summary[status] = count
                    summary["total"] += count
            
            # Aggregate processingMetrics from PROCESSED and ACKNOWLEDGED jobs
            metrics_query = {
                **query,
                "status": {"$in": [JobStatus.PROCESSED.value, JobStatus.ACKNOWLEDGED.value]},
                "processingMetrics": {"$exists": True, "$ne": None}
            }
            
            def find_metrics_operation():
                return list(collection.find(metrics_query, {"processingMetrics": 1}))
            
            jobs_with_metrics = safe_operation(find_metrics_operation)
            
            if jobs_with_metrics:
                # Initialize aggregated metrics
                total_input_tokens = 0
                total_output_tokens = 0
                total_tokens = 0
                total_duration = 0.0
                total_input_cost = 0.0
                total_output_cost = 0.0
                total_cost = 0.0
                currencies = set()
                jobs_with_currency = 0
                jobs_without_currency = 0
                
                # Aggregate metrics from all jobs
                for job in jobs_with_metrics:
                    metrics = job.get("processingMetrics", {})
                    if not metrics:
                        continue
                    
                    # Sum always-available fields
                    if "inputTokens" in metrics:
                        total_input_tokens += metrics.get("inputTokens", 0)
                    if "outputTokens" in metrics:
                        total_output_tokens += metrics.get("outputTokens", 0)
                    if "totalTokens" in metrics:
                        total_tokens += metrics.get("totalTokens", 0)
                    if "duration" in metrics:
                        total_duration += metrics.get("duration", 0.0)
                    
                    # Collect cost data and currencies
                    if "currency" in metrics and metrics["currency"]:
                        currencies.add(metrics["currency"])
                        jobs_with_currency += 1
                        # Sum cost fields if they exist
                        if "inputCost" in metrics:
                            total_input_cost += metrics.get("inputCost", 0.0)
                        if "outputCost" in metrics:
                            total_output_cost += metrics.get("outputCost", 0.0)
                        if "totalCost" in metrics:
                            total_cost += metrics.get("totalCost", 0.0)
                    else:
                        jobs_without_currency += 1
                
                # Build processingMetrics response
                processing_metrics = {
                    "inputTokens": total_input_tokens,
                    "outputTokens": total_output_tokens,
                    "totalTokens": total_tokens,
                    "duration": round(total_duration, 2)
                }
                
                # Check if all currencies match
                # Only include cost data if all jobs have currency and all currencies are the same
                if len(currencies) == 1 and jobs_without_currency == 0:
                    # All jobs have the same currency, include cost data
                    processing_metrics["inputCost"] = total_input_cost
                    processing_metrics["outputCost"] = total_output_cost
                    processing_metrics["totalCost"] = total_cost
                    processing_metrics["currency"] = currencies.pop()
                elif len(currencies) > 1 or (len(currencies) == 1 and jobs_without_currency > 0):
                    # Multiple different currencies found, or some jobs missing currency
                    processing_metrics["currency"] = "different currencies found, no cost data could be summarised"
                else:
                    # No currency data available at all
                    processing_metrics["currency"] = None
                
                summary["processingMetrics"] = processing_metrics
            else:
                # No jobs with metrics found
                summary["processingMetrics"] = None
            
            logger.info("Job summary retrieved", client_id=client_id, summary=summary)
            return summary
            
        except Exception as e:
            logger.error("Error getting job summary", error=str(e), client_id=client_id)
            raise RuntimeError(f"Failed to get job summary: {str(e)}")
    
    def _format_job_response(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a job document for API response.
        
        Args:
            job: Raw job document from database
            
        Returns:
            Formatted job dictionary
        """
        return {
            "jobId": str(job["_id"]),
            "clientId": job.get("clientId"),
            "status": job.get("status"),
            "operation": job.get("operation"),
            "prompts": job.get("prompts", []),
            "model": job.get("model"),
            "temperature": job.get("temperature"),
            "priority": job.get("priority"),
            "id": job.get("id"),
            "requestData": job.get("requestData", job.get("data", {})),  # Support both old and new field names for backward compatibility
            "responseData": job.get("responseData"),
            "processingMetrics": job.get("processingMetrics"),
            "clientReference": job.get("clientReference"),
            "_metadata": job.get("_metadata", {})
        }


# Singleton instance
_job_service: Optional[JobService] = None


def get_job_service() -> JobService:
    """Get or create the singleton job service instance"""
    global _job_service
    if _job_service is None:
        _job_service = JobService()
    return _job_service

