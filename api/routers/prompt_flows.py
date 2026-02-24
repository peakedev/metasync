"""
Prompt flow management API router
Provides CRUD operations for prompt flows with client and admin authentication
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Header
from typing import List, Optional, Union, Annotated

from api.middleware.auth import verify_admin_api_key
from api.middleware.client_auth import verify_client_auth
from api.models.prompt_flow_models import (
    PromptFlowCreateRequest,
    PromptFlowUpdateRequest,
    PromptFlowResponse
)
from api.services.prompt_flow_service import get_prompt_flow_service
from api.core.logging import get_logger

logger = get_logger("api.routers.prompt_flows")

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


@router.post(
    "",
    response_model=PromptFlowResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_prompt_flow(
    request: PromptFlowCreateRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Create a new prompt flow.
    
    - Public flows (isPublic: true) can only be created with Admin
      API Key
    - Private flows (isPublic: false) can be created by any
      authenticated client
    - Returns the created prompt flow data
    """
    try:
        service = get_prompt_flow_service()
        
        # Validate: public flows require admin API key
        if request.isPublic:
            if admin_api_key is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Admin API key is required to create public prompt "
                        "flows"
                    )
                )
            # For public flows, client_id is None
            created_flow = service.create_prompt_flow(
                name=request.name,
                prompt_ids=request.promptIds,
                is_public=True,
                client_id=None
            )
        else:
            # For private flows, client_id is required (from auth)
            if client_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Client authentication is required to create private "
                        "prompt flows"
                    )
                )
            created_flow = service.create_prompt_flow(
                name=request.name,
                prompt_ids=request.promptIds,
                is_public=False,
                client_id=client_id
            )
        
        return PromptFlowResponse(**created_flow)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error creating prompt flow", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating prompt flow", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create prompt flow"
        )


@router.get("", response_model=List[PromptFlowResponse])
async def list_prompt_flows(
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    List prompt flows with access control.
    
    - Clients see their own private flows and all public flows
    - Admin can see all flows
    - Requires either client authentication OR admin API key
    """
    try:
        service = get_prompt_flow_service()
        
        # Determine if admin
        is_admin = admin_api_key is not None
        
        # If not admin, client_id is required
        if not is_admin and client_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client authentication or admin API key is required"
            )
        
        flows = service.list_prompt_flows(client_id=client_id, is_admin=is_admin)
        
        return [PromptFlowResponse(**flow) for flow in flows]
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error listing prompt flows", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "Error listing prompt flows", error=str(e), exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list prompt flows: {str(e)}"
        )


@router.get("/{flow_id}", response_model=PromptFlowResponse)
async def get_prompt_flow(
    flow_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Get a prompt flow by ID.
    
    - Clients can access their own private flows and all public flows
    - Admin can access any flow
    - Requires either client authentication OR admin API key
    """
    try:
        service = get_prompt_flow_service()
        
        # Determine if admin
        is_admin = admin_api_key is not None
        
        # If not admin, client_id is required
        if not is_admin and client_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client authentication or admin API key is required"
            )
        
        flow = service.get_prompt_flow_by_id(
            flow_id, client_id=client_id, is_admin=is_admin
        )
        
        return PromptFlowResponse(**flow)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error getting prompt flow", error=str(e), flow_id=flow_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting prompt flow", error=str(e), flow_id=flow_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get prompt flow"
        )


@router.patch("/{flow_id}", response_model=PromptFlowResponse)
async def update_prompt_flow(
    flow_id: str,
    request: PromptFlowUpdateRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Update a prompt flow.
    
    - Public flows can only be updated by admin
    - Private flows can only be updated by the owning client
    - Returns the updated prompt flow data
    """
    try:
        service = get_prompt_flow_service()
        
        # Determine if admin
        is_admin = admin_api_key is not None
        
        # First, get the flow to check if it's public or private
        existing_flow = service.get_prompt_flow_by_id(flow_id, client_id, is_admin)
        
        # Check access: public flows require admin, private flows
        # require owner. Admins can update any flow.
        if existing_flow.get("isPublic", False):
            if not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Admin API key is required to update "
                        "public prompt flows"
                    )
                )
            updated_flow = service.update_prompt_flow(
                flow_id=flow_id,
                client_id=None,
                name=request.name,
                prompt_ids=request.promptIds,
                is_public=request.isPublic,
                is_admin=True
            )
        else:
            # For private flows, require client auth or admin
            if not is_admin and client_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Client authentication is required to "
                        "update private prompt flows"
                    )
                )
            updated_flow = service.update_prompt_flow(
                flow_id=flow_id,
                client_id=client_id,
                name=request.name,
                prompt_ids=request.promptIds,
                is_public=request.isPublic,
                is_admin=is_admin
            )
        
        return PromptFlowResponse(**updated_flow)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(
            "Validation error updating prompt flow",
            error=str(e),
            flow_id=flow_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating prompt flow", error=str(e), flow_id=flow_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update prompt flow"
        )


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_flow(
    flow_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Delete a prompt flow (soft delete).
    
    - Public flows can only be deleted by admin
    - Private flows can only be deleted by the owning client
    """
    try:
        service = get_prompt_flow_service()
        
        # Determine if admin
        is_admin = admin_api_key is not None
        
        # First, get the flow to check if it's public or private
        existing_flow = service.get_prompt_flow_by_id(flow_id, client_id, is_admin)
        
        # Check access: admins can delete any flow, public flows
        # require admin, private flows require owner
        if is_admin:
            service.delete_prompt_flow(
                flow_id, client_id=None, is_admin=True
            )
        elif existing_flow.get("isPublic", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Admin API key is required to delete "
                    "public prompt flows"
                )
            )
        else:
            if client_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Client authentication is required to "
                        "delete private prompt flows"
                    )
                )
            service.delete_prompt_flow(
                flow_id, client_id=client_id
            )
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(
            "Error deleting prompt flow", error=str(e), flow_id=flow_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting prompt flow", error=str(e), flow_id=flow_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete prompt flow"
        )

