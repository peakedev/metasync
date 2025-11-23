"""
Job management API router
Provides CRUD operations for jobs with client and admin authentication
"""
from fastapi import APIRouter, HTTPException, Depends, Header, Query, Request
from fastapi import status as http_status
from typing import List, Optional, Annotated, Dict, Any

from api.middleware.auth import verify_admin_api_key
from api.middleware.client_auth import verify_client_auth
from api.models.job_models import (
    JobCreateRequest,
    JobBatchCreateRequest,
    JobBatchUpdateRequest,
    JobBatchDeleteRequest,
    JobStatusUpdateRequest,
    JobUpdateRequest,
    JobResponse,
    JobStatus,
    JobSummaryResponse
)
from api.services.job_service import get_job_service
from api.core.logging import get_logger

logger = get_logger("api.routers.jobs")

router = APIRouter()


def optional_client_auth(
    client_id: Annotated[Optional[str], Header(alias="client_id")] = None,
    client_api_key: Annotated[
        Optional[str], Header(alias="client_api_key")
    ] = None
) -> Optional[str]:
    """
    Optional client authentication.
    
    Returns client_id if valid, None otherwise.
    """
    if client_id is None or client_api_key is None:
        return None
    try:
        return verify_client_auth(client_id, client_api_key)
    except Exception:
        # Catch all exceptions (including HTTPException and database errors)
        return None


def optional_admin_auth(
    admin_api_key: Annotated[
        Optional[str], Header(alias="admin_api_key")
    ] = None
) -> Optional[str]:
    """
    Optional admin authentication.
    
    Returns admin_api_key if valid, None otherwise.
    """
    if admin_api_key is None:
        return None
    try:
        return verify_admin_api_key(admin_api_key)
    except Exception:
        # Catch all exceptions (including HTTPException and database errors)
        return None


@router.post("", response_model=JobResponse, status_code=http_status.HTTP_201_CREATED)
async def create_job(
    request: JobCreateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Create a new job.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Validates that all prompt IDs exist in the prompts collection
    - Validates that the model exists in the models collection
    - Returns the created job data
    """
    try:
        service = get_job_service()
        job = service.create_job(
            client_id=client_id,
            operation=request.operation,
            prompts=request.prompts,
            working_prompts=request.workingPrompts,
            model=request.model,
            temperature=request.temperature,
            priority=request.priority,
            request_data=request.requestData,
            job_id=request.id,
            client_reference=request.clientReference,
            eval_prompt=request.evalPrompt,
            eval_model=request.evalModel,
            meta_prompt=request.metaPrompt,
            meta_model=request.metaModel
        )
        
        return JobResponse(**job)
    except ValueError as e:
        logger.warning("Validation error creating job", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating job", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create job"
        )


@router.post(
    "/batch",
    response_model=List[JobResponse],
    status_code=http_status.HTTP_201_CREATED
)
async def create_jobs_batch(
    request: JobBatchCreateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Create multiple jobs at once.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Validates that all prompt IDs exist in the prompts collection
      for each job
    - Validates that all models exist in the models collection for
      each job
    - Returns a list of created job data
    - If any job fails validation, the entire batch fails
      (all-or-nothing)
    """
    try:
        service = get_job_service()
        jobs = service.create_jobs_batch(
            client_id=client_id,
            job_requests=request.jobs
        )
        
        return [JobResponse(**job) for job in jobs]
    except ValueError as e:
        logger.warning("Validation error creating jobs batch", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating jobs batch", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create jobs batch"
        )


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth),
    jobId: Optional[str] = Query(None, description="Filter by client-provided job ID"),
    status: Optional[JobStatus] = Query(None, description="Filter by job status"),
    operation: Optional[str] = Query(
        None, description="Filter by operation"
    ),
    model: Optional[str] = Query(None, description="Filter by model"),
    priority: Optional[int] = Query(None, description="Filter by priority"),
    limit: Optional[int] = Query(
        None, description="Limit the number of results returned", ge=1
    )
):
    """
    List jobs with access control and optional filters.
    
    - Clients see only their own jobs
    - Admin can see all jobs
    - Requires either client authentication OR admin API key
    - Supports filtering by jobId, status, operation, model, and priority
      via query parameters
    - Supports limiting results with the limit parameter (e.g., limit=10
      returns only 10 items)
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication or admin API key is required"
        )
    
    try:
        service = get_job_service()
        
        jobs = service.list_jobs(
            client_id=client_id,
            is_admin=is_admin,
            job_id=jobId,
            status=status,
            operation=operation,
            model=model,
            priority=priority,
            limit=limit
        )
        
        return [JobResponse(**job) for job in jobs]
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error listing jobs", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error listing jobs", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list jobs"
        )


@router.get("/summary", response_model=JobSummaryResponse)
async def get_jobs_summary(
    request: Request,
    client_id: str = Depends(verify_client_auth),
    operation: Optional[str] = Query(
        None, description="Filter by operation"
    ),
    model: Optional[str] = Query(None, description="Filter by model"),
    id: Optional[str] = Query(
        None, description="Filter by client-provided job ID", alias="id"
    )
):
    """
    Get summary of jobs with counts by status.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Returns counts for each status (PENDING, PROCESSING, PROCESSED,
      CONSUMED, ERROR_PROCESSING, ERROR_CONSUMING, CANCELED)
    - Supports filtering by operation, model, id, and any
      clientReference field
    - For clientReference filtering, use query parameters like:
      clientReference.randomProp=hello
    - Clients can only see their own jobs
    """
    try:
        service = get_job_service()
        
        # Parse clientReference filters from query parameters
        # Look for query params that start with "clientReference."
        client_reference_filters: Dict[str, Any] = {}
        for key, value in request.query_params.items():
            if key.startswith("clientReference."):
                # Extract the field name after "clientReference."
                field_name = key[len("clientReference."):]
                client_reference_filters[field_name] = value
        
        # Convert empty dict to None if no filters
        if not client_reference_filters:
            client_reference_filters = None
        
        summary = service.get_jobs_summary(
            client_id=client_id,
            operation=operation,
            model=model,
            job_id=id,
            client_reference_filters=client_reference_filters
        )
        
        return JobSummaryResponse(**summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting job summary", error=str(e), client_id=client_id
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job summary"
        )


@router.patch(
    "/batch",
    response_model=List[JobResponse],
    status_code=http_status.HTTP_200_OK
)
async def update_jobs_batch(
    request: JobBatchUpdateRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Update multiple jobs at once.
    
    - Clients can only update their own jobs
    - Admin can update any job
    - Requires either client authentication OR admin API key
    - Validates all jobs before updating (all-or-nothing)
    - Returns a list of updated job data
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication or admin API key is required"
        )
    
    try:
        service = get_job_service()
        
        # Convert Pydantic models to dicts for service layer
        job_updates = [job.model_dump() for job in request.jobs]
        
        jobs = service.update_jobs_batch(
            client_id=client_id,
            job_updates=job_updates,
            is_admin=is_admin
        )
        
        return [JobResponse(**job) for job in jobs]
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error updating jobs batch", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating jobs batch", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update jobs batch"
        )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Get a job by ID.
    
    - Clients can only access their own jobs
    - Admin can access any job
    - Requires either client authentication OR admin API key
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication or admin API key is required"
        )
    
    try:
        service = get_job_service()
        
        job = service.get_job_by_id(
            job_id, client_id=client_id, is_admin=is_admin
        )
        
        return JobResponse(**job)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error getting job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job"
        )


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job_status(
    job_id: str,
    request: JobStatusUpdateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Update job status (clients only).
    
    - Clients can only update status field
    - Allowed transitions: PENDING→CANCELED, PROCESSED→CONSUMED,
      PROCESSED→ERROR_CONSUMING
    - Invalid transitions return 400 Bad Request
    - Clients can only update their own jobs
    """
    try:
        service = get_job_service()
        
        # Convert string to JobStatus enum
        new_status = JobStatus(request.status)
        
        job = service.update_job_status(
            job_id=job_id,
            new_status=new_status,
            client_id=client_id
        )
        
        return JobResponse(**job)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error updating job status", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "Error updating job status", error=str(e), job_id=job_id
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update job status"
        )


