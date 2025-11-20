"""
Worker management API router
Provides CRUD operations for workers with client and admin authentication
"""
from fastapi import APIRouter, HTTPException, status, Depends, Header, Query, Request
from typing import List, Optional, Annotated, Dict, Any

from api.middleware.auth import verify_admin_api_key
from api.middleware.client_auth import verify_client_auth
from api.models.worker_models import (
    WorkerCreateRequest,
    WorkerUpdateRequest,
    WorkerResponse,
    WorkerStatus,
    WorkerOverviewResponse,
    WorkerSummaryResponse
)
from api.services.worker_service import get_worker_service
from api.services.worker_manager import get_worker_manager
from api.core.logging import get_logger

logger = get_logger("api.routers.workers")

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
    except HTTPException:
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
    except HTTPException:
        return None


@router.post("", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
async def create_worker(
    request: WorkerCreateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Create a new worker.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Worker is created in stopped state
    - Returns the created worker data
    """
    try:
        service = get_worker_service()
        worker = service.create_worker(
            client_id=client_id,
            worker_id=request.workerId,
            config=request.config
        )
        
        return WorkerResponse(**worker)
    except ValueError as e:
        logger.warning("Validation error creating worker", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating worker", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create worker"
        )


@router.get("", response_model=List[WorkerResponse])
async def list_workers(
    client_id: str = Depends(verify_client_auth)
):
    """
    List all workers for the authenticated client.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Clients can only see their own workers
    """
    try:
        service = get_worker_service()
        workers = service.list_workers(client_id=client_id)
        
        return [WorkerResponse(**worker) for worker in workers]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing workers", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list workers"
        )


@router.get("/summary", response_model=WorkerSummaryResponse)
async def get_workers_summary(
    request: Request,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth),
    modelFilter: Optional[str] = Query(None, description="Filter by config.modelFilter"),
    operationFilter: Optional[str] = Query(None, description="Filter by config.operationFilter")
):
    """
    Get summary of workers with counts and IDs by status.
    
    - Supports both client and admin authentication
    - Clients can only see their own workers
    - Admins can see all workers
    - Returns counts for each status (running, stopped, error)
    - Returns lists of worker IDs for each status
    - Supports filtering by modelFilter, operationFilter, and any
      config.clientReferenceFilters field
    - For clientReferenceFilters filtering, use query parameters like:
      clientReference.randomProp=hello
    """
    # Determine if admin
    is_admin = admin_api_key is not None
    
    # If not admin, client_id is required
    if not is_admin and client_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication or admin API key is required"
        )
    
    try:
        service = get_worker_service()
        
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
        
        summary = service.get_workers_summary(
            client_id=client_id,
            is_admin=is_admin,
            model_filter=modelFilter,
            operation_filter=operationFilter,
            client_reference_filters=client_reference_filters
        )
        
        return WorkerSummaryResponse(**summary)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error getting workers summary", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "Error getting workers summary", error=str(e), client_id=client_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get workers summary"
        )


@router.get("/{worker_id}", response_model=WorkerResponse)
async def get_worker(
    worker_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Get a worker by ID.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Clients can only access their own workers
    """
    try:
        service = get_worker_service()
        worker = service.get_worker_by_id(worker_id, client_id=client_id)
        
        return WorkerResponse(**worker)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error getting worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get worker"
        )


@router.patch("/{worker_id}", response_model=WorkerResponse)
async def update_worker(
    worker_id: str,
    request: WorkerUpdateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Update worker configuration.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Worker must be stopped before updating configuration
    - Clients can only update their own workers
    """
    try:
        service = get_worker_service()
        manager = get_worker_manager()
        
        # Check if worker is running
        worker = service.get_worker_by_id(worker_id, client_id=client_id)
        if worker.get("status") == WorkerStatus.RUNNING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot update a running worker. Stop the worker first."
                )
            )
        
        # Update worker configuration
        if request.config is not None:
            worker = service.update_worker(
                worker_id=worker_id,
                config=request.config,
                client_id=client_id
            )
        
        return WorkerResponse(**worker)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(
            "Validation error updating worker",
            error=str(e),
            worker_id=worker_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update worker"
        )


@router.post("/{worker_id}/start", response_model=WorkerResponse)
async def start_worker(
    worker_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Start a worker.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Worker must be in stopped state
    - Clients can only start their own workers
    """
    try:
        service = get_worker_service()
        manager = get_worker_manager()
        
        # Verify worker exists and belongs to client
        worker = service.get_worker_by_id(worker_id, client_id=client_id)
        
        # Check if worker is already running
        if worker.get("status") == WorkerStatus.RUNNING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Worker is already running"
            )
        
        # Start the worker
        try:
            success = manager.start_worker(worker_id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to start worker"
                )
        except Exception as e:
            logger.error(
                "Error in start_worker endpoint",
                error=str(e),
                worker_id=worker_id,
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start worker: {str(e)}"
            )
        
        # Get updated worker status from manager (avoids redundant DB call)
        worker = manager.get_worker_status(worker_id)
        if not worker:
            # Fallback to service if manager doesn't have it
            worker = service.get_worker_by_id(worker_id, client_id=client_id)
        
        return WorkerResponse(**worker)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error starting worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error starting worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start worker"
        )


@router.post("/{worker_id}/stop", response_model=WorkerResponse)
async def stop_worker(
    worker_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Stop a worker.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Worker must be in running state
    - Clients can only stop their own workers
    """
    try:
        service = get_worker_service()
        manager = get_worker_manager()
        
        # Verify worker exists and belongs to client
        worker = service.get_worker_by_id(worker_id, client_id=client_id)
        
        # Check if worker is already stopped
        if worker.get("status") == WorkerStatus.STOPPED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Worker is already stopped"
            )
        
        # Stop the worker
        success = manager.stop_worker(worker_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to stop worker"
            )
        
        # Get updated worker status from manager (avoids redundant DB call)
        worker = manager.get_worker_status(worker_id)
        if not worker:
            # Fallback to service if manager doesn't have it
            worker = service.get_worker_by_id(worker_id, client_id=client_id)
        
        return WorkerResponse(**worker)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error stopping worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error stopping worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop worker"
        )


@router.delete("/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker(
    worker_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Delete a worker.
    
    - Requires client authentication (client_id and client_api_key
      headers)
    - Worker must be stopped before deletion
    - Clients can only delete their own workers
    """
    try:
        service = get_worker_service()
        manager = get_worker_manager()
        
        # Verify worker exists and belongs to client
        worker = service.get_worker_by_id(worker_id, client_id=client_id)
        
        # Check if worker is running
        if worker.get("status") == WorkerStatus.RUNNING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot delete a running worker. Stop the worker first."
                )
            )
        
        # Stop worker if it's somehow still running in manager
        manager.stop_worker(worker_id)
        
        # Delete the worker
        service.delete_worker(worker_id, client_id=client_id)
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error deleting worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting worker", error=str(e), worker_id=worker_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete worker"
        )
