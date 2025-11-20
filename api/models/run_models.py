"""
Pydantic models for run management API
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from enum import Enum


class RunStatus(str, Enum):
    """Status enum for runs"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IterationResult(BaseModel):
    """Result from a single iteration"""
    iteration: int = Field(..., description="Iteration number (0-indexed)")
    jobId: str = Field(..., description="Job ID for this iteration")
    workingPromptId: str = Field(..., description="Working prompt ID used")
    status: str = Field(..., description="Job status")
    evalResult: Optional[Dict[str, Any]] = Field(None, description="Evaluation result if available")
    suggestedPromptId: Optional[str] = Field(None, description="Suggested prompt ID from meta step if available")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "iteration": 0,
                "jobId": "507f1f77bcf86cd799439011",
                "workingPromptId": "507f1f77bcf86cd799439012",
                "status": "PROCESSED",
                "evalResult": {"score": 8.5, "feedback": "Good translation"},
                "suggestedPromptId": "507f1f77bcf86cd799439013"
            }
        }
    )


class ModelRun(BaseModel):
    """Results from running all iterations with a specific model"""
    model: str = Field(..., description="Model name")
    iterations: List[IterationResult] = Field(default_factory=list, description="List of iteration results")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "gpt-4o",
                "iterations": [
                    {
                        "iteration": 0,
                        "jobId": "507f1f77bcf86cd799439011",
                        "workingPromptId": "507f1f77bcf86cd799439012",
                        "status": "PROCESSED",
                        "evalResult": {"score": 8.5},
                        "suggestedPromptId": "507f1f77bcf86cd799439013"
                    }
                ]
            }
        }
    )


class RunCreateRequest(BaseModel):
    """Request model for creating a new run"""
    initialWorkingPromptId: str = Field(..., description="Starting working prompt ID", min_length=1)
    evalPromptId: str = Field(..., description="Evaluation prompt ID (fixed for all iterations)", min_length=1)
    evalModel: str = Field(..., description="Evaluation model name (fixed for all iterations)", min_length=1)
    metaPromptId: str = Field(..., description="Meta-prompting prompt ID (fixed for all iterations)", min_length=1)
    metaModel: str = Field(..., description="Meta-prompting model name (fixed for all iterations)", min_length=1)
    workingModels: List[str] = Field(..., description="List of working model names to iterate through", min_items=1)
    maxIterations: int = Field(..., description="Maximum iterations per model", ge=1, le=100)
    temperature: float = Field(0.7, description="Temperature between 0 and 1", ge=0.0, le=1.0)
    priority: int = Field(100, description="Job priority between 1 and 1000", ge=1, le=1000)
    requestData: Dict[str, Any] = Field(..., description="Input data to be sent to LLM (e.g., text to translate)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "initialWorkingPromptId": "507f1f77bcf86cd799439011",
                "evalPromptId": "507f1f77bcf86cd799439012",
                "evalModel": "gpt-4o",
                "metaPromptId": "507f1f77bcf86cd799439013",
                "metaModel": "gpt-4o",
                "workingModels": ["gpt-4o", "claude-3.5-sonnet"],
                "maxIterations": 5,
                "temperature": 0.7,
                "priority": 100,
                "requestData": {"text": "Bonjour mon ami"}
            }
        }
    )


class RunUpdateStatusRequest(BaseModel):
    """Request model for updating run status"""
    action: str = Field(..., description="Action to perform: 'pause', 'resume', or 'cancel'")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "pause"
            }
        }
    )


class RunResponse(BaseModel):
    """Response model for run data"""
    runId: str = Field(..., description="Unique run identifier (MongoDB _id)")
    clientId: str = Field(..., description="Client ID that owns the run")
    status: RunStatus = Field(..., description="Run status")
    initialWorkingPromptId: str = Field(..., description="Initial working prompt ID")
    evalPromptId: str = Field(..., description="Evaluation prompt ID")
    evalModel: str = Field(..., description="Evaluation model name")
    metaPromptId: str = Field(..., description="Meta-prompting prompt ID")
    metaModel: str = Field(..., description="Meta-prompting model name")
    workingModels: List[str] = Field(..., description="List of working model names")
    maxIterations: int = Field(..., description="Maximum iterations per model")
    temperature: float = Field(..., description="Temperature")
    priority: int = Field(..., description="Priority")
    requestData: Dict[str, Any] = Field(..., description="Input data for working prompts")
    currentModelIndex: int = Field(0, description="Index of current model being processed")
    currentIteration: int = Field(0, description="Current iteration number")
    currentJobId: Optional[str] = Field(None, description="Current job ID being processed")
    modelRuns: List[ModelRun] = Field(default_factory=list, description="Results for each model")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, etc.")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "runId": "507f1f77bcf86cd799439011",
                "clientId": "123e4567-e89b-12d3-a456-426614174000",
                "status": "RUNNING",
                "initialWorkingPromptId": "507f1f77bcf86cd799439012",
                "evalPromptId": "507f1f77bcf86cd799439013",
                "evalModel": "gpt-4o",
                "metaPromptId": "507f1f77bcf86cd799439014",
                "metaModel": "gpt-4o",
                "workingModels": ["gpt-4o", "claude-3.5-sonnet"],
                "maxIterations": 5,
                "temperature": 0.7,
                "priority": 100,
                "requestData": {"text": "Bonjour mon ami"},
                "currentModelIndex": 0,
                "currentIteration": 0,
                "currentJobId": "507f1f77bcf86cd799439015",
                "modelRuns": [
                    {
                        "model": "gpt-4o",
                        "iterations": []
                    }
                ],
                "_metadata": {
                    "isDeleted": False,
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": "2024-01-01T00:00:00"
                }
            }
        }
    )

