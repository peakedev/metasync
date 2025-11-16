"""
Pydantic models for prompt flow management API
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any


class PromptFlowCreateRequest(BaseModel):
    """Request model for creating a new prompt flow"""
    name: str = Field(..., description="Prompt flow name", min_length=1)
    promptIds: List[str] = Field(..., description="Array of prompt IDs", min_items=0)
    isPublic: bool = Field(False, description="Whether the prompt flow is public (requires admin API key)")


class PromptFlowUpdateRequest(BaseModel):
    """Request model for updating a prompt flow"""
    name: Optional[str] = Field(None, description="Prompt flow name", min_length=1)
    promptIds: Optional[List[str]] = Field(None, description="Array of prompt IDs")
    isPublic: Optional[bool] = Field(None, description="Whether the prompt flow is public")


class PromptFlowResponse(BaseModel):
    """Response model for prompt flow data"""
    flowId: str = Field(..., description="Unique prompt flow identifier (MongoDB _id)")
    name: str = Field(..., description="Prompt flow name")
    promptIds: List[str] = Field(..., description="Array of prompt IDs")
    clientId: Optional[str] = Field(None, description="Client ID (None for public flows)")
    isPublic: bool = Field(..., description="Whether the prompt flow is public")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, and other relevant metadata")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "flowId": "507f1f77bcf86cd799439011",
                "name": "main-flow",
                "promptIds": ["507f1f77bcf86cd799439012", "507f1f77bcf86cd799439013"],
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "isPublic": False,
                "_metadata": {
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": "2024-01-01T00:00:00"
                }
            }
        }
    )

