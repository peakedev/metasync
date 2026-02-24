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
    clientReference: Optional[Dict[str, Any]] = Field(
        None, description="Free JSON object for client reference"
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
    requestData: Optional[Dict[str, Any]] = Field(
        None,
        description="Request data including user prompt, system "
        "prompt, and additional prompts"
    )
    responseData: Optional[Dict[str, Any]] = Field(
        None,
        description="Response data including full LLM response text"
    )
    processingMetrics: Optional[Dict[str, Any]] = Field(
        None, description="Processing metrics including tokens, duration, and costs (only present after streaming completes)"
    )
    clientReference: Optional[Dict[str, Any]] = Field(
        None, description="Client reference data"
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
                "requestData": {
                    "userPrompt": "Summarize this text...",
                    "systemPrompt": "You are a helpful assistant.",
                    "additionalPrompts": ["prompt-id-1"]
                },
                "responseData": {
                    "fullText": "Here is a summary of the text..."
                },
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
                "clientReference": {"ref": "abc123"},
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
    client_reference: Optional[Dict[str, Any]] = Field(
        None, description="Client reference data"
    )
    status: str = Field(default="streaming", description="Stream status")
    metadata: Dict[str, Any] = Field(
        ..., alias="_metadata", description="Metadata with timestamps"
    )


class StreamAnalyticsDataPoint(BaseModel):
    """Individual stream data point for analytics charting"""
    streamId: str = Field(..., description="MongoDB document ID")
    createdAt: str = Field(
        ..., description="ISO datetime when the stream was created"
    )
    model: str = Field(..., description="Model used for the stream")
    clientReference: Optional[Dict[str, Any]] = Field(
        None, description="Client reference data"
    )
    promptIds: Optional[List[str]] = Field(
        None,
        description="IDs of additional prompts used"
    )
    userPrompt: str = Field(
        ..., description="The user prompt sent to the model"
    )
    processingMetrics: Dict[str, Any] = Field(
        ...,
        description="Processing metrics: tokens, duration, costs"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "streamId": "68d39fe8aac434df5f140c57",
                "createdAt": "2024-01-01T00:00:00",
                "model": "gpt-4",
                "clientReference": {
                    "sessionId": "abc",
                    "userId": "xyz"
                },
                "promptIds": ["id1", "id2"],
                "userPrompt": "Summarize this text...",
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
                }
            }
        }
    )


class StreamAnalyticsGroupMetrics(BaseModel):
    """Aggregated metrics for an analytics group"""
    inputTokens: int = Field(
        0, description="Total input tokens across the group"
    )
    outputTokens: int = Field(
        0, description="Total output tokens across the group"
    )
    totalTokens: int = Field(
        0, description="Total tokens across the group"
    )
    totalDuration: float = Field(
        0.0, description="Total processing duration in seconds"
    )
    totalCost: Optional[float] = Field(
        None,
        description="Total cost across the group (null if "
        "currencies are mixed or unavailable)"
    )
    currency: Optional[str] = Field(
        None, description="Currency if uniform across the group"
    )


class StreamAnalyticsGroup(BaseModel):
    """Unique grouping of streams by model, clientReference, and prompts"""
    model: str = Field(..., description="Model name")
    clientReference: Optional[Dict[str, Any]] = Field(
        None, description="Client reference data"
    )
    promptIds: Optional[List[str]] = Field(
        None, description="Additional prompt IDs used"
    )
    count: int = Field(
        ..., description="Number of streams in this group"
    )
    aggregatedMetrics: StreamAnalyticsGroupMetrics = Field(
        ..., description="Aggregated processing metrics"
    )


class StreamAnalyticsDateRange(BaseModel):
    """Applied date range for the analytics query"""
    fromDate: Optional[str] = Field(
        None,
        alias="from",
        description="Start of the date range (ISO datetime)"
    )
    toDate: Optional[str] = Field(
        None,
        alias="to",
        description="End of the date range (ISO datetime)"
    )

    model_config = ConfigDict(populate_by_name=True)


class StreamAnalyticsResponse(BaseModel):
    """Response model for stream analytics endpoint"""
    dataPoints: List[StreamAnalyticsDataPoint] = Field(
        ..., description="Individual stream data points"
    )
    groups: List[StreamAnalyticsGroup] = Field(
        ...,
        description="Unique groups derived from model, "
        "clientReference, and promptIds"
    )
    totalCount: int = Field(
        ..., description="Total number of data points returned"
    )
    dateRange: StreamAnalyticsDateRange = Field(
        ..., description="Applied date range filters"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dataPoints": [
                    {
                        "streamId": "68d39fe8aac434df5f140c57",
                        "createdAt": "2024-01-01T00:00:00",
                        "model": "gpt-4",
                        "clientReference": {
                            "sessionId": "abc"
                        },
                        "promptIds": ["id1"],
                        "userPrompt": "Summarize this...",
                        "processingMetrics": {
                            "inputTokens": 10,
                            "outputTokens": 50,
                            "totalTokens": 60,
                            "duration": 1.45,
                            "inputCost": 0.0001,
                            "outputCost": 0.0005,
                            "totalCost": 0.0006,
                            "currency": "USD"
                        }
                    }
                ],
                "groups": [
                    {
                        "model": "gpt-4",
                        "clientReference": {
                            "sessionId": "abc"
                        },
                        "promptIds": ["id1"],
                        "count": 5,
                        "aggregatedMetrics": {
                            "inputTokens": 150,
                            "outputTokens": 800,
                            "totalTokens": 950,
                            "totalDuration": 12.5,
                            "totalCost": 0.023,
                            "currency": "USD"
                        }
                    }
                ],
                "totalCount": 20,
                "dateRange": {
                    "from": "2024-01-01T00:00:00",
                    "to": "2024-01-31T23:59:59"
                }
            }
        }
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

