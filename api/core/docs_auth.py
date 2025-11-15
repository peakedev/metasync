"""
Documentation authentication utilities for HTTP Basic auth
"""

import base64
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Optional
from config import config

# Create HTTP Basic security scheme with explicit realm
security = HTTPBasic(realm="Documentation")

def verify_docs_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Verify HTTP Basic credentials for documentation endpoints
    
    Args:
        credentials: HTTP Basic credentials from Authorization header
        
    Returns:
        str: The verified username
        
    Raises:
        HTTPException: If credentials are missing or invalid
    """
    # Get credentials from config
    expected_username = config.docs_user
    expected_password = config.docs_secret
    
    if not expected_username:
        raise HTTPException(
            status_code=500, 
            detail="Documentation authentication not configured"
        )
    
    if not expected_password:
        raise HTTPException(
            status_code=500, 
            detail="Documentation secret not configured"
        )
    
    # Check credentials
    if credentials.username != expected_username or credentials.password != expected_password:
        raise HTTPException(
            status_code=401,
            detail="Invalid documentation credentials",
            headers={"WWW-Authenticate": "Basic realm=\"Documentation\""},
        )
    
    return credentials.username

# Create a dependency that can be used for docs endpoints
docs_auth_dependency = verify_docs_credentials

