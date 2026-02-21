"""
Model management service layer
Handles business logic for model CRUD operations
"""
from typing import Optional, Dict, Any, Tuple

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_read,
    db_find_one,
    db_update,
    db_delete
)
from api.core.logging import get_logger, BusinessLogger

logger = get_logger("api.services.model_service")
business_logger = BusinessLogger()


class ModelService:
    """Service for managing models"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "models"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def create_model(self, model_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        Create a new model.
        
        Args:
            model_data: Model data dictionary with all required fields
            
        Returns:
            Tuple of (model_data, key) where key is only returned once
        """
        business_logger.log_operation("model_service", "create_model", name=model_data.get("name"))
        
        # Create model document
        model_doc = {
            "name": model_data["name"],
            "sdk": model_data["sdk"],
            "endpoint": model_data["endpoint"],
            "apiType": model_data["apiType"],
            "apiVersion": model_data["apiVersion"],
            "deployment": model_data["deployment"],
            "key": model_data["key"],
            "maxToken": model_data["maxToken"],
            "minTemperature": model_data["minTemperature"],
            "maxTemperature": model_data["maxTemperature"],
            "cost": model_data["cost"]
        }
        
        # Only include service if provided
        if model_data.get("service") is not None:
            model_doc["service"] = model_data["service"]
        
        # Only include maxCompletionToken if provided
        if model_data.get("maxCompletionToken") is not None:
            model_doc["maxCompletionToken"] = model_data["maxCompletionToken"]
        
        # Save to database (metadata will be added by db_create)
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            model_doc
        )
        
        if not db_id:
            business_logger.log_error("model_service", "create_model", "Failed to create model in database")
            raise RuntimeError("Failed to create model in database")
        
        logger.info("Model created successfully", model_id=db_id, name=model_data.get("name"))
        
        # Get the created document to retrieve metadata
        from bson import ObjectId
        created_model = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"_id": ObjectId(db_id)},
            include_deleted=False
        )
        
        if not created_model:
            raise RuntimeError("Failed to retrieve created model")
        
        # Return model data with key
        result_data = {
            "model_id": db_id,
            "name": created_model["name"],
            "sdk": created_model["sdk"],
            "endpoint": created_model["endpoint"],
            "apiType": created_model["apiType"],
            "apiVersion": created_model["apiVersion"],
            "deployment": created_model["deployment"],
            "service": created_model["service"],
            "key": created_model["key"],
            "maxToken": created_model["maxToken"],
            "maxCompletionToken": created_model.get("maxCompletionToken"),
            "minTemperature": created_model["minTemperature"],
            "maxTemperature": created_model["maxTemperature"],
            "cost": created_model["cost"],
            "_metadata": created_model.get("_metadata", {})
        }
        
        return result_data, model_data["key"]
    
    def list_models(self) -> list[Dict[str, Any]]:
        """
        List all models (excluding API keys).
        
        Returns:
            List of model dictionaries
        """
        business_logger.log_operation("model_service", "list_models")
        
        models = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={},
            projection={
                "name": 1,
                "sdk": 1,
                "endpoint": 1,
                "apiType": 1,
                "apiVersion": 1,
                "deployment": 1,
                "service": 1,
                "maxToken": 1,
                "maxCompletionToken": 1,
                "minTemperature": 1,
                "maxTemperature": 1,
                "cost": 1,
                "_metadata": 1
            }
        )
        
        result = []
        for model in models:
            result.append({
                "model_id": str(model["_id"]),
                "name": model.get("name"),
                "sdk": model.get("sdk"),
                "endpoint": model.get("endpoint"),
                "apiType": model.get("apiType"),
                "apiVersion": model.get("apiVersion"),
                "deployment": model.get("deployment"),
                "service": model.get("service"),
                "maxToken": model.get("maxToken"),
                "maxCompletionToken": model.get("maxCompletionToken"),
                "minTemperature": model.get("minTemperature"),
                "maxTemperature": model.get("maxTemperature"),
                "cost": model.get("cost"),
                "_metadata": model.get("_metadata", {})
            })
        
        logger.info("Listed models", count=len(result))
        return result
    
    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a model by ID.
        
        Args:
            model_id: Model identifier (MongoDB _id)
            
        Returns:
            Model dictionary or None if not found
        """
        business_logger.log_operation("model_service", "get_model", model_id=model_id)
        
        from bson import ObjectId
        try:
            model = db_find_one(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                query={"_id": ObjectId(model_id)},
                projection={
                    "name": 1,
                    "sdk": 1,
                    "endpoint": 1,
                    "apiType": 1,
                    "apiVersion": 1,
                    "deployment": 1,
                    "service": 1,
                    "maxToken": 1,
                    "maxCompletionToken": 1,
                    "minTemperature": 1,
                    "maxTemperature": 1,
                    "cost": 1,
                    "_metadata": 1
                }
            )
        except Exception as e:
            logger.warning("Invalid model ID format", model_id=model_id, error=str(e))
            return None
        
        if not model:
            logger.warning("Model not found", model_id=model_id)
            return None
        
        return {
            "model_id": str(model["_id"]),
            "name": model.get("name"),
            "sdk": model.get("sdk"),
            "endpoint": model.get("endpoint"),
            "apiType": model.get("apiType"),
            "apiVersion": model.get("apiVersion"),
            "deployment": model.get("deployment"),
            "service": model.get("service"),
            "maxToken": model.get("maxToken"),
            "maxCompletionToken": model.get("maxCompletionToken"),
            "minTemperature": model.get("minTemperature"),
            "maxTemperature": model.get("maxTemperature"),
            "cost": model.get("cost"),
            "_metadata": model.get("_metadata", {})
        }
    
    def update_model(self, model_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a model's fields.
        
        Args:
            model_id: Model identifier (MongoDB _id)
            updates: Dictionary of fields to update
            
        Returns:
            True if update successful, False otherwise
        """
        business_logger.log_operation("model_service", "update_model", model_id=model_id, updates=updates)
        
        # First verify model exists
        from bson import ObjectId
        try:
            model = db_find_one(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                query={"_id": ObjectId(model_id)}
            )
        except Exception as e:
            logger.warning("Invalid model ID format for update", model_id=model_id, error=str(e))
            return False
        
        if not model:
            logger.warning("Model not found for update", model_id=model_id)
            return False
        
        # Build update document (exclude None values)
        update_doc = {k: v for k, v in updates.items() if v is not None}
        
        if not update_doc:
            logger.warning("No updates provided", model_id=model_id)
            return False
        
        # Update the model (metadata.updatedAt will be set by db_update)
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            model_id,
            update_doc
        )
        
        if success:
            logger.info("Model updated successfully", model_id=model_id, updates=update_doc)
        else:
            logger.error("Failed to update model", model_id=model_id)
        
        return success
    
    def delete_model(self, model_id: str) -> bool:
        """
        Soft delete a model.
        
        Args:
            model_id: Model identifier (MongoDB _id)
            
        Returns:
            True if deletion successful, False otherwise
        """
        business_logger.log_operation("model_service", "delete_model", model_id=model_id)
        
        # First verify model exists
        from bson import ObjectId
        try:
            model = db_find_one(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                query={"_id": ObjectId(model_id)}
            )
        except Exception as e:
            logger.warning("Invalid model ID format for deletion", model_id=model_id, error=str(e))
            return False
        
        if not model:
            logger.warning("Model not found for deletion", model_id=model_id)
            return False
        
        # Soft delete the model (metadata.isDeleted will be set by db_delete)
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            model_id
        )
        
        if success:
            logger.info("Model deleted successfully", model_id=model_id)
        else:
            logger.error("Failed to delete model", model_id=model_id)
        
        return success


# Singleton instance
_model_service: Optional[ModelService] = None


def get_model_service() -> ModelService:
    """Get or create the singleton model service instance"""
    global _model_service
    if _model_service is None:
        _model_service = ModelService()
    return _model_service

