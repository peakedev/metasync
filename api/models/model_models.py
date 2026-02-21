"""
Pydantic models for model management API
"""
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict
)
from typing import Optional, Dict, Any
from datetime import datetime
from llm_sdks.registry import SDKRegistry


class CostModel(BaseModel):
    """Cost structure for model pricing"""
    tokens: int = Field(
        ..., description="Number of tokens for cost calculation", gt=0
    )
    currency: str = Field(
        ..., description="Currency code (e.g., USD)", min_length=1
    )
    input: float = Field(..., description="Cost per input token", ge=0)
    output: float = Field(..., description="Cost per output token", ge=0)


class ModelCreateRequest(BaseModel):
    """Request model for creating a new model"""
    name: str = Field(
        ..., description="Model name", min_length=1, max_length=255
    )
    sdk: str = Field(
        ...,
        description=(
            "SDK type (ChatCompletionsClient, AzureOpenAI, or Anthropic)"
        )
    )
    endpoint: str = Field(..., description="API endpoint URL", min_length=1)
    apiType: str = Field(..., description="API type", min_length=1)
    apiVersion: str = Field(..., description="API version", min_length=1)
    deployment: str = Field(..., description="Deployment name", min_length=1)
    service: Optional[str] = Field(None, description="Service name for local keyring lookup only (optional). Used to determine which keyring service to query when loading API keys from the local keychain. Not used for actual LLM API calls.", min_length=1)
    key: str = Field(..., description="API key identifier", min_length=1)
    maxToken: int = Field(..., description="Maximum tokens", gt=0)
    maxCompletionToken: Optional[int] = Field(
        None,
        description="Maximum completion tokens (use instead of maxToken for models requiring max_completion_tokens)",
        gt=0
    )
    minTemperature: float = Field(
        ..., description="Minimum temperature", ge=0, le=2
    )
    maxTemperature: float = Field(
        ..., description="Maximum temperature", ge=0, le=2
    )
    cost: CostModel = Field(..., description="Cost structure")
    
    @field_validator('sdk')
    @classmethod
    def validate_sdk(cls, v: str) -> str:
        """Validate SDK is one of the supported types"""
        allowed_sdks = SDKRegistry.list_sdks()
        if v not in allowed_sdks:
            raise ValueError(f"SDK must be one of: {', '.join(allowed_sdks)}")
        return v
    
    @model_validator(mode='after')
    def validate_temperature_range(self):
        """Validate maxTemperature is >= minTemperature"""
        if self.maxTemperature < self.minTemperature:
            raise ValueError("maxTemperature must be >= minTemperature")
        return self


class ModelUpdateRequest(BaseModel):
    """Request model for updating a model"""
    name: Optional[str] = Field(None, description="Model name", min_length=1, max_length=255)
    sdk: Optional[str] = Field(None, description="SDK type (ChatCompletionsClient, AzureOpenAI, or Anthropic)")
    endpoint: Optional[str] = Field(None, description="API endpoint URL", min_length=1)
    apiType: Optional[str] = Field(None, description="API type", min_length=1)
    apiVersion: Optional[str] = Field(None, description="API version", min_length=1)
    deployment: Optional[str] = Field(None, description="Deployment name", min_length=1)
    service: Optional[str] = Field(None, description="Service name for local keyring lookup only (optional). Used to determine which keyring service to query when loading API keys from the local keychain. Not used for actual LLM API calls.", min_length=1)
    key: Optional[str] = Field(None, description="API key identifier", min_length=1)
    maxToken: Optional[int] = Field(None, description="Maximum tokens", gt=0)
    maxCompletionToken: Optional[int] = Field(
        None,
        description="Maximum completion tokens (use instead of maxToken for models requiring max_completion_tokens)",
        gt=0
    )
    minTemperature: Optional[float] = Field(None, description="Minimum temperature", ge=0, le=2)
    maxTemperature: Optional[float] = Field(None, description="Maximum temperature", ge=0, le=2)
    cost: Optional[CostModel] = Field(None, description="Cost structure")
    
    @field_validator('sdk')
    @classmethod
    def validate_sdk(cls, v: Optional[str]) -> Optional[str]:
        """Validate SDK is one of the supported types"""
        if v is None:
            return v
        allowed_sdks = SDKRegistry.list_sdks()
        if v not in allowed_sdks:
            raise ValueError(f"SDK must be one of: {', '.join(allowed_sdks)}")
        return v
    
    @model_validator(mode='after')
    def validate_temperature_range(self):
        """Validate maxTemperature is >= minTemperature if both are provided"""
        if self.maxTemperature is not None and self.minTemperature is not None:
            if self.maxTemperature < self.minTemperature:
                raise ValueError("maxTemperature must be >= minTemperature")
        return self


