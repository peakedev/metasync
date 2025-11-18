"""
Prompt management API router
Provides CRUD operations for prompts with client and admin authentication
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Header
from typing import List, Optional, Union, Annotated

from api.middleware.auth import verify_admin_api_key
from api.middleware.client_auth import verify_client_auth
from api.models.prompt_models import (
    PromptCreateRequest,
    PromptUpdateRequest,
    PromptResponse,
    PromptStatus
)
from api.services.prompt_service import get_prompt_service
from api.core.logging import get_logger

logger = get_logger("api.routers.prompts")

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


@router.post("", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    request: PromptCreateRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Create a new prompt.
    
    - Public prompts (isPublic: true) can only be created with Admin
      API Key
    - Private prompts (isPublic: false) can be created by any
      authenticated client
    - Version is auto-incremented if not provided
    - Returns the created prompt data
    """
    try:
        service = get_prompt_service()
        
        # Validate: public prompts require admin API key
        if request.isPublic:
            if admin_api_key is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Admin API key is required to create public prompts"
                    )
                )
            # For public prompts, client_id is None
            created_prompt = service.create_prompt(
                name=request.name,
                type_name=request.type,
                status=request.status,
                prompt_text=request.prompt,
                is_public=True,
                client_id=None,
                version=request.version
            )
        else:
            # For private prompts, client_id is required (from auth)
            if client_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Client authentication is required to create "
                        "private prompts"
                    )
                )
            created_prompt = service.create_prompt(
                name=request.name,
                type_name=request.type,
                status=request.status,
                prompt_text=request.prompt,
                is_public=False,
                client_id=client_id,
                version=request.version
            )
        
        return PromptResponse(**created_prompt)
    except ValueError as e:
        logger.warning("Validation error creating prompt", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating prompt", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create prompt"
        )


@router.get("", response_model=List[PromptResponse])
async def list_prompts(
    client_id: str = Depends(verify_client_auth),
    name: Optional[str] = Query(None, description="Filter by prompt name"),
    type: Optional[str] = Query(None, description="Filter by prompt type"),
    status_filter: Optional[PromptStatus] = Query(
        None, alias="status", description="Filter by prompt status"
    ),
    version: Optional[Union[str, int]] = Query(
        None, description="Filter by prompt version"
    )
):
    """
    List prompts with optional filtering.
    
    Returns both public prompts and the authenticated client's private
    prompts. Filters can be combined (AND logic).
    """
    try:
        service = get_prompt_service()
        prompts = service.list_prompts(
            client_id=client_id,
            name=name,
            type_name=type,
            status=status_filter,
            version=version
        )
        
        return [PromptResponse(**prompt) for prompt in prompts]
    except Exception as e:
        logger.error(
            "Error listing prompts",
            error=str(e),
            exc_info=True,
            client_id=client_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list prompts: {str(e)}"
        )


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: str,
    client_id: str = Depends(verify_client_auth)
):
    """
    Get a prompt by ID.
    
    Returns the prompt if it's public or belongs to the authenticated
    client.
    """
    try:
        service = get_prompt_service()
        prompt = service.get_prompt_by_id(prompt_id, client_id)
        
        return PromptResponse(**prompt)
    except ValueError as e:
        logger.warning("Error getting prompt", error=str(e), prompt_id=prompt_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error getting prompt", error=str(e), prompt_id=prompt_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get prompt"
        )


@router.patch("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: str,
    request: PromptUpdateRequest,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Update a prompt.
    
    - Public prompts can only be updated by admin
    - Private prompts can only be updated by the owning client
    - client_id updates are admin-only and require validation
    - Returns the updated prompt data
    """
    try:
        service = get_prompt_service()
        
        # Check if clientId update was requested (admin only)
        # Use model_dump to check if clientId was explicitly provided in
        # the request
        request_dict = request.model_dump(exclude_unset=True)
        update_client_id = 'clientId' in request_dict
        
        if update_client_id and admin_api_key is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin API key is required to update clientId"
            )
        
        # First, get the prompt to check if it's public or private
        # Admins can access any prompt
        is_admin_update = admin_api_key is not None
        existing_prompt = service.get_prompt_by_id(
            prompt_id, client_id, is_admin=is_admin_update
        )
        
        # Check access: public prompts require admin, private prompts require owner
        # Admins can update any prompt
        if existing_prompt.get("isPublic", False):
            if not is_admin_update:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Admin API key is required to update public prompts"
                    )
                )
            # For public prompts, pass None as client_id (unless updating client_id)
            updated_prompt = service.update_prompt(
                prompt_id=prompt_id,
                client_id=None,
                version=request.version,
                status=request.status,
                prompt_text=request.prompt,
                is_public=request.isPublic,
                new_client_id=request.clientId if update_client_id else None,
                is_admin=is_admin_update,
                update_client_id=update_client_id
            )
        else:
            # For private prompts, client_id is required (unless admin is
            # updating)
            if not is_admin_update and client_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Client authentication is required to update "
                        "private prompts"
                    )
                )
            # Admins can update any prompt
            # Otherwise, verify the client owns the prompt
            if (
                not is_admin_update
                and existing_prompt.get("clientId") != client_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Access denied: prompt not found or insufficient "
                        "permissions"
                    )
                )
            updated_prompt = service.update_prompt(
                prompt_id=prompt_id,
                client_id=client_id if not update_client_id else None,
                version=request.version,
                status=request.status,
                prompt_text=request.prompt,
                is_public=request.isPublic,
                new_client_id=request.clientId if update_client_id else None,
                is_admin=is_admin_update,
                update_client_id=update_client_id
            )
        
        return PromptResponse(**updated_prompt)
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Validation error updating prompt", error=str(e), prompt_id=prompt_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating prompt", error=str(e), prompt_id=prompt_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update prompt"
        )


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: str,
    client_id: Optional[str] = Depends(optional_client_auth),
    admin_api_key: Optional[str] = Depends(optional_admin_auth)
):
    """
    Delete a prompt (soft delete).
    
    - Public prompts can only be deleted by admin
    - Private prompts can only be deleted by the owning client
    """
    try:
        service = get_prompt_service()
        
        # First, get the prompt to check if it's public or private
        existing_prompt = service.get_prompt_by_id(prompt_id, client_id)
        
        # Check access: public prompts require admin, private prompts require owner
        if existing_prompt.get("isPublic", False):
            if admin_api_key is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Admin API key is required to delete public prompts"
                    )
                )
            # For public prompts, pass None as client_id
            service.delete_prompt(prompt_id, client_id=None)
        else:
            # For private prompts, client_id is required
            if client_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Client authentication is required to delete "
                        "private prompts"
                    )
                )
            service.delete_prompt(prompt_id, client_id=client_id)
        
        return None
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Error deleting prompt", error=str(e), prompt_id=prompt_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting prompt", error=str(e), prompt_id=prompt_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete prompt"
        )

