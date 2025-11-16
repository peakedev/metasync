"""
Pydantic models for client management API
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
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
    clientId: str = Field(..., description="Unique client identifier")
    name: str = Field(..., description="Client name")
    enabled: bool = Field(..., description="Whether client is enabled")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, and other relevant metadata")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Example Client",
                "enabled": True,
                "_metadata": {
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": "2024-01-01T00:00:00"
                }
            }
        }
    )


class ClientCreateResponse(BaseModel):
    """Response model for client creation (includes API key once)"""
    clientId: str = Field(..., description="Unique client identifier")
    name: str = Field(..., description="Client name")
    enabled: bool = Field(..., description="Whether client is enabled")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, and other relevant metadata")
    api_key: str = Field(..., description="API key (only returned once during creation)")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Example Client",
                "enabled": True,
                "_metadata": {
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": "2024-01-01T00:00:00"
                },
                "api_key": "a1b2c3d4e5f6..."
            }
        }
    )


class ClientRotateKeyResponse(BaseModel):
    """Response model for key rotation (includes new API key once)"""
    clientId: str = Field(..., description="Unique client identifier")
    api_key: str = Field(..., description="New API key (only returned once during rotation)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "api_key": "a1b2c3d4e5f6..."
            }
        }
    )



