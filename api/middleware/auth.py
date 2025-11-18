"""
Admin API key authentication middleware
"""
from fastapi import Header, HTTPException, status
from typing import Annotated, Optional
import secrets

from config import config
from api.core.logging import get_logger

logger = get_logger("api.middleware.auth")


def verify_admin_api_key(
    admin_api_key: Annotated[
        Optional[str], Header(alias="admin_api_key")
    ] = None
) -> str:
    """
    FastAPI dependency to verify admin API key from header.
    
    Args:
        admin_api_key: Admin API key from request header
        
    Returns:
        The admin API key if valid
        
    Raises:
        HTTPException: 401 if admin API key is missing or invalid
    """
    if admin_api_key is None:
        logger.warning("Admin API key missing from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key is required"
        )
    
    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(admin_api_key, config.admin_api_key):
        logger.warning("Invalid admin API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key"
        )
    
    return admin_api_key

