"""
Pydantic models for stream API
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class StreamCreateRequest(BaseModel):
    """Request model for creating a stream"""
    userPrompt: str = Field(
        ..., description="Raw text user prompt", min_length=1
    )
    additionalPrompts: Optional[List[str]] = Field(
        None, description="Optional list of prompt IDs to validate and include"
    )
    model: str = Field(
        ..., description="Model name to use for inference", min_length=1
    )
    temperature: float = Field(
        default=0.7, description="Sampling temperature", ge=0, le=2
    )

    @field_validator('additionalPrompts')
    @classmethod
    def validate_additional_prompts(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate additional prompts list"""
        if v is not None and len(v) == 0:
            return None  # Convert empty list to None
        return v


class StreamResponse(BaseModel):
    """Response model for stream metadata (returned after streaming completes)"""
    streamId: str = Field(..., alias="stream_id", description="MongoDB document ID")
    clientId: str = Field(..., description="Client ID that created the stream")
    model: str = Field(..., description="Model used for the stream")
    temperature: float = Field(..., description="Temperature used")
    status: str = Field(..., description="Stream status (completed, error)")
    metadata: Dict[str, Any] = Field(
        ..., alias="_metadata", description="Metadata with timestamps"
    )
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "streamId": "68d39fe8aac434df5f140c57",
                "clientId": "d486037e-d1d7-4213-980e-0f47d8677ad2",
                "model": "gptest",
                "temperature": 0.7,
                "status": "completed",
                "_metadata": {
                    "createdAt": "2024-01-01T00:00:00",
                    "completedAt": "2024-01-01T00:00:05"
                }
            }
        }
    )


class StreamRecord(BaseModel):
    """Internal model for database storage"""
    stream_id: str = Field(..., description="MongoDB document ID")
    client_id: str = Field(..., description="Client ID")
    model: str = Field(..., description="Model name")
    temperature: float = Field(..., description="Temperature used")
    request_data: Dict[str, Any] = Field(
        ..., description="Request data including prompts"
    )
    response_data: Optional[Dict[str, Any]] = Field(
        None, description="Response data including full text"
    )
    processing_metrics: Optional[Dict[str, Any]] = Field(
        None, description="Processing metrics including tokens and duration"
    )
    status: str = Field(default="streaming", description="Stream status")
    metadata: Dict[str, Any] = Field(
        ..., alias="_metadata", description="Metadata with timestamps"
    )

