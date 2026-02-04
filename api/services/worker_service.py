"""
Worker management service layer
Handles business logic for worker CRUD operations, validation, and access control
"""
from typing import Optional, Dict, Any, List

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_read,
    db_find_one,
    db_update,
    db_delete,
    get_document_by_id,
)
from api.core.logging import get_logger, BusinessLogger
from api.models.worker_models import WorkerStatus, WorkerConfig

logger = get_logger("api.services.worker_service")
business_logger = BusinessLogger()


class WorkerService:
    """Service for managing workers with validation and access control"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "workers"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def _check_worker_access(self, worker: Dict[str, Any], client_id: Optional[str], is_admin: bool = False) -> bool:
        """
        Check if a client has access to a worker.
        
        Args:
            worker: Worker document
            client_id: Client ID requesting access
            is_admin: Whether the requester is an admin
            
        Returns:
            True if access is allowed, False otherwise
        """
        if is_admin:
            return True
        
        if not client_id:
            return False
        
        worker_client_id = worker.get("clientId")
        return worker_client_id == client_id
    
    def create_worker(
        self,
        client_id: str,
        worker_id: str,
        config: WorkerConfig,
        group: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new worker.

        Args:
            client_id: Client ID creating the worker
            worker_id: Client-provided worker identifier
            config: Worker configuration
            group: Optional group name for batch operations

        Returns:
            Created worker dictionary

        Raises:
            ValueError: If validation fails
        """
        business_logger.log_operation("worker_service", "create_worker", client_id=client_id, worker_id=worker_id, group=group)

        # Check if worker_id is unique for this client
        existing = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"workerId": worker_id, "clientId": client_id}
        )
        if existing:
            raise ValueError(f"Worker ID '{worker_id}' already exists for this client")

        # Create worker document
        worker_doc = {
            "workerId": worker_id,
            "clientId": client_id,
            "status": WorkerStatus.STOPPED.value,
            "config": {
                "pollInterval": config.pollInterval,
                "maxItemsPerBatch": config.maxItemsPerBatch,
                "modelFilter": config.modelFilter,
                "operationFilter": config.operationFilter,
                "clientReferenceFilters": config.clientReferenceFilters
            },
            "group": group,
            "threadInfo": None
        }

        # Save to database
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            worker_doc
        )

        if not db_id:
            business_logger.log_error("worker_service", "create_worker", "Failed to create worker in database")
            raise RuntimeError("Failed to create worker in database")

        logger.info("Worker created successfully", worker_id=db_id, client_id=client_id, worker_identifier=worker_id, group=group)

        # Return the created worker
        return self.get_worker_by_id(db_id, client_id)
    
    def list_workers(self, client_id: Optional[str] = None, is_admin: bool = False) -> List[Dict[str, Any]]:
        """
        List workers with access control.
        
        Args:
            client_id: Client ID (required if not admin)
            is_admin: Whether the requester is an admin
            
        Returns:
            List of worker dictionaries
        """
        business_logger.log_operation("worker_service", "list_workers", client_id=client_id, is_admin=is_admin)
        
        # Build query
        if is_admin:
            query = {}
        else:
            if not client_id:
                raise ValueError("Client ID is required for non-admin users")
            query = {"clientId": client_id}
        
        workers = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query
        )
        
        result = []
        for worker in workers:
            # Additional defensive check: ensure non-admin users only see their own workers
            if not is_admin:
                worker_client_id = worker.get("clientId")
                if worker_client_id != client_id:
                    logger.warning(
                        "Worker returned with incorrect clientId, filtering out",
                        worker_id=str(worker.get("_id")),
                        expected_client_id=client_id,
                        actual_client_id=worker_client_id
                    )
                    continue
            
            result.append(self._format_worker_response(worker))
        
        logger.info("Listed workers", count=len(result), client_id=client_id, is_admin=is_admin)
        return result
    
    def get_worker_by_id(self, worker_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> Dict[str, Any]:
        """
        Get a worker by ID with access control.
        
        Args:
            worker_id: Worker document ID
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Worker dictionary
            
        Raises:
            ValueError: If worker not found or access denied
        """
        business_logger.log_operation("worker_service", "get_worker_by_id", worker_id=worker_id, client_id=client_id)
        
        worker = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            worker_id
        )
        
        if not worker:
            raise ValueError(f"Worker not found: {worker_id}")
        
        # Check access
        if not self._check_worker_access(worker, client_id, is_admin):
            raise ValueError("Access denied: worker not found or insufficient permissions")
        
        return self._format_worker_response(worker)
    
    def update_worker(
        self,
        worker_id: str,
        config: Optional[WorkerConfig] = None,
        status: Optional[WorkerStatus] = None,
        thread_info: Optional[Dict[str, Any]] = None,
        client_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        """
        Update a worker.
        
        Args:
            worker_id: Worker document ID
            config: Optional new configuration
            status: Optional new status
            thread_info: Optional thread information
            client_id: Optional client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Updated worker dictionary
            
        Raises:
            ValueError: If worker not found, access denied, or validation fails
        """
        business_logger.log_operation("worker_service", "update_worker", worker_id=worker_id, is_admin=is_admin)
        
        # Get existing worker
        worker = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            worker_id
        )
        
        if not worker:
            raise ValueError(f"Worker not found: {worker_id}")
        
        # Check access (admin can update any, client can only update their own)
        if not is_admin:
            if not client_id or not self._check_worker_access(worker, client_id, is_admin=False):
                raise ValueError("Access denied: worker not found or insufficient permissions")
        
        # Build update document
        updates = {}
        
        if config is not None:
            updates["config"] = {
                "pollInterval": config.pollInterval,
                "maxItemsPerBatch": config.maxItemsPerBatch,
                "modelFilter": config.modelFilter,
                "operationFilter": config.operationFilter,
                "clientReferenceFilters": config.clientReferenceFilters
            }
        
        if status is not None:
            updates["status"] = status.value
        
        if thread_info is not None:
            updates["threadInfo"] = thread_info
        
        if not updates:
            logger.warning("No updates provided", worker_id=worker_id)
            return self._format_worker_response(worker)
        
        # Update the worker
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            worker_id,
            updates
        )
        
        if not success:
            business_logger.log_error("worker_service", "update_worker", "Failed to update worker in database")
            raise RuntimeError("Failed to update worker in database")
        
        logger.info("Worker updated successfully", worker_id=worker_id)
        
        # Return updated worker
        return self.get_worker_by_id(worker_id, client_id, is_admin)
    
    def delete_worker(self, worker_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> bool:
        """
        Delete a worker with access control.
        
        Args:
            worker_id: Worker document ID
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            True if deletion successful
            
        Raises:
            ValueError: If worker not found or access denied
        """
        business_logger.log_operation("worker_service", "delete_worker", worker_id=worker_id, client_id=client_id)
        
        # Get existing worker
        worker = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            worker_id
        )
        
        if not worker:
            raise ValueError(f"Worker not found: {worker_id}")
        
        # Check access
        if not self._check_worker_access(worker, client_id, is_admin):
            raise ValueError("Access denied: worker not found or insufficient permissions")
        
        # Check if worker is running (should be stopped before deletion)
        current_status = worker.get("status")
        if current_status == WorkerStatus.RUNNING.value:
            raise ValueError("Cannot delete a running worker. Stop the worker first.")
        
        # Soft delete the worker
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            worker_id
        )
        
        if success:
            logger.info("Worker deleted successfully", worker_id=worker_id)
        else:
            business_logger.log_error("worker_service", "delete_worker", "Failed to delete worker in database")
            raise RuntimeError("Failed to delete worker in database")
        
        return success
    
    def get_workers_summary(
        self,
        client_id: Optional[str] = None,
        is_admin: bool = False,
        model_filter: Optional[str] = None,
        operation_filter: Optional[str] = None,
        client_reference_filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get summary of workers with counts and IDs by status, with optional filtering.
        
        Args:
            client_id: Client ID (required if not admin)
            is_admin: Whether the requester is an admin
            model_filter: Optional filter by config.modelFilter
            operation_filter: Optional filter by config.operationFilter
            client_reference_filters: Optional dict of filters for config.clientReferenceFilters fields
                e.g., {"randomProp": "hello"} will filter where config.clientReferenceFilters.randomProp == "hello"
            
        Returns:
            Dictionary with counts by status, total count, and lists of IDs by status
        """
        business_logger.log_operation("worker_service", "get_workers_summary", client_id=client_id, is_admin=is_admin)
        
        # Build query
        if is_admin:
            query = {}
        else:
            if not client_id:
                raise ValueError("Client ID is required for non-admin users")
            query = {"clientId": client_id}
        
        # Add filters for nested config fields
        if model_filter:
            query["config.modelFilter"] = model_filter
        
        if operation_filter:
            query["config.operationFilter"] = operation_filter
        
        # Add clientReferenceFilters filters (nested field filtering)
        if client_reference_filters:
            for key, value in client_reference_filters.items():
                query[f"config.clientReferenceFilters.{key}"] = value
        
        # Use aggregation to group by status and collect IDs
        db = self.mongo_client[self.db_name]
        collection = db[self.collection_name]
        
        # Build aggregation pipeline
        pipeline = [
            {"$match": query},
            {"$match": {"_metadata.isDeleted": {"$ne": True}}},  # Exclude soft-deleted
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "worker_ids": {"$push": {"$toString": "$_id"}}
                }
            }
        ]
        
        try:
            results = list(collection.aggregate(pipeline))
            
            # Initialize summary with all statuses
            summary = {
                WorkerStatus.RUNNING.value: 0,
                WorkerStatus.STOPPED.value: 0,
                WorkerStatus.ERROR.value: 0,
                "total": 0,
                f"{WorkerStatus.RUNNING.value}_ids": [],
                f"{WorkerStatus.STOPPED.value}_ids": [],
                f"{WorkerStatus.ERROR.value}_ids": []
            }
            
            # Populate counts and IDs from aggregation results
            for result in results:
                status = result.get("_id")
                count = result.get("count", 0)
                worker_ids = result.get("worker_ids", [])
                
                if status in [WorkerStatus.RUNNING.value, WorkerStatus.STOPPED.value, WorkerStatus.ERROR.value]:
                    summary[status] = count
                    summary[f"{status}_ids"] = worker_ids
                    summary["total"] += count
            
            logger.info("Workers summary retrieved", total=summary["total"], client_id=client_id, is_admin=is_admin)
            return summary
            
        except Exception as e:
            logger.error("Error getting workers summary", error=str(e), client_id=client_id)
            raise RuntimeError(f"Failed to get workers summary: {str(e)}")
    
    def _format_worker_response(self, worker: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a worker document for API response.

        Args:
            worker: Raw worker document from database

        Returns:
            Formatted worker dictionary
        """
        config_data = worker.get("config", {})

        return {
            "workerId": str(worker["_id"]),
            "clientId": worker.get("clientId"),
            "status": worker.get("status"),
            "config": {
                "pollInterval": config_data.get("pollInterval"),
                "maxItemsPerBatch": config_data.get("maxItemsPerBatch"),
                "modelFilter": config_data.get("modelFilter"),
                "operationFilter": config_data.get("operationFilter"),
                "clientReferenceFilters": config_data.get("clientReferenceFilters")
            },
            "group": worker.get("group"),
            "threadInfo": worker.get("threadInfo"),
            "_metadata": worker.get("_metadata", {})
        }

    def get_workers_by_group(
        self,
        group: str,
        client_id: Optional[str] = None,
        is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all workers in a specific group.

        Args:
            group: Group name to filter by
            client_id: Client ID for access control
            is_admin: Whether the requester is an admin

        Returns:
            List of worker dictionaries in the group
        """
        business_logger.log_operation("worker_service", "get_workers_by_group", group=group, client_id=client_id)

        # Build query
        query = {"group": group}
        if not is_admin:
            if not client_id:
                raise ValueError("Client ID is required for non-admin users")
            query["clientId"] = client_id

        workers = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query
        )

        result = []
        for worker in workers:
            result.append(self._format_worker_response(worker))

        logger.info("Listed workers by group", group=group, count=len(result), client_id=client_id)
        return result

    def create_workers_batch(
        self,
        client_id: str,
        worker_id_prefix: str,
        count: int,
        config: WorkerConfig,
        group: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create multiple workers in batch.

        Args:
            client_id: Client ID creating the workers
            worker_id_prefix: Prefix for worker identifiers
            count: Number of workers to create
            config: Worker configuration (shared by all workers)
            group: Optional group name for batch operations

        Returns:
            Dictionary with created workers, failed creations, and counts
        """
        business_logger.log_operation(
            "worker_service", "create_workers_batch",
            client_id=client_id, prefix=worker_id_prefix, count=count, group=group
        )

        created = []
        failed = []

        for i in range(1, count + 1):
            worker_id = f"{worker_id_prefix}-{i}"
            try:
                worker = self.create_worker(
                    client_id=client_id,
                    worker_id=worker_id,
                    config=config,
                    group=group
                )
                created.append(worker)
            except Exception as e:
                logger.warning(
                    "Failed to create worker in batch",
                    worker_id=worker_id,
                    error=str(e)
                )
                failed.append({
                    "workerId": worker_id,
                    "error": str(e)
                })

        logger.info(
            "Batch worker creation completed",
            total_requested=count,
            total_created=len(created),
            total_failed=len(failed),
            client_id=client_id
        )

        return {
            "created": created,
            "failed": failed,
            "total_requested": count,
            "total_created": len(created)
        }


# Singleton instance
_worker_service: Optional[WorkerService] = None


def get_worker_service() -> WorkerService:
    """Get or create the singleton worker service instance"""
    global _worker_service
    if _worker_service is None:
        _worker_service = WorkerService()
    return _worker_service



