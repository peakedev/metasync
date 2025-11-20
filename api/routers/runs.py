"""
Run management API router
Provides CRUD operations for runs with client and admin authentication
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi import status as http_status
from typing import List, Optional, Annotated

from api.middleware.auth import verify_admin_api_key
from api.middleware.client_auth import verify_client_auth
from api.models.run_models import (
    RunCreateRequest,
    RunUpdateStatusRequest,
    RunResponse,
    RunStatus
)
from api.services.run_service import get_run_service
from api.core.logging import get_logger

logger = get_logger("api.routers.runs")

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
        return None


@router.post("", response_model=RunResponse, status_code=http_status.HTTP_201_CREATED)
async def create_run(
    request: RunCreateRequest,
    client_id: str = Depends(verify_client_auth)
):
    """
    Create a new optimization run.
    
    - Requires client authentication (client_id and client_api_key headers)
    - Validates all prompt IDs and model names exist
    - Creates the run and seeds the first job
    - Run starts in PENDING status and transitions to RUNNING
    """
    try:
        service = get_run_service()
        run = service.create_run(
            client_id=client_id,
            initial_working_prompt_id=request.initialWorkingPromptId,
            eval_prompt_id=request.evalPromptId,
            eval_model=request.evalModel,
            meta_prompt_id=request.metaPromptId,
            meta_model=request.metaModel,
            working_models=request.workingModels,
            max_iterations=request.maxIterations,
            temperature=request.temperature,
            priority=request.priority,
            request_data=request.requestData
        )
        
        return RunResponse(**run)
    except ValueError as e:
        logger.warning("Validation error creating run", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating run", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create run"
        )


@router.get("", response_model=List[RunResponse])
async def list_runs(
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth),
    status: Optional[RunStatus] = None
):
    """
    List runs with access control.
    
    - Clients see only their own runs
    - Admin can see all runs
    - Requires either client authentication OR admin API key
    - Optional status filter
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
        service = get_run_service()
        
        runs = service.list_runs(
            client_id=client_id,
            is_admin=is_admin,
            status=status
        )
        
        return [RunResponse(**run) for run in runs]
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error listing runs", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error listing runs", error=str(e))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list runs"
        )


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Get a run by ID.
    
    - Clients can only access their own runs
    - Admin can access any run
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
        service = get_run_service()
        
        run = service.get_run_by_id(
            run_id, client_id=client_id, is_admin=is_admin
        )
        
        return RunResponse(**run)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error getting run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get run"
        )


@router.patch("/{run_id}/pause", response_model=RunResponse)
async def pause_run(
    run_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Pause a running run.
    
    - Pauses the run (prevents new jobs from being created)
    - Only works if run status is RUNNING
    - Clients can only pause their own runs
    - Admin can pause any run
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
        service = get_run_service()
        
        run = service.update_run_status(
            run_id=run_id,
            action="pause",
            client_id=client_id,
            is_admin=is_admin
        )
        
        return RunResponse(**run)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error pausing run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error pausing run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to pause run"
        )


@router.patch("/{run_id}/resume", response_model=RunResponse)
async def resume_run(
    run_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Resume a paused run.
    
    - Resumes the run (allows new jobs to be created)
    - Only works if run status is PAUSED
    - Clients can only resume their own runs
    - Admin can resume any run
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
        service = get_run_service()
        
        run = service.update_run_status(
            run_id=run_id,
            action="resume",
            client_id=client_id,
            is_admin=is_admin
        )
        
        return RunResponse(**run)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error resuming run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error resuming run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resume run"
        )


@router.patch("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Cancel a run.
    
    - Cancels the run (stops all future jobs)
    - Only works if run is not already COMPLETED, FAILED, or CANCELLED
    - Clients can only cancel their own runs
    - Admin can cancel any run
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
        service = get_run_service()
        
        run = service.update_run_status(
            run_id=run_id,
            action="cancel",
            client_id=client_id,
            is_admin=is_admin
        )
        
        return RunResponse(**run)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error cancelling run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error cancelling run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel run"
        )


@router.delete("/{run_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Delete a run (soft delete).
    
    - Clients can only delete their own runs
    - Admin can delete any run
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
        service = get_run_service()
        
        service.delete_run(run_id, client_id=client_id, is_admin=is_admin)
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error deleting run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting run", error=str(e), run_id=run_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete run"
        )

