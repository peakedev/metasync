"""
Pydantic models for stream API
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class StreamStatus(str, Enum):
    """Status enum for streams"""
    STREAMING = "streaming"
    COMPLETED = "completed"
    ERROR = "error"


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
    streamId: str = Field(..., description="MongoDB document ID")
    clientId: str = Field(..., description="Client ID that created the stream")
    model: str = Field(..., description="Model used for the stream")
    temperature: float = Field(..., description="Temperature used")
    status: str = Field(..., description="Stream status (completed, error)")
    processingMetrics: Optional[Dict[str, Any]] = Field(
        None, description="Processing metrics including tokens, duration, and costs (only present after streaming completes)"
    )
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
                "processingMetrics": {
                    "inputTokens": 10,
                    "outputTokens": 50,
                    "totalTokens": 60,
                    "duration": 1.45,
                    "llmDuration": 1.23,
                    "totalDuration": 1.45,
                    "overheadDuration": 0.22,
                    "inputCost": 0.0001,
                    "outputCost": 0.0005,
                    "totalCost": 0.0006,
                    "currency": "USD"
                },
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


class StreamSummaryResponse(BaseModel):
    """Response model for stream summary with counts by status"""
    streaming: int = Field(0, description="Count of streams with streaming status")
    completed: int = Field(0, description="Count of streams with completed status")
    error: int = Field(0, description="Count of streams with error status")
    total: int = Field(0, description="Total count of streams matching filters")
    processingMetrics: Optional[Dict[str, Any]] = Field(
        None, 
        description="Aggregated processing metrics from completed streams. Includes inputTokens, outputTokens, totalTokens, duration, and optionally inputCost, outputCost, totalCost, currency (only if all currencies match)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "streaming": 2,
                "completed": 15,
                "error": 1,
                "total": 18,
                "processingMetrics": {
                    "inputTokens": 1500,
                    "outputTokens": 800,
                    "totalTokens": 2300,
                    "duration": 48.3,
                    "llmDuration": 45.5,
                    "totalDuration": 48.3,
                    "overheadDuration": 2.8,
                    "inputCost": 0.015,
                    "outputCost": 0.008,
                    "totalCost": 0.023,
                    "currency": "USD"
                }
            }
        }
    )