class ModelResponse(BaseModel):
    """Response model for model data (without API key)"""
    modelId: str = Field(..., alias="model_id", description="MongoDB document ID")
    name: str = Field(..., description="Model name")
    sdk: str = Field(..., description="SDK type")
    endpoint: str = Field(..., description="API endpoint URL")
    apiType: str = Field(..., description="API type")
    apiVersion: str = Field(..., description="API version")
    deployment: str = Field(..., description="Deployment name")
    service: Optional[str] = Field(None, description="Service name for local keyring lookup only (optional). Used to determine which keyring service to query when loading API keys from the local keychain. Not used for actual LLM API calls.")
    maxToken: int = Field(..., description="Maximum tokens")
    maxCompletionToken: Optional[int] = Field(
        None,
        description="Maximum completion tokens (for models requiring max_completion_tokens)"
    )
    minTemperature: float = Field(..., description="Minimum temperature")
    maxTemperature: float = Field(..., description="Maximum temperature")
    cost: CostModel = Field(..., description="Cost structure")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, and other relevant metadata")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "modelId": "68d39fe8aac434df5f140c57",
                "name": "mistral-medium-2505",
                "sdk": "ChatCompletionsClient",
                "endpoint": "https://myendpoint.com",
                "apiType": "foundry",
                "apiVersion": "2024-05-01-preview",
                "deployment": "mistral-medium-2505",
                "service": "azure-ai",
                "maxToken": 100000,
                "minTemperature": 0,
                "maxTemperature": 1,
                "cost": {
                    "tokens": 1000,
                    "currency": "USD",
                    "input": 0.0002,
                    "output": 0.0004
                },
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


class ModelCreateResponse(BaseModel):
    """Response model for model creation (includes key once)"""
    modelId: str = Field(..., alias="model_id", description="MongoDB document ID")
    name: str = Field(..., description="Model name")
    sdk: str = Field(..., description="SDK type")
    endpoint: str = Field(..., description="API endpoint URL")
    apiType: str = Field(..., description="API type")
    apiVersion: str = Field(..., description="API version")
    deployment: str = Field(..., description="Deployment name")
    service: Optional[str] = Field(None, description="Service name for local keyring lookup only (optional). Used to determine which keyring service to query when loading API keys from the local keychain. Not used for actual LLM API calls.")
    key: str = Field(..., description="API key identifier (only returned once during creation)")
    maxToken: int = Field(..., description="Maximum tokens")
    maxCompletionToken: Optional[int] = Field(
        None,
        description="Maximum completion tokens (for models requiring max_completion_tokens)"
    )
    minTemperature: float = Field(..., description="Minimum temperature")
    maxTemperature: float = Field(..., description="Maximum temperature")
    cost: CostModel = Field(..., description="Cost structure")
    metadata: Dict[str, Any] = Field(..., alias="_metadata", description="Metadata object with createdAt, updatedAt, and other relevant metadata")
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "modelId": "68d39fe8aac434df5f140c57",
                "name": "mistral-medium-2505",
                "sdk": "ChatCompletionsClient",
                "endpoint": "https://myendpoint.com",
                "apiType": "foundry",
                "apiVersion": "2024-05-01-preview",
                "deployment": "mistral-medium-2505",
                "service": "azure-ai",
                "key": "KEY-MISTRAL-MEDIUM-2505",
                "maxToken": 100000,
                "minTemperature": 0,
                "maxTemperature": 1,
                "cost": {
                    "tokens": 1000,
                    "currency": "USD",
                    "input": 0.0002,
                    "output": 0.0004
                },
                "_metadata": {
                    "isDeleted": False,
                    "createdAt": "2024-01-01T00:00:00",
                    "updatedAt": None,
                    "deletedAt": None,
                    "archivedAt": None,
                    "createdBy": None,
                    "updatedBy": None,
                    "deletedBy": None
                }
            }
        }
    )

