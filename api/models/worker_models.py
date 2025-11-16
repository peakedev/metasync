"""
Pydantic models for worker management API
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any
from enum import Enum


class WorkerStatus(str, Enum):
    """Status enum for workers"""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class WorkerConfig(BaseModel):
    """Configuration for a worker"""
    pollInterval: int = Field(..., description="Polling interval in seconds", ge=1, le=3600)
    maxItemsPerBatch: int = Field(..., description="Maximum items to process per batch", ge=1, le=1000)
    modelFilter: Optional[str] = Field(None, description="Optional filter for model name (e.g., 'o3-mini')")
    operationFilter: Optional[str] = Field(None, description="Optional filter for operation type (e.g., 'process')")
    clientReferenceFilters: Optional[Dict[str, str]] = Field(None, description="Optional filters for clientReference fields (exact match)")


class WorkerCreateRequest(BaseModel):
    """Request model for creating a new worker"""
    workerId: str = Field(..., description="Unique worker identifier", min_length=1, max_length=100)
    config: WorkerConfig = Field(..., description="Worker configuration")


class WorkerUpdateRequest(BaseModel):
    """Request model for updating worker configuration"""
    config: Optional[WorkerConfig] = Field(None, description="Updated worker configuration")


class WorkerResponse(BaseModel):
    """Response model for worker data"""
    workerId: str = Field(..., description="Unique worker identifier (MongoDB _id)")
    clientId: str = Field(..., description="Client ID that owns the worker")
    status: WorkerStatus = Field(..., description="Worker status")
    config: WorkerConfig = Field(..., description="Worker configuration")
    threadInfo: Optional[Dict[str, Any]] = Field(None, description="Thread information (if running)")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "workerId": "507f1f77bcf86cd799439011",
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "status": "stopped",
                "config": {
                    "pollInterval": 10,
                    "maxItemsPerBatch": 50,
                    "modelFilter": "o3-mini",
                    "operationFilter": "process",
                    "clientReferenceFilters": {"randomProp": "X"}
                },
                "threadInfo": None,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }
    )


class WorkerOverviewResponse(BaseModel):
    """Response model for admin worker overview"""
    total_workers: int = Field(..., description="Total number of workers")
    running_workers: int = Field(..., description="Number of running workers")
    stopped_workers: int = Field(..., description="Number of stopped workers")
    error_workers: int = Field(..., description="Number of workers in error state")
    workers_by_client: Dict[str, Dict[str, int]] = Field(..., description="Worker counts by client ID and status")
    workers: list[WorkerResponse] = Field(..., description="List of all workers")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_workers": 5,
                "running_workers": 2,
                "stopped_workers": 2,
                "error_workers": 1,
                "workers_by_client": {
                    "client-1": {"running": 1, "stopped": 1, "error": 0},
                    "client-2": {"running": 1, "stopped": 1, "error": 1}
                },
                "workers": []
            }
        }
    )