@router.patch("/{job_id}/full", response_model=JobResponse)
async def update_job_full(
    job_id: str,
    request: JobUpdateRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Full update of a job (workers/admin only).
    
    - Allows updating all fields
    - Used by workers to update status to PROCESSING, PROCESSED, etc.
    - Requires admin API key or client authentication (for their own
      jobs)
    - Not documented for regular clients
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key or client authentication is required"
        )
    
    try:
        service = get_job_service()
        
        # Convert status string to enum if provided
        status_enum = None
        if request.status is not None:
            status_enum = JobStatus(request.status)
        
        job = service.update_job(
            job_id=job_id,
            status=status_enum,
            operation=request.operation,
            prompts=request.prompts,
            working_prompts=request.workingPrompts,
            model=request.model,
            temperature=request.temperature,
            priority=request.priority,
            request_data=request.requestData,
            client_reference=request.clientReference,
            eval_prompt=request.evalPrompt,
            eval_model=request.evalModel,
            meta_prompt=request.metaPrompt,
            meta_model=request.metaModel,
            eval_result=request.evalResult,
            suggested_prompt_id=request.suggestedPromptId,
            client_id=client_id,
            is_admin=is_admin
        )
        
        return JobResponse(**job)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error updating job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update job"
        )


@router.delete("/batch", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_jobs_batch(
    request: JobBatchDeleteRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Delete multiple jobs at once (soft delete).
    
    - Clients can only delete their own jobs
    - Admin can delete any job
    - Requires either client authentication OR admin API key
    - Validates all jobs before deleting (all-or-nothing)
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication or admin API key is required"
        )
    
    try:
        service = get_job_service()
        
        service.delete_jobs_batch(
            client_id=client_id,
            job_ids=request.jobIds,
            is_admin=is_admin
        )
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error deleting jobs batch", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting jobs batch", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete jobs batch"
        )


@router.delete("/{job_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Delete a job (soft delete).
    
    - Clients can only delete their own jobs
    - Admin can delete any job
    - Requires either client authentication OR admin API key
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication or admin API key is required"
        )
    
    try:
        service = get_job_service()
        
        service.delete_job(job_id, client_id=client_id, is_admin=is_admin)
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error deleting job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete job"
        )

