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
    db_read,
    db_update,
    get_document_by_id,
    safe_operation
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
    
    def get_stream_by_id(self, stream_id: str, client_id: str) -> Dict[str, Any]:
        """
        Get a stream by its ID.
        
        Args:
            stream_id: MongoDB document ID of the stream
            client_id: Client ID for access control
            
        Returns:
            Stream document
            
        Raises:
            ValueError: If stream not found or access denied
        """
        business_logger.log_operation(
            "stream_service",
            "get_stream_by_id",
            stream_id=stream_id,
            client_id=client_id
        )
        
        stream = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            stream_id
        )
        
        if not stream:
            raise ValueError(f"Stream with ID '{stream_id}' not found")
        
        # Check if client owns this stream
        if stream.get("clientId") != client_id:
            raise ValueError(f"Access denied to stream '{stream_id}'")
        
        logger.info(
            "Stream retrieved successfully",
            stream_id=stream_id,
            client_id=client_id
        )
        
        return stream
    
    def list_streams(
        self,
        client_id: str,
        model: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List streams with optional filters.
        
        Args:
            client_id: Client ID (required, clients can only see their own streams)
            model: Optional filter by model
            status: Optional filter by status
            limit: Optional limit on number of results returned
            
        Returns:
            List of stream dictionaries
        """
        business_logger.log_operation(
            "stream_service",
            "list_streams",
            client_id=client_id
        )
        
        # Build query - clients can only see their own streams
        query = {"clientId": client_id}
        
        # Add filters
        if model is not None:
            query["model"] = model
        
        if status is not None:
            query["status"] = status
        
        streams = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query,
            limit=limit
        )
        
        result = []
        for stream in streams:
            # Additional defensive check: ensure client only sees their own streams
            stream_client_id = stream.get("clientId")
            if stream_client_id != client_id:
                logger.warning(
                    "Stream returned with incorrect clientId, filtering out",
                    stream_id=str(stream.get("_id")),
                    expected_client_id=client_id,
                    actual_client_id=stream_client_id
                )
                continue
            
            result.append(self._format_stream_response(stream))
        
        logger.info("Listed streams", count=len(result), client_id=client_id)
        return result
    
    def get_streams_summary(
        self,
        client_id: str,
        model: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get summary of streams with counts by status, with optional filtering.
        
        Args:
            client_id: Client ID (required, clients can only see their own streams)
            model: Optional filter by model
            status: Optional filter by status
            
        Returns:
            Dictionary with counts by status, total count, and aggregated processingMetrics
        """
        business_logger.log_operation(
            "stream_service",
            "get_streams_summary",
            client_id=client_id
        )
        
        # Build query - clients can only see their own streams
        query = {"clientId": client_id}
        
        # Add filters
        if model:
            query["model"] = model
        
        if status:
            query["status"] = status
        
        # Use aggregation to count by status
        db = self.mongo_client[self.db_name]
        collection = db[self.collection_name]
        
        # Build aggregation pipeline
        pipeline = [
            {"$match": query},
            {"$match": {"_metadata.isDeleted": {"$ne": True}}},  # Exclude soft-deleted
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        try:
            # Execute aggregation with retry logic
            def aggregate_operation():
                return list(collection.aggregate(pipeline))
            
            results = safe_operation(aggregate_operation)
            
            # Initialize counts for all statuses
            summary = {
                "streaming": 0,
                "completed": 0,
                "error": 0,
                "total": 0
            }
            
            # Populate counts from aggregation results
            for result in results:
                status_val = result.get("_id")
                count = result.get("count", 0)
                if status_val in summary:
                    summary[status_val] = count
                    summary["total"] += count
            
            # Aggregate processingMetrics from completed streams
            metrics_query = {
                **query,
                "status": "completed",
                "processingMetrics": {"$exists": True, "$ne": None}
            }
            
            def find_metrics_operation():
                return list(collection.find(metrics_query, {"processingMetrics": 1}))
            
            streams_with_metrics = safe_operation(find_metrics_operation)
            
            if streams_with_metrics:
                # Initialize aggregated metrics
                total_input_tokens = 0
                total_output_tokens = 0
                total_tokens = 0
                total_duration = 0.0
                total_llm_duration = 0.0
                total_overhead_duration = 0.0
                total_input_cost = 0.0
                total_output_cost = 0.0
                total_cost = 0.0
                currencies = set()
                streams_with_currency = 0
                streams_without_currency = 0
                
                # Aggregate metrics from all streams
                for stream in streams_with_metrics:
                    metrics = stream.get("processingMetrics", {})
                    if not metrics:
                        continue
                    
                    # Sum always-available fields
                    if "inputTokens" in metrics:
                        total_input_tokens += metrics.get("inputTokens", 0)
                    if "outputTokens" in metrics:
                        total_output_tokens += metrics.get("outputTokens", 0)
                    if "totalTokens" in metrics:
                        total_tokens += metrics.get("totalTokens", 0)
                    if "duration" in metrics:
                        total_duration += metrics.get("duration", 0.0)
                    if "llmDuration" in metrics:
                        total_llm_duration += metrics.get("llmDuration", 0.0)
                    if "overheadDuration" in metrics:
                        total_overhead_duration += metrics.get(
                            "overheadDuration", 0.0
                        )
                    
                    # Collect cost data and currencies
                    if "currency" in metrics and metrics["currency"]:
                        currencies.add(metrics["currency"])
                        streams_with_currency += 1
                        # Sum cost fields if they exist
                        if "inputCost" in metrics:
                            total_input_cost += metrics.get("inputCost", 0.0)
                        if "outputCost" in metrics:
                            total_output_cost += metrics.get("outputCost", 0.0)
                        if "totalCost" in metrics:
                            total_cost += metrics.get("totalCost", 0.0)
                    else:
                        streams_without_currency += 1
                
                # Build processingMetrics response
                processing_metrics = {
                    "inputTokens": total_input_tokens,
                    "outputTokens": total_output_tokens,
                    "totalTokens": total_tokens,
                    "duration": round(total_duration, 2),
                    "llmDuration": round(total_llm_duration, 2),
                    "totalDuration": round(total_duration, 2),
                    "overheadDuration": round(total_overhead_duration, 2)
                }
                
                # Include cost data if:
                # - At least one stream has cost data
                # - All streams that have cost data use the same currency
                if len(currencies) == 1:
                    # All streams with cost data use the same currency
                    # Include aggregated costs (only from streams that had cost data)
                    processing_metrics["inputCost"] = total_input_cost
                    processing_metrics["outputCost"] = total_output_cost
                    processing_metrics["totalCost"] = total_cost
                    processing_metrics["currency"] = currencies.pop()
                elif len(currencies) > 1:
                    # Multiple different currencies found across streams
                    processing_metrics["inputCost"] = None
                    processing_metrics["outputCost"] = None
                    processing_metrics["totalCost"] = None
                    processing_metrics["currency"] = "multiple currencies"
                else:
                    # No streams have cost data at all
                    processing_metrics["inputCost"] = None
                    processing_metrics["outputCost"] = None
                    processing_metrics["totalCost"] = None
                    processing_metrics["currency"] = None
                
                summary["processingMetrics"] = processing_metrics
            else:
                # No streams with metrics found
                summary["processingMetrics"] = None
            
            logger.info("Stream summary retrieved", client_id=client_id, summary=summary)
            return summary
            
        except Exception as e:
            logger.error("Error getting stream summary", error=str(e), client_id=client_id)
            raise RuntimeError(f"Failed to get stream summary: {str(e)}")
    
    def _format_stream_response(self, stream: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a stream document for API response.
        
        Args:
            stream: Raw stream document from database
            
        Returns:
            Formatted stream dictionary
        """
        return {
            "streamId": str(stream["_id"]),
            "clientId": stream.get("clientId"),
            "model": stream.get("model"),
            "temperature": stream.get("temperature"),
            "status": stream.get("status"),
            "processingMetrics": stream.get("processingMetrics"),
            "_metadata": stream.get("_metadata", {})
        }


# Singleton instance
_stream_service_instance = None


def get_stream_service() -> StreamService:
    """Get the singleton StreamService instance."""
    global _stream_service_instance
    if _stream_service_instance is None:
        _stream_service_instance = StreamService()
    return _stream_service_instance

