"""
Prompt management service layer
Handles business logic for prompt CRUD operations, version management, and access control
"""
from typing import Optional, Dict, Any, List, Union
from bson import ObjectId

from config import config
from utilities.cosmos_connector import (
    ClientManager,
    db_create,
    db_read,
    db_find_one,
    db_update,
    db_delete,
    get_document_by_id
)
from api.core.logging import get_logger, BusinessLogger
from api.models.prompt_models import PromptStatus
from api.services.client_service import get_client_service

logger = get_logger("api.services.prompt_service")
business_logger = BusinessLogger()


class PromptService:
    """Service for managing prompts with version control and access control"""
    
    def __init__(self):
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "prompts"
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """Get a valid MongoDB client, reusing cached client if available and not closed."""
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(self._connection_string, self._cached_client)
        return self._cached_client
    
    def _get_next_version_number(self, name: str, type_name: str, client_id: Optional[str], is_public: bool) -> int:
        """
        Get the next version number for a prompt with given name, type, and client_id.
        For private prompts, only considers versions from the same client.
        For public prompts, considers all public prompts.
        
        Args:
            name: Prompt name
            type_name: Prompt type
            client_id: Client ID (None for public prompts)
            is_public: Whether the prompt is public
            
        Returns:
            Next version number (integer)
        """
        try:
            # Build query based on public/private
            if is_public:
                query = {"name": name, "type": type_name, "isPublic": True}
            else:
                query = {"name": name, "type": type_name, "client_id": client_id, "isPublic": False}
            
            existing_prompts = db_read(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                query=query
            )
            
            if not existing_prompts:
                return 1
            
            # Find the highest integer version number
            max_version = 0
            for prompt in existing_prompts:
                version = prompt.get("version")
                # Skip non-integer versions (like "latest", "v1.0", etc.)
                if isinstance(version, int):
                    max_version = max(max_version, version)
            
            return max_version + 1
        except Exception as e:
            logger.error("Error getting next version number", error=str(e), name=name, type=type_name)
            return 1
    
    def _check_version_uniqueness(self, name: str, type_name: str, version: Union[str, int], 
                                   client_id: Optional[str], is_public: bool, exclude_id: Optional[str] = None) -> bool:
        """
        Check if a version is unique for the given name, type, and client_id.
        
        Args:
            name: Prompt name
            type_name: Prompt type
            version: Version to check
            client_id: Client ID (None for public prompts)
            is_public: Whether the prompt is public
            exclude_id: Optional document ID to exclude from check (for updates)
            
        Returns:
            True if version is unique, False otherwise
        """
        try:
            # Build query based on public/private
            if is_public:
                query = {"name": name, "type": type_name, "version": version, "isPublic": True}
            else:
                query = {"name": name, "type": type_name, "version": version, "client_id": client_id, "isPublic": False}
            
            existing = db_find_one(
                self.mongo_client,
                self.db_name,
                self.collection_name,
                query=query
            )
            
            if not existing:
                return True
            
            # If exclude_id is provided, check if the found document is the one we're updating
            if exclude_id:
                if str(existing["_id"]) == exclude_id:
                    return True
            
            return False
        except Exception as e:
            logger.error("Error checking version uniqueness", error=str(e))
            return False
    
    def create_prompt(self, name: str, type_name: str, status: PromptStatus, prompt_text: str,
                     is_public: bool, client_id: Optional[str] = None, 
                     version: Optional[Union[str, int]] = None) -> Dict[str, Any]:
        """
        Create a new prompt with version management.
        
        Args:
            name: Prompt name
            type_name: Prompt type
            status: Prompt status
            prompt_text: The actual prompt text
            is_public: Whether the prompt is public
            client_id: Client ID (required for private prompts, None for public)
            version: Optional version (auto-incremented if not provided)
            
        Returns:
            Created prompt document
            
        Raises:
            ValueError: If version is not unique or if private prompt missing client_id
        """
        business_logger.log_operation("prompt_service", "create_prompt", name=name, type=type_name, 
                                     is_public=is_public, client_id=client_id)
        
        # Validate: private prompts must have client_id
        if not is_public and not client_id:
            raise ValueError("Private prompts require a client_id")
        
        # Determine version
        if version is None:
            version = self._get_next_version_number(name, type_name, client_id, is_public)
        
        # Check version uniqueness
        if not self._check_version_uniqueness(name, type_name, version, client_id, is_public):
            raise ValueError(f"Version {version} already exists for prompt '{name}' with type '{type_name}'")
        
        # Create prompt document
        prompt_doc = {
            "name": name,
            "version": version,
            "type": type_name,
            "status": status.value,
            "prompt": prompt_text,
            "isPublic": is_public
        }
        
        # Only add client_id for private prompts
        if not is_public:
            prompt_doc["client_id"] = client_id
        
        # Save to database
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            prompt_doc
        )
        
        if not db_id:
            business_logger.log_error("prompt_service", "create_prompt", "Failed to create prompt in database")
            raise RuntimeError("Failed to create prompt in database")
        
        logger.info("Prompt created successfully", prompt_id=db_id, name=name, type=type_name, version=version)
        
        # Return the created prompt
        return self.get_prompt_by_id(db_id, client_id)
    
    def list_prompts(self, client_id: str, name: Optional[str] = None, 
                    type_name: Optional[str] = None, status: Optional[PromptStatus] = None,
                    version: Optional[Union[str, int]] = None) -> List[Dict[str, Any]]:
        """
        List prompts with filtering. Returns both public prompts and client's private prompts.
        
        Args:
            client_id: Authenticated client ID
            name: Optional filter by name
            type_name: Optional filter by type
            status: Optional filter by status
            version: Optional filter by version
            
        Returns:
            List of prompt dictionaries
        """
        business_logger.log_operation("prompt_service", "list_prompts", client_id=client_id)
        
        # Build query: include public prompts OR client's private prompts
        # Use $and to properly combine $or with filters (db_read will add _metadata.isDeleted)
        query_conditions = [
            {
                "$or": [
                    {"isPublic": True},
                    {"isPublic": False, "client_id": client_id}
                ]
            }
        ]
        
        # Add filters
        if name:
            query_conditions.append({"name": name})
        if type_name:
            query_conditions.append({"type": type_name})
        if status:
            query_conditions.append({"status": status.value})
        if version is not None:
            query_conditions.append({"version": version})
        
        # Build final query - use $and to combine conditions
        # db_read will add _metadata.isDeleted which will be ANDed with this
        if len(query_conditions) == 1:
            query = query_conditions[0]
        else:
            query = {"$and": query_conditions}
        
        prompts = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query=query
        )
        
        result = []
        for prompt in prompts:
            result.append(self._format_prompt_response(prompt))
        
        logger.info("Listed prompts", count=len(result), client_id=client_id)
        return result
    
    def get_prompt_by_id(self, prompt_id: str, client_id: Optional[str] = None, is_admin: bool = False) -> Dict[str, Any]:
        """
        Get a prompt by ID with access control.
        
        Args:
            prompt_id: Prompt document ID
            client_id: Optional client ID for access control
            is_admin: Whether the requester is an admin (bypasses access control)
            
        Returns:
            Prompt dictionary
            
        Raises:
            ValueError: If prompt not found or access denied
        """
        business_logger.log_operation("prompt_service", "get_prompt_by_id", prompt_id=prompt_id, client_id=client_id, is_admin=is_admin)
        
        prompt = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            prompt_id
        )
        
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")
        
        # Access control: public prompts accessible to all, private prompts only to owner
        # Admins can access any prompt
        if not is_admin and not prompt.get("isPublic", False):
            if not client_id or prompt.get("client_id") != client_id:
                raise ValueError("Access denied: prompt not found or insufficient permissions")
        
        return self._format_prompt_response(prompt)
    
    def update_prompt(self, prompt_id: str, client_id: Optional[str] = None,
                     version: Optional[Union[str, int]] = None,
                     status: Optional[PromptStatus] = None,
                     prompt_text: Optional[str] = None,
                     is_public: Optional[bool] = None,
                     new_client_id: Optional[str] = None,
                     is_admin: bool = False,
                     update_client_id: bool = False) -> Dict[str, Any]:
        """
        Update a prompt with access control.
        
        Args:
            prompt_id: Prompt document ID
            client_id: Client ID for access control (required for private prompts)
            version: Optional new version
            status: Optional new status
            prompt_text: Optional new prompt text
            is_public: Optional new isPublic value
            new_client_id: Optional new client_id (admin only)
            is_admin: Whether the requester is an admin
            update_client_id: Whether client_id update was requested
            
        Returns:
            Updated prompt dictionary
            
        Raises:
            ValueError: If prompt not found, access denied, version conflict, or invalid client_id
        """
        business_logger.log_operation("prompt_service", "update_prompt", prompt_id=prompt_id, client_id=client_id)
        
        # Get existing prompt
        prompt = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            prompt_id
        )
        
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")
        
        # Access control: public prompts can only be updated by admin (checked in router)
        # Private prompts can only be updated by owner
        if not prompt.get("isPublic", False):
            if not client_id or prompt.get("client_id") != client_id:
                raise ValueError("Access denied: prompt not found or insufficient permissions")
        
        # Check version uniqueness if version is being changed
        if version is not None and version != prompt.get("version"):
            name = prompt.get("name")
            type_name = prompt.get("type")
            existing_client_id = prompt.get("client_id") if not prompt.get("isPublic", False) else None
            existing_is_public = prompt.get("isPublic", False)
            
            if not self._check_version_uniqueness(name, type_name, version, existing_client_id, 
                                                 existing_is_public, exclude_id=prompt_id):
                raise ValueError(f"Version {version} already exists for prompt '{name}' with type '{type_name}'")
        
        # Handle client_id updates (admin only)
        # Determine final isPublic value (use new value if provided, otherwise existing)
        final_is_public = is_public if is_public is not None else prompt.get("isPublic", False)
        
        # Process client_id update if explicitly requested (admin only)
        if update_client_id:
            if not is_admin:
                raise ValueError("Only admins can update client_id")
            
            # Validate client_id exists if provided (not None and not empty)
            if new_client_id is not None and new_client_id != "":
                client_service = get_client_service()
                existing_client = client_service.get_client(new_client_id)
                if existing_client is None:
                    raise ValueError(f"Client not found: {new_client_id}")
            
            # Business rule: client_id can be removed/nullified only if isPublic is true
            if (new_client_id is None or new_client_id == "") and not final_is_public:
                raise ValueError("Cannot remove client_id when isPublic is false")
            
            # Business rule: if isPublic is false, client_id must be valid
            if final_is_public is False and (new_client_id is None or new_client_id == ""):
                raise ValueError("client_id is required when isPublic is false")
            
            # Business rule: if isPublic is true, client_id must be None
            if final_is_public is True and (new_client_id is not None and new_client_id != ""):
                raise ValueError("client_id must be null when isPublic is true")
        
        # Build update document
        updates = {}
        if version is not None:
            updates["version"] = version
        if status is not None:
            updates["status"] = status.value
        if prompt_text is not None:
            updates["prompt"] = prompt_text
        if is_public is not None:
            updates["isPublic"] = is_public
            # If changing from public to private, need client_id
            if is_public is False and not prompt.get("client_id"):
                if not client_id and new_client_id is None:
                    raise ValueError("Cannot make prompt private without client_id")
                updates["client_id"] = new_client_id if new_client_id is not None else client_id
            # If changing from private to public, remove client_id (admin only)
            elif is_public is True:
                updates["client_id"] = None
        
        # Handle client_id update separately (admin only)
        if update_client_id:
            updates["client_id"] = new_client_id if new_client_id else None
        
        if not updates:
            logger.warning("No updates provided", prompt_id=prompt_id)
            return self._format_prompt_response(prompt)
        
        # Update the prompt
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            prompt_id,
            updates
        )
        
        if not success:
            business_logger.log_error("prompt_service", "update_prompt", "Failed to update prompt in database")
            raise RuntimeError("Failed to update prompt in database")
        
        logger.info("Prompt updated successfully", prompt_id=prompt_id)
        
        # Return updated prompt
        return self.get_prompt_by_id(prompt_id, client_id)
    
    def delete_prompt(self, prompt_id: str, client_id: Optional[str] = None) -> bool:
        """
        Soft delete a prompt with access control.
        
        Args:
            prompt_id: Prompt document ID
            client_id: Client ID for access control (required for private prompts)
            
        Returns:
            True if deletion successful
            
        Raises:
            ValueError: If prompt not found or access denied
        """
        business_logger.log_operation("prompt_service", "delete_prompt", prompt_id=prompt_id, client_id=client_id)
        
        # Get existing prompt
        prompt = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            prompt_id
        )
        
        if not prompt:
            raise ValueError(f"Prompt not found: {prompt_id}")
        
        # Access control: public prompts can only be deleted by admin (checked in router)
        # Private prompts can only be deleted by owner
        if not prompt.get("isPublic", False):
            if not client_id or prompt.get("client_id") != client_id:
                raise ValueError("Access denied: prompt not found or insufficient permissions")
        
        # Soft delete the prompt
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            prompt_id
        )
        
        if success:
            logger.info("Prompt deleted successfully", prompt_id=prompt_id)
        else:
            business_logger.log_error("prompt_service", "delete_prompt", "Failed to delete prompt in database")
            raise RuntimeError("Failed to delete prompt in database")
        
        return success
    
    def _normalize_status(self, status: Any) -> str:
        """
        Normalize status value to match PromptStatus enum.
        Maps old/legacy status values to valid enum values.
        
        Args:
            status: Status value from database
            
        Returns:
            Normalized status string
        """
        if not status:
            return "DRAFT"
        
        status_str = str(status).upper()
        
        # Map old/legacy values to new enum values
        status_mapping = {
            "ACTIVE": "PUBLISHED",
            "INACTIVE": "ARCHIVE",
            "PUBLISHED": "PUBLISHED",
            "DRAFT": "DRAFT",
            "ARCHIVE": "ARCHIVE",
            "ARCHIVED": "ARCHIVE"
        }
        
        return status_mapping.get(status_str, "DRAFT")
    
    def _format_prompt_response(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a prompt document for API response.
        
        Args:
            prompt: Raw prompt document from database
            
        Returns:
            Formatted prompt dictionary
        """
        return {
            "promptId": str(prompt["_id"]),
            "name": prompt.get("name"),
            "version": prompt.get("version"),
            "type": prompt.get("type"),
            "status": self._normalize_status(prompt.get("status")),
            "prompt": prompt.get("prompt"),
            "clientId": prompt.get("client_id"),
            "isPublic": prompt.get("isPublic", False),
            "_metadata": prompt.get("_metadata", {})
        }


# Singleton instance
_prompt_service: Optional[PromptService] = None


def get_prompt_service() -> PromptService:
    """Get or create the singleton prompt service instance"""
    global _prompt_service
    if _prompt_service is None:
        _prompt_service = PromptService()
    return _prompt_service

