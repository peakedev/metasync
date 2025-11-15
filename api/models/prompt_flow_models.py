"""
Pydantic models for prompt flow management API
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class PromptFlowCreateRequest(BaseModel):
    """Request model for creating a new prompt flow"""
    name: str = Field(..., description="Prompt flow name", min_length=1)
    prompt_ids: List[str] = Field(..., description="Array of prompt IDs", min_items=0)
    isPublic: bool = Field(False, description="Whether the prompt flow is public (requires admin API key)")


class PromptFlowUpdateRequest(BaseModel):
    """Request model for updating a prompt flow"""
    name: Optional[str] = Field(None, description="Prompt flow name", min_length=1)
    prompt_ids: Optional[List[str]] = Field(None, description="Array of prompt IDs")
    isPublic: Optional[bool] = Field(None, description="Whether the prompt flow is public")


class PromptFlowResponse(BaseModel):
    """Response model for prompt flow data"""
    flow_id: str = Field(..., description="Unique prompt flow identifier (MongoDB _id)")
    name: str = Field(..., description="Prompt flow name")
    prompt_ids: List[str] = Field(..., description="Array of prompt IDs")
    client_id: Optional[str] = Field(None, description="Client ID (None for public flows)")
    isPublic: bool = Field(..., description="Whether the prompt flow is public")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "flow_id": "507f1f77bcf86cd799439011",
                "name": "main-flow",
                "prompt_ids": ["507f1f77bcf86cd799439012", "507f1f77bcf86cd799439013"],
                "client_id": "123e4567-e89b-12d3-a456-426614174000",
                "isPublic": False,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }

