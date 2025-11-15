"""
Pydantic models for prompt management API
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Union
from enum import Enum


class PromptStatus(str, Enum):
    """Status enum for prompts"""
    PUBLISHED = "PUBLISHED"
    DRAFT = "DRAFT"
    ARCHIVE = "ARCHIVE"


class PromptCreateRequest(BaseModel):
    """Request model for creating a new prompt"""
    name: str = Field(..., description="Prompt name", min_length=1)
    version: Optional[Union[str, int]] = Field(None, description="Prompt version (optional, auto-incremented if not provided)")
    type: str = Field(..., description="Prompt type", min_length=1)
    status: PromptStatus = Field(..., description="Prompt status")
    prompt: str = Field(..., description="The actual prompt text", min_length=1)
    isPublic: bool = Field(..., description="Whether the prompt is public (requires admin API key)")


class PromptUpdateRequest(BaseModel):
    """Request model for updating a prompt"""
    version: Optional[Union[str, int]] = Field(None, description="Prompt version")
    status: Optional[PromptStatus] = Field(None, description="Prompt status")
    prompt: Optional[str] = Field(None, description="The actual prompt text")
    isPublic: Optional[bool] = Field(None, description="Whether the prompt is public")


class PromptResponse(BaseModel):
    """Response model for prompt data"""
    prompt_id: str = Field(..., description="Unique prompt identifier (MongoDB _id)")
    name: str = Field(..., description="Prompt name")
    version: Union[str, int] = Field(..., description="Prompt version")
    type: str = Field(..., description="Prompt type")
    status: PromptStatus = Field(..., description="Prompt status")
    prompt: str = Field(..., description="The actual prompt text")
    client_id: Optional[str] = Field(None, description="Client ID (None for public prompts)")
    isPublic: bool = Field(..., description="Whether the prompt is public")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "prompt_id": "507f1f77bcf86cd799439011",
                "name": "main",
                "version": 1,
                "type": "system",
                "status": "PUBLISHED",
                "prompt": "You are a helpful assistant.",
                "client_id": "123e4567-e89b-12d3-a456-426614174000",
                "isPublic": False,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }

