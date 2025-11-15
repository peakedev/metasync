"""
Pydantic models for client management API
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClientCreateRequest(BaseModel):
    """Request model for creating a new client"""
    name: str = Field(..., description="Client name", min_length=1, max_length=255)


class ClientUpdateRequest(BaseModel):
    """Request model for updating a client"""
    name: Optional[str] = Field(None, description="Client name", min_length=1, max_length=255)
    enabled: Optional[bool] = Field(None, description="Enable/disable client")


class ClientResponse(BaseModel):
    """Response model for client data (without API key)"""
    client_id: str = Field(..., description="Unique client identifier")
    name: str = Field(..., description="Client name")
    enabled: bool = Field(..., description="Whether client is enabled")
    created_at: str = Field(..., description="Creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Example Client",
                "enabled": True,
                "created_at": "2024-01-01T00:00:00"
            }
        }


class ClientCreateResponse(BaseModel):
    """Response model for client creation (includes API key once)"""
    client_id: str = Field(..., description="Unique client identifier")
    name: str = Field(..., description="Client name")
    enabled: bool = Field(..., description="Whether client is enabled")
    created_at: str = Field(..., description="Creation timestamp")
    api_key: str = Field(..., description="API key (only returned once during creation)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Example Client",
                "enabled": True,
                "created_at": "2024-01-01T00:00:00",
                "api_key": "a1b2c3d4e5f6..."
            }
        }


class ClientRotateKeyResponse(BaseModel):
    """Response model for key rotation (includes new API key once)"""
    client_id: str = Field(..., description="Unique client identifier")
    api_key: str = Field(..., description="New API key (only returned once during rotation)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "123e4567-e89b-12d3-a456-426614174000",
                "api_key": "a1b2c3d4e5f6..."
            }
        }


