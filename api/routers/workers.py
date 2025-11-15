"""
Worker management API router
Provides CRUD operations for workers with client and admin authentication
"""
from fastapi import APIRouter, HTTPException, status, Depends, Header, Query, Request
from typing import List, Optional, Annotated

from api.middleware.auth import verify_admin_api_key
from api.middleware.client_auth import verify_client_auth
from api.models.worker_models import (
    WorkerCreateRequest,
    WorkerUpdateRequest,
    WorkerResponse,
    WorkerStatus,
    WorkerOverviewResponse
)
from api.services.worker_service import get_worker_service
from api.services.worker_manager import get_worker_manager
from api.core.logging import get_logger

logger = get_logger("api.routers.workers")

router = APIRouter()


def optional_client_auth(
    client_id: Annotated[Optional[str], Header(alias="client_id")] = None,
    client_api_key: Annotated[Optional[str], Header(alias="client_api_key")] = None
) -> Optional[str]:
    """Optional client authentication - returns client_id if valid, None otherwise"""
    if client_id is None or client_api_key is None:
        return None
    try:
        return verify_client_auth(client_id, client_api_key)
    except HTTPException:
        return None


def optional_admin_auth(
    admin_api_key: Annotated[Optional[str], Header(alias="admin_api_key")] = None
) -> Optional[str]:
    """Optional admin authentication - returns admin_api_key if valid, None otherwise"""
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
    
    - Requires client authentication (client_id and client_api_key headers)
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
    
    - Requires client authentication (client_id and client_api_key headers)
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


@router.get("/{worker_id}", response_model=WorkerResponse)
async def get_worker(
    worker_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Get a worker by ID.
    
    - Requires client authentication (client_id and client_api_key headers)
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
    
    - Requires client authentication (client_id and client_api_key headers)
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
                detail="Cannot update a running worker. Stop the worker first."
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
        logger.warning("Validation error updating worker", error=str(e), worker_id=worker_id)
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
    
    - Requires client authentication (client_id and client_api_key headers)
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
            logger.error("Error in start_worker endpoint", error=str(e), worker_id=worker_id, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start worker: {str(e)}"
            )
        
        # Get updated worker status
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
    
    - Requires client authentication (client_id and client_api_key headers)
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
        
        # Get updated worker status
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
    
    - Requires client authentication (client_id and client_api_key headers)
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
                detail="Cannot delete a running worker. Stop the worker first."
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


@router.get("/admin/overview", response_model=WorkerOverviewResponse)
async def get_workers_overview(
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Get overview of all workers across all clients (admin only).
    
    - Requires admin API key (admin_api_key header)
    - Returns summary statistics and list of all workers
    """
    try:
        manager = get_worker_manager()
        workers = manager.list_workers()
        
        # Calculate statistics
        total_workers = len(workers)
        running_workers = sum(1 for w in workers if w.get("status") == WorkerStatus.RUNNING.value)
        stopped_workers = sum(1 for w in workers if w.get("status") == WorkerStatus.STOPPED.value)
        error_workers = sum(1 for w in workers if w.get("status") == WorkerStatus.ERROR.value)
        
        # Group by client
        workers_by_client: dict = {}
        for worker in workers:
            client_id = worker.get("clientId")
            if client_id not in workers_by_client:
                workers_by_client[client_id] = {"running": 0, "stopped": 0, "error": 0}
            
            status = worker.get("status")
            if status == WorkerStatus.RUNNING.value:
                workers_by_client[client_id]["running"] += 1
            elif status == WorkerStatus.STOPPED.value:
                workers_by_client[client_id]["stopped"] += 1
            elif status == WorkerStatus.ERROR.value:
                workers_by_client[client_id]["error"] += 1
        
        return WorkerOverviewResponse(
            total_workers=total_workers,
            running_workers=running_workers,
            stopped_workers=stopped_workers,
            error_workers=error_workers,
            workers_by_client=workers_by_client,
            workers=[WorkerResponse(**worker) for worker in workers]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting workers overview", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get workers overview"
        )

