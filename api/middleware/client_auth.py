"""
Client API key authentication middleware
"""
from fastapi import Header, HTTPException, status
from typing import Annotated, Optional

from api.services.client_service import get_client_service
from api.core.logging import get_logger

logger = get_logger("api.middleware.client_auth")


def verify_client_auth(
    client_id: Annotated[Optional[str], Header(alias="client_id")] = None,
    client_api_key: Annotated[
        Optional[str], Header(alias="client_api_key")
    ] = None
) -> str:
    """
    FastAPI dependency to verify client API key from headers.
    
    Args:
        client_id: Client ID from request header
        client_api_key: Client API key from request header
        
    Returns:
        The client_id if authentication is successful
        
    Raises:
        HTTPException: 401 if client credentials are missing or invalid
    """
    if client_id is None:
        logger.warning("Client ID missing from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client ID is required"
        )
    
    if client_api_key is None:
        logger.warning(
            "Client API key missing from request", client_id=client_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client API key is required"
        )
    
    # Get client service and verify credentials
    service = get_client_service()
    client = service.get_client_for_auth(client_id)
    
    if not client:
        logger.warning("Client not found or disabled", client_id=client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials"
        )
    
    # Verify API key
    is_valid = service.verify_api_key(
        provided_key=client_api_key,
        salt=client["salt"],
        stored_hash=client["hash"],
        pepper=service.pepper
    )
    
    if not is_valid:
        logger.warning("Invalid client API key", client_id=client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials"
        )
    
    logger.info(
        "Client authenticated successfully", client_id=client_id
    )
    return client_id

