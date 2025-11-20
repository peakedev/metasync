"""
Stream management service layer
Handles business logic for stream operations, validation, and access control
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from bson import ObjectId

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_update,
    get_document_by_id
)
from api.core.logging import get_logger, BusinessLogger

logger = get_logger("api.services.stream_service")
business_logger = BusinessLogger()


class StreamService:
    """Service for managing streams with validation and access control"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "streams"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def validate_additional_prompts(self, prompt_ids: List[str]) -> None:
        """
        Validate that all provided prompt IDs exist in the prompts collection.
        
        Args:
            prompt_ids: List of prompt IDs to validate
            
        Raises:
            ValueError: If any prompt ID does not exist
        """
        if not prompt_ids:
            return
        
        # Check each prompt exists
        for prompt_id in prompt_ids:
            try:
                prompt = get_document_by_id(
                    self.mongo_client,
                    self.db_name,
                    "prompts",
                    prompt_id
                )
                if not prompt:
                    raise ValueError(f"Prompt with ID '{prompt_id}' not found")
            except Exception as e:
                logger.error(f"Error validating prompt {prompt_id}", error=str(e))
                raise ValueError(f"Prompt with ID '{prompt_id}' not found")
    
    def validate_model(self, model_name: str) -> Dict[str, Any]:
        """
        Validate that the model exists and return its configuration.
        
        Args:
            model_name: Name of the model to validate
            
        Returns:
            Model configuration dictionary
            
        Raises:
            ValueError: If model does not exist
        """
        from utilities.cosmos_connector import db_find_one
        
        model_doc = db_find_one(
            self.mongo_client,
            self.db_name,
            "models",
            query={"name": model_name}
        )
        
        if not model_doc:
            raise ValueError(f"Model '{model_name}' not found")
        
        return model_doc
    
    def create_stream_record(
        self,
        client_id: str,
        model: str,
        temperature: float,
        request_data: Dict[str, Any]
    ) -> str:
        """
        Create a new stream record in the database.
        
        Args:
            client_id: ID of the client making the request
            model: Model name
            temperature: Temperature parameter
            request_data: Request data including prompts
            
        Returns:
            Stream ID (MongoDB document ID)
        """
        business_logger.log_operation(
            "stream_service",
            "create_stream_record",
            client_id=client_id,
            model=model
        )
        
        stream_data = {
            "clientId": client_id,
            "model": model,
            "temperature": temperature,
            "requestData": request_data,
            "responseData": None,
            "processingMetrics": None,
            "status": "streaming",
            "_metadata": {
                "createdAt": datetime.utcnow().isoformat(),
                "completedAt": None,
                "isDeleted": False
            }
        }
        
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            stream_data
        )
        
        if not db_id:
            business_logger.log_error(
                "stream_service",
                "create_stream_record",
                "Failed to create stream record in database"
            )
            raise RuntimeError("Failed to create stream record in database")
        
        logger.info(
            "Stream record created successfully",
            stream_id=db_id,
            client_id=client_id,
            model=model
        )
        
        return db_id
    
    def update_stream_record(
        self,
        stream_id: str,
        response_data: Dict[str, Any],
        processing_metrics: Dict[str, Any],
        status: str = "completed"
    ) -> None:
        """
        Update a stream record with response data and metrics.
        
        Args:
            stream_id: ID of the stream to update
            response_data: Response data including full text
            processing_metrics: Processing metrics including tokens and duration
            status: Final status (completed or error)
        """
        business_logger.log_operation(
            "stream_service",
            "update_stream_record",
            stream_id=stream_id,
            status=status
        )
        
        update_data = {
            "responseData": response_data,
            "processingMetrics": processing_metrics,
            "status": status,
            "_metadata.completedAt": datetime.utcnow().isoformat()
        }
        
        db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            stream_id,
            update_data
        )
        
        logger.info(
            "Stream record updated successfully",
            stream_id=stream_id,
            status=status
        )


# Singleton instance
_stream_service_instance = None


def get_stream_service() -> StreamService:
    """Get the singleton StreamService instance."""
    global _stream_service_instance
    if _stream_service_instance is None:
        _stream_service_instance = StreamService()
    return _stream_service_instance

