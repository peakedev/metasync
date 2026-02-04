"""
Pydantic models for worker management API
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, List
from enum import Enum


class WorkerStatus(str, Enum):
    """Status enum for workers"""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class WorkerConfig(BaseModel):
    """Configuration for a worker"""
    pollInterval: int = Field(
        ..., description="Polling interval in seconds", ge=1, le=3600
    )
    maxItemsPerBatch: int = Field(
        ...,
        description="Maximum items to process per batch",
        ge=1,
        le=1000
    )
    modelFilter: Optional[str] = Field(
        None, description="Optional filter for model name (e.g., 'o3-mini')"
    )
    operationFilter: Optional[str] = Field(
        None,
        description="Optional filter for operation type (e.g., 'process')"
    )
    clientReferenceFilters: Optional[Dict[str, str]] = Field(
        None,
        description="Optional filters for clientReference fields (exact match)"
    )


class WorkerCreateRequest(BaseModel):
    """Request model for creating a new worker"""
    workerId: str = Field(
        ...,
        description="Unique worker identifier",
        min_length=1,
        max_length=100
    )
    config: WorkerConfig = Field(..., description="Worker configuration")
    group: Optional[str] = Field(
        None,
        description="Optional group name for batch operations",
        min_length=1,
        max_length=100
    )


class WorkerUpdateRequest(BaseModel):
    """Request model for updating worker configuration"""
    config: Optional[WorkerConfig] = Field(None, description="Updated worker configuration")


class WorkerResponse(BaseModel):
    """Response model for worker data"""
    workerId: str = Field(..., description="Unique worker identifier (MongoDB _id)")
    clientId: str = Field(..., description="Client ID that owns the worker")
    status: WorkerStatus = Field(..., description="Worker status")
    config: WorkerConfig = Field(..., description="Worker configuration")
    group: Optional[str] = Field(
        None,
        description="Optional group name for batch operations"
    )
    threadInfo: Optional[Dict[str, Any]] = Field(
        None, description="Thread information (if running)"
    )
    metadata: Dict[str, Any] = Field(
        ...,
        alias="_metadata",
        description=(
            "Metadata object with createdAt, updatedAt, and other relevant "
            "metadata"
        )
    )
    
    model_config = ConfigDict(
        populate_by_name=True,
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
                "group": "blue",
                "threadInfo": None,
                "_metadata": {
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": "2024-01-01T00:00:00"
                }
            }
        }
    )


class WorkerOverviewResponse(BaseModel):
    """Response model for admin worker overview"""
    total_workers: int = Field(..., description="Total number of workers")
    running_workers: int = Field(..., description="Number of running workers")
    stopped_workers: int = Field(..., description="Number of stopped workers")
    error_workers: int = Field(..., description="Number of workers in error state")
    workers_by_client: Dict[str, Dict[str, int]] = Field(
        ..., description="Worker counts by client ID and status"
    )
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


class WorkerSummaryResponse(BaseModel):
    """Response model for worker summary with counts and IDs by status"""
    running: int = Field(0, description="Count of workers with RUNNING status")
    stopped: int = Field(0, description="Count of workers with STOPPED status")
    error: int = Field(0, description="Count of workers with ERROR status")
    total: int = Field(0, description="Total count of workers matching filters")
    running_ids: List[str] = Field(default_factory=list, description="List of worker IDs with RUNNING status")
    stopped_ids: List[str] = Field(default_factory=list, description="List of worker IDs with STOPPED status")
    error_ids: List[str] = Field(default_factory=list, description="List of worker IDs with ERROR status")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "running": 2,
                "stopped": 3,
                "error": 1,
                "total": 6,
                "running_ids": ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"],
                "stopped_ids": ["507f1f77bcf86cd799439013", "507f1f77bcf86cd799439014", "507f1f77bcf86cd799439015"],
                "error_ids": ["507f1f77bcf86cd799439016"]
            }
        }
    )


class BatchAction(str, Enum):
    """Actions that can be performed on workers in batch"""
    START = "start"
    STOP = "stop"


class WorkerBatchCreateRequest(BaseModel):
    """Request model for batch creating workers"""
    workerIdPrefix: str = Field(
        ...,
        description="Prefix for worker identifiers. Workers will be named {prefix}-1, {prefix}-2, etc.",
        min_length=1,
        max_length=90
    )
    count: int = Field(
        ...,
        description="Number of workers to create",
        ge=1,
        le=100
    )
    config: WorkerConfig = Field(..., description="Worker configuration (shared by all workers)")
    group: Optional[str] = Field(
        None,
        description="Optional group name for batch operations",
        min_length=1,
        max_length=100
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "workerIdPrefix": "worker-group-a",
                "count": 5,
                "config": {
                    "pollInterval": 10,
                    "maxItemsPerBatch": 50,
                    "modelFilter": "o3-mini"
                },
                "group": "blue"
            }
        }
    )


class WorkerBatchUpdateRequest(BaseModel):
    """Request model for batch updating workers (start/stop)"""
    action: BatchAction = Field(
        ...,
        description="Action to perform on the workers"
    )
    workerIds: Optional[List[str]] = Field(
        None,
        description="List of worker IDs to update. Either workerIds or group must be provided."
    )
    group: Optional[str] = Field(
        None,
        description="Group name to select workers. Either workerIds or group must be provided."
    )

    @field_validator('workerIds', 'group')
    @classmethod
    def validate_target_selection(cls, v, info):
        return v

    def model_post_init(self, __context):
        """Validate that either workerIds or group is provided, but not both empty"""
        if not self.workerIds and not self.group:
            raise ValueError("Either workerIds or group must be provided")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "start",
                "group": "blue"
            }
        }
    )


class WorkerBatchCreateResponse(BaseModel):
    """Response model for batch worker creation"""
    created: List[WorkerResponse] = Field(
        ...,
        description="List of successfully created workers"
    )
    failed: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of failed creations with error details"
    )
    total_requested: int = Field(..., description="Total number of workers requested")
    total_created: int = Field(..., description="Number of workers successfully created")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "created": [],
                "failed": [],
                "total_requested": 5,
                "total_created": 5
            }
        }
    )


class WorkerBatchUpdateResponse(BaseModel):
    """Response model for batch worker update (start/stop)"""
    updated: List[WorkerResponse] = Field(
        ...,
        description="List of successfully updated workers"
    )
    failed: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of failed updates with error details"
    )
    action: BatchAction = Field(..., description="Action that was performed")
    total_requested: int = Field(..., description="Total number of workers targeted")
    total_updated: int = Field(..., description="Number of workers successfully updated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "updated": [],
                "failed": [],
                "action": "start",
                "total_requested": 5,
                "total_updated": 5
            }
        }
    )
