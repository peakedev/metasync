"""
Prompt flow management service layer
Handles business logic for prompt flow CRUD operations and access control
"""
from typing import Optional, Dict, Any, List

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_read,
    db_update,
    db_delete,
    get_document_by_id
)
from api.core.logging import get_logger, BusinessLogger

logger = get_logger("api.services.prompt_flow_service")
business_logger = BusinessLogger()


class PromptFlowService:
    """Service for managing prompt flows with access control"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "prompt_flows"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def create_prompt_flow(self, name: str, prompt_ids: List[str],
                          is_public: bool, client_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new prompt flow.
        
        Args:
            name: Prompt flow name
            prompt_ids: Array of prompt IDs
            is_public: Whether the prompt flow is public
            client_id: Client ID (required for private flows, None for public)
            
        Returns:
            Created prompt flow document
            
        Raises:
            ValueError: If private flow missing client_id
        """
        business_logger.log_operation("prompt_flow_service", "create_prompt_flow", name=name, 
                                     is_public=is_public, client_id=client_id)
        
        # Validate: private flows must have client_id
        if not is_public and not client_id:
            raise ValueError("Private prompt flows require a client_id")
        
        # Create prompt flow document
        flow_doc = {
            "name": name,
            "prompt_ids": prompt_ids,
            "isPublic": is_public
        }
        
        # Only add client_id for private flows
        if not is_public:
            flow_doc["client_id"] = client_id
        
        # Save to database
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            flow_doc
        )
        
        if not db_id:
            business_logger.log_error("prompt_flow_service", "create_prompt_flow", "Failed to create prompt flow in database")
            raise RuntimeError("Failed to create prompt flow in database")
        
        logger.info("Prompt flow created successfully", flow_id=db_id, name=name)
        
        # Return the created prompt flow
        return self.get_prompt_flow_by_id(db_id, client_id)
    
    def list_prompt_flows(self, client_id: Optional[str] = None, is_admin: bool = False) -> List[Dict[str, Any]]:
        """
        List prompt flows with filtering. Returns public flows and client's private flows, or all if admin.
        
        Args:
            client_id: Optional client ID (required if not admin)
            is_admin: Whether the requester is an admin
            
        Returns:
            List of prompt flow dictionaries
        """
        business_logger.log_operation("prompt_flow_service", "list_prompt_flows", client_id=client_id, is_admin=is_admin)
        
        # Build query
        if is_admin:
            # Admin can see all flows
            query = {}
        else:
            if not client_id:
                raise ValueError("Client ID is required for non-admin users")
            # Build query: include public flows OR client's private flows
            query = {
                "$or": [
                    {"isPublic": True},
                    {"isPublic": False, "client_id": client_id}
                ]
            }
        
        flows = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query
        )
        
        result = []
        for flow in flows:
            # Additional defensive check: ensure non-admin users only see their own private flows
            if not is_admin:
                flow_client_id = flow.get("client_id")
                flow_is_public = flow.get("isPublic", False)
                if not flow_is_public and flow_client_id != client_id:
                    logger.warning(
                        "Prompt flow returned with incorrect client_id, filtering out",
                        flow_id=str(flow.get("_id")),
                        expected_client_id=client_id,
                        actual_client_id=flow_client_id
                    )
                    continue
            
            result.append(self._format_flow_response(flow))
        
        logger.info("Listed prompt flows", count=len(result), client_id=client_id, is_admin=is_admin)
        return result
    
    def get_prompt_flow_by_id(self, flow_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> Dict[str, Any]:
        """
        Get a prompt flow by ID with access control.
        
        Args:
            flow_id: Prompt flow document ID
            client_id: Optional client ID for access control
            is_admin: Whether the requester is an admin
            
        Returns:
            Prompt flow dictionary
            
        Raises:
            ValueError: If prompt flow not found or access denied
        """
        business_logger.log_operation("prompt_flow_service", "get_prompt_flow_by_id", flow_id=flow_id, client_id=client_id, is_admin=is_admin)
        
        flow = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            flow_id
        )
        
        if not flow:
            raise ValueError(f"Prompt flow not found: {flow_id}")
        
        # Access control: public flows accessible to all, private flows only to owner or admin
        if not is_admin:
            if not flow.get("isPublic", False):
                if not client_id or flow.get("client_id") != client_id:
                    raise ValueError("Access denied: prompt flow not found or insufficient permissions")
        
        return self._format_flow_response(flow)
    
    def update_prompt_flow(self, flow_id: str, client_id: Optional[str] = None,
                          name: Optional[str] = None,
                          prompt_ids: Optional[List[str]] = None,
                          is_public: Optional[bool] = None,
                          is_admin: bool = False) -> Dict[str, Any]:
        """
        Update a prompt flow with access control.
        
        Args:
            flow_id: Prompt flow document ID
            client_id: Client ID for access control (required for private flows)
            name: Optional new name
            prompt_ids: Optional new prompt_ids array
            is_public: Optional new isPublic value
            is_admin: Whether the requester is an admin
            
        Returns:
            Updated prompt flow dictionary
            
        Raises:
            ValueError: If prompt flow not found, access denied
        """
        business_logger.log_operation("prompt_flow_service", "update_prompt_flow", flow_id=flow_id, client_id=client_id, is_admin=is_admin)
        
        # Get existing prompt flow
        flow = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            flow_id
        )
        
        if not flow:
            raise ValueError(f"Prompt flow not found: {flow_id}")
        
        # Access control: public flows can only be updated by admin (checked in router)
        # Private flows can only be updated by owner
        if not is_admin:
            if not flow.get("isPublic", False):
                if not client_id or flow.get("client_id") != client_id:
                    raise ValueError("Access denied: prompt flow not found or insufficient permissions")
        
        # Build update document
        updates = {}
        if name is not None:
            updates["name"] = name
        if prompt_ids is not None:
            updates["prompt_ids"] = prompt_ids
        if is_public is not None:
            updates["isPublic"] = is_public
            # If changing from public to private, need client_id
            if is_public is False and not flow.get("client_id"):
                if not client_id:
                    raise ValueError("Cannot make prompt flow private without client_id")
                updates["client_id"] = client_id
            # If changing from private to public, remove client_id (admin only)
            elif is_public is True:
                updates["client_id"] = None
        
        if not updates:
            logger.warning("No updates provided", flow_id=flow_id)
            return self._format_flow_response(flow)
        
        # Update the prompt flow
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            flow_id,
            updates
        )
        
        if not success:
            business_logger.log_error("prompt_flow_service", "update_prompt_flow", "Failed to update prompt flow in database")
            raise RuntimeError("Failed to update prompt flow in database")
        
        logger.info("Prompt flow updated successfully", flow_id=flow_id)
        
        # Return updated prompt flow
        return self.get_prompt_flow_by_id(flow_id, client_id, is_admin)
    
    def delete_prompt_flow(self, flow_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> bool:
        """
        Soft delete a prompt flow with access control.
        
        Args:
            flow_id: Prompt flow document ID
            client_id: Client ID for access control (required for private flows)
            is_admin: Whether the requester is an admin
            
        Returns:
            True if deletion successful
            
        Raises:
            ValueError: If prompt flow not found or access denied
        """
        business_logger.log_operation("prompt_flow_service", "delete_prompt_flow", flow_id=flow_id, client_id=client_id, is_admin=is_admin)
        
        # Get existing prompt flow
        flow = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            flow_id
        )
        
        if not flow:
            raise ValueError(f"Prompt flow not found: {flow_id}")
        
        # Access control: public flows can only be deleted by admin (checked in router)
        # Private flows can only be deleted by owner
        if not is_admin:
            if not flow.get("isPublic", False):
                if not client_id or flow.get("client_id") != client_id:
                    raise ValueError("Access denied: prompt flow not found or insufficient permissions")
        
        # Soft delete the prompt flow
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            flow_id
        )
        
        if success:
            logger.info("Prompt flow deleted successfully", flow_id=flow_id)
        else:
            business_logger.log_error("prompt_flow_service", "delete_prompt_flow", "Failed to delete prompt flow in database")
            raise RuntimeError("Failed to delete prompt flow in database")
        
        return success
    
    def _format_flow_response(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a prompt flow document for API response.
        
        Args:
            flow: Raw prompt flow document from database
            
        Returns:
            Formatted prompt flow dictionary
        """
        metadata = flow.get("_metadata", {})
        return {
            "flow_id": str(flow["_id"]),
            "name": flow.get("name"),
            "prompt_ids": flow.get("prompt_ids", []),
            "client_id": flow.get("client_id"),
            "isPublic": flow.get("isPublic", False),
            "created_at": metadata.get("createdAt") or "",
            "updated_at": metadata.get("updatedAt")
        }


# Singleton instance
_prompt_flow_service: Optional[PromptFlowService] = None


def get_prompt_flow_service() -> PromptFlowService:
    """Get or create the singleton prompt flow service instance"""
    global _prompt_flow_service
    if _prompt_flow_service is None:
        _prompt_flow_service = PromptFlowService()
    return _prompt_flow_service

