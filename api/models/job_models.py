"""
Pydantic models for job management API
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from enum import Enum


class JobStatus(str, Enum):
    """Status enum for jobs"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    CONSUMED = "CONSUMED"
    ERROR_PROCESSING = "ERROR_PROCESSING"
    ERROR_CONSUMING = "ERROR_CONSUMING"
    CANCELED = "CANCELED"


class JobCreateRequest(BaseModel):
    """Request model for creating a new job"""
    operation: str = Field(..., description="Operation type", min_length=1)
    prompts: List[str] = Field(..., description="List of prompt IDs", min_items=1)
    model: str = Field(..., description="Model name from models collection", min_length=1)
    temperature: float = Field(..., description="Temperature between 0 and 1", ge=0.0, le=1.0)
    priority: int = Field(..., description="Priority between 1 and 1000", ge=1, le=1000)
    id: Optional[str] = Field(None, description="Optional client-provided job ID")
    requestData: Dict[str, Any] = Field(..., description="Free JSON object to be sent to LLM with prompt (most important field)")
    clientReference: Optional[Dict[str, Any]] = Field(None, description="Free JSON object for client reference")


class JobBatchCreateRequest(BaseModel):
    """Request model for creating multiple jobs at once"""
    jobs: List[JobCreateRequest] = Field(..., description="List of jobs to create", min_items=1)


class JobStatusUpdateRequest(BaseModel):
    """Request model for client status updates only (restricted to status field)"""
    status: JobStatus = Field(..., description="New job status")


class JobUpdateRequest(BaseModel):
    """Request model for full job updates (workers/admin only)"""
    status: Optional[JobStatus] = Field(None, description="Job status")
    operation: Optional[str] = Field(None, description="Operation type")
    prompts: Optional[List[str]] = Field(None, description="List of prompt IDs")
    model: Optional[str] = Field(None, description="Model name")
    temperature: Optional[float] = Field(None, description="Temperature between 0 and 1", ge=0.0, le=1.0)
    priority: Optional[int] = Field(None, description="Priority between 1 and 1000", ge=1, le=1000)
    requestData: Optional[Dict[str, Any]] = Field(None, description="Free JSON object to be sent to LLM")
    clientReference: Optional[Dict[str, Any]] = Field(None, description="Free JSON object for client reference")


class JobResponse(BaseModel):
    """Response model for job data"""
    jobId: str = Field(..., description="Unique job identifier (MongoDB _id)")
    clientId: str = Field(..., description="Client ID that owns the job")
    status: JobStatus = Field(..., description="Job status")
    operation: str = Field(..., description="Operation type")
    prompts: List[str] = Field(..., description="List of prompt IDs")
    model: str = Field(..., description="Model name")
    temperature: float = Field(..., description="Temperature")
    priority: int = Field(..., description="Priority")
    id: Optional[str] = Field(None, description="Client-provided job ID")
    requestData: Dict[str, Any] = Field(..., description="Data to be sent to LLM")
    responseData: Optional[Dict[str, Any]] = Field(None, description="Response data from LLM processing (only present after processing)")
    processingMetrics: Optional[Dict[str, Any]] = Field(None, description="Processing metrics including tokens, duration, and costs (only present after processing)")
    clientReference: Optional[Dict[str, Any]] = Field(None, description="Client reference data")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, and other relevant metadata")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "jobId": "507f1f77bcf86cd799439011",
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "status": "PENDING",
                "operation": "process",
                "prompts": ["507f1f77bcf86cd799439012"],
                "model": "gpt-4",
                "temperature": 0.7,
                "priority": 100,
                "id": "client-job-123",
                "requestData": {"input": "Hello world"},
                "responseData": None,
                "processingMetrics": None,
                "clientReference": {"ref": "abc123"},
                "_metadata": {
                    "isDeleted": False,
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": "2024-01-01T00:00:00",
                    "deletedAt": None,
                    "archivedAt": None,
                    "createdBy": None,
                    "updatedBy": None,
                    "deletedBy": None
                }
            }
        }
    )


class JobSummaryResponse(BaseModel):
    """Response model for job summary with counts by status"""
    PENDING: int = Field(0, description="Count of jobs with PENDING status")
    PROCESSING: int = Field(0, description="Count of jobs with PROCESSING status")
    PROCESSED: int = Field(0, description="Count of jobs with PROCESSED status")
    CONSUMED: int = Field(0, description="Count of jobs with CONSUMED status")
    ERROR_PROCESSING: int = Field(0, description="Count of jobs with ERROR_PROCESSING status")
    ERROR_CONSUMING: int = Field(0, description="Count of jobs with ERROR_CONSUMING status")
    CANCELED: int = Field(0, description="Count of jobs with CANCELED status")
    total: int = Field(0, description="Total count of jobs matching filters")
    processingMetrics: Optional[Dict[str, Any]] = Field(None, description="Aggregated processing metrics from PROCESSED and CONSUMED jobs. Includes inputTokens, outputTokens, totalTokens, duration, and optionally inputCost, outputCost, totalCost, currency (only if all currencies match)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "PENDING": 5,
                "PROCESSING": 2,
                "PROCESSED": 10,
                "CONSUMED": 3,
                "ERROR_PROCESSING": 1,
                "ERROR_CONSUMING": 0,
                "CANCELED": 0,
                "total": 21,
                "processingMetrics": {
                    "inputTokens": 1500,
                    "outputTokens": 800,
                    "totalTokens": 2300,
                    "duration": 45.5,
                    "inputCost": 0.015,
                    "outputCost": 0.008,
                    "totalCost": 0.023,
                    "currency": "USD"
                }
            }
        }
    )

