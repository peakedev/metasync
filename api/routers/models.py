"""
Model management API router
Provides CRUD operations for models with admin authentication
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from api.middleware.auth import verify_admin_api_key
from api.models.model_models import (
    ModelCreateRequest,
    ModelUpdateRequest,
    ModelResponse,
    ModelCreateResponse
)
from api.services.model_service import get_model_service
from api.core.logging import get_logger

logger = get_logger("api.routers.models")

router = APIRouter()


@router.post("", response_model=ModelCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    request: ModelCreateRequest,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Create a new model.
    
    Returns the model data along with the key (only returned once).
    """
    try:
        service = get_model_service()
        
        # Convert Pydantic model to dict (cost will be automatically converted)
        model_data = request.model_dump()
        
        model_data, key = service.create_model(model_data)
        
        return ModelCreateResponse(
            model_id=model_data["model_id"],
            name=model_data["name"],
            sdk=model_data["sdk"],
            endpoint=model_data["endpoint"],
            apiType=model_data["apiType"],
            apiVersion=model_data["apiVersion"],
            deployment=model_data["deployment"],
            service=model_data["service"],
            key=key,
            maxToken=model_data["maxToken"],
            minTemperature=model_data["minTemperature"],
            maxTemperature=model_data["maxTemperature"],
            cost=model_data["cost"],
            _metadata=model_data["_metadata"]
        )
    except ValueError as e:
        logger.error("Validation error creating model", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating model", error=str(e), name=request.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create model"
        )


@router.get("", response_model=List[ModelResponse])
async def list_models(
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    List all models.
    
    Returns a list of all models (excluding keys).
    """
    try:
        service = get_model_service()
        models = service.list_models()
        
        return [
            ModelResponse(
                model_id=model["model_id"],
                name=model["name"],
                sdk=model["sdk"],
                endpoint=model["endpoint"],
                apiType=model["apiType"],
                apiVersion=model["apiVersion"],
                deployment=model["deployment"],
                service=model["service"],
                maxToken=model["maxToken"],
                minTemperature=model["minTemperature"],
                maxTemperature=model["maxTemperature"],
                cost=model["cost"],
                _metadata=model["_metadata"]
            )
            for model in models
        ]
    except Exception as e:
        logger.error("Error listing models", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list models"
        )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Get a model by ID.
    
    Returns the model data (excluding key).
    """
    try:
        service = get_model_service()
        model = service.get_model(model_id)
        
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model not found: {model_id}"
            )
        
        return ModelResponse(
            model_id=model["model_id"],
            name=model["name"],
            sdk=model["sdk"],
            endpoint=model["endpoint"],
            api_type=model["api_type"],
            api_version=model["api_version"],
            deployment=model["deployment"],
            service=model["service"],
            maxToken=model["maxToken"],
            minTemperature=model["minTemperature"],
            maxTemperature=model["maxTemperature"],
            cost=model["cost"],
            _metadata=model["_metadata"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting model", error=str(e), model_id=model_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get model"
        )


@router.patch("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    request: ModelUpdateRequest,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Update a model's fields.
    
    Returns the updated model data.
    """
    try:
        service = get_model_service()
        
        # Convert Pydantic model to dict, excluding None values (cost will be automatically converted)
        updates = request.model_dump(exclude_none=True)
        
        success = service.update_model(model_id, updates)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model not found: {model_id}"
            )
        
        # Get updated model
        model = service.get_model(model_id)
        if not model:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve updated model"
            )
        
        return ModelResponse(
            model_id=model["model_id"],
            name=model["name"],
            sdk=model["sdk"],
            endpoint=model["endpoint"],
            api_type=model["api_type"],
            api_version=model["api_version"],
            deployment=model["deployment"],
            service=model["service"],
            maxToken=model["maxToken"],
            minTemperature=model["minTemperature"],
            maxTemperature=model["maxTemperature"],
            cost=model["cost"],
            _metadata=model["_metadata"]
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.error("Validation error updating model", error=str(e), model_id=model_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating model", error=str(e), model_id=model_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update model"
        )


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: str,
    admin_api_key: str = Depends(verify_admin_api_key)
):
    """
    Delete a model (soft delete).
    """
    try:
        service = get_model_service()
        success = service.delete_model(model_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model not found: {model_id}"
            )
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting model", error=str(e), model_id=model_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete model"
        )

