"""
Client management API router
Provides CRUD operations for clients with admin authentication
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from api.middleware.auth import verify_admin_api_key
from api.models.client_models import (
    ClientCreateRequest,
    ClientUpdateRequest,
    ClientResponse,
    ClientCreateResponse,
    ClientRotateKeyResponse
)
from api.services.client_service import get_client_service
from api.core.logging import get_logger

logger = get_logger("api.routers.clients")

router = APIRouter()


@router.post("", response_model=ClientCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    request: ClientCreateRequest,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Create a new client.
    
    Returns the client data along with the API key (only returned once).
    """
    try:
        service = get_client_service()
        client_data, api_key = service.create_client(request.name)
        
        return ClientCreateResponse(
            clientId=client_data["clientId"],
            name=client_data["name"],
            enabled=client_data["enabled"],
            _metadata=client_data["_metadata"],
            api_key=api_key
        )
    except Exception as e:
        logger.error("Error creating client", error=str(e), name=request.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client"
        )


@router.get("", response_model=List[ClientResponse])
async def list_clients(
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    List all clients.
    
    Returns a list of all clients (excluding API keys).
    """
    try:
        service = get_client_service()
        clients = service.list_clients()
        
        return [
            ClientResponse(
                clientId=client["clientId"],
                name=client["name"],
                enabled=client["enabled"],
                _metadata=client["_metadata"]
            )
            for client in clients
        ]
    except Exception as e:
        logger.error("Error listing clients", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list clients"
        )


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Get a client by ID.
    
    Returns the client data (excluding API key).
    """
    try:
        service = get_client_service()
        client = service.get_client(client_id)
        
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client not found: {client_id}"
            )
        
        return ClientResponse(
            clientId=client["clientId"],
            name=client["name"],
            enabled=client["enabled"],
            _metadata=client["_metadata"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting client", error=str(e), client_id=client_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get client"
        )


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    request: ClientUpdateRequest,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Update a client's name and/or enabled status.
    
    Returns the updated client data.
    """
    try:
        service = get_client_service()
        success = service.update_client(
            client_id,
            name=request.name,
            enabled=request.enabled
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client not found: {client_id}"
            )
        
        # Get updated client
        client = service.get_client(client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve updated client"
            )
        
        return ClientResponse(
            clientId=client["clientId"],
            name=client["name"],
            enabled=client["enabled"],
            _metadata=client["_metadata"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating client", error=str(e), client_id=client_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update client"
        )


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: str,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Delete a client (soft delete).
    """
    try:
        service = get_client_service()
        success = service.delete_client(client_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client not found: {client_id}"
            )
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting client", error=str(e), client_id=client_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete client"
        )


@router.post("/{client_id}/toggle", response_model=ClientResponse)
async def toggle_client_enabled(
    client_id: str,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Toggle the enabled status of a client.
    
    Returns the updated client data.
    """
    try:
        service = get_client_service()
        new_enabled = service.toggle_client_enabled(client_id)
        
        if new_enabled is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client not found: {client_id}"
            )
        
        # Get updated client
        client = service.get_client(client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve updated client"
            )
        
        return ClientResponse(
            clientId=client["clientId"],
            name=client["name"],
            enabled=client["enabled"],
            _metadata=client["_metadata"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error toggling client enabled status",
            error=str(e),
            client_id=client_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle client enabled status"
        )


@router.post(
    "/{client_id}/rotate-key",
    response_model=ClientRotateKeyResponse,
    status_code=status.HTTP_200_OK
)
async def rotate_client_key(
    client_id: str,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Rotate a client's API key.
    
    Generates a new random salt and API key, updates the hash in
    the database. Returns the new API key once (only returned during
    this call).
    """
    try:
        service = get_client_service()
        rotated_client_id, new_api_key = service.rotate_client_key(client_id)
        
        if rotated_client_id is None or new_api_key is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client not found: {client_id}"
            )
        
        return ClientRotateKeyResponse(
            clientId=rotated_client_id,
            api_key=new_api_key
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error rotating client key", error=str(e), client_id=client_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate client key"
        )



