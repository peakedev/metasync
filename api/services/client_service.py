"""
Client management service layer
Handles business logic for client CRUD operations, API key generation, hashing, and verification
"""
import uuid
import secrets
from typing import Optional, Dict, Any, Tuple
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

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

logger = get_logger("api.services.client_service")
business_logger = BusinessLogger()


class ClientService:
    """Service for managing clients and API keys"""
    
    def __init__(self):
        self.hasher = PasswordHasher()
        self._connection_string = config.db_connection_string
        self.db_name = config.db_name
        self.collection_name = "clients"
        self.pepper = config.api_key_pepper
        self._cached_client = None
    
    @property
    def mongo_client(self):
        """
        Get a valid MongoDB client.
        
        Reusing cached client if available and not closed.
        """
        client_manager = ClientManager()
        self._cached_client = client_manager.get_valid_client(
            self._connection_string, self._cached_client
        )
        return self._cached_client
    
    @staticmethod
    def generate_api_key() -> str:
        """
        Generate a 256-bit (64 hex characters) random API key.
        
        Returns:
            Random 64-character hex string
        """
        return secrets.token_hex(32)
    
    @staticmethod
    def generate_salt() -> str:
        """
        Generate a random salt for hashing.
        
        Returns:
            Random hex-encoded salt string
        """
        return secrets.token_hex(32)
    
    def hash_api_key(self, api_key: str, salt: str, pepper: str) -> str:
        """
        Hash an API key using argon2 with salt and pepper.
        
        Args:
            api_key: The API key to hash
            salt: Random salt for this client
            pepper: Global pepper from config
            
        Returns:
            Argon2 hash string
        """
        # Combine salt + api_key + pepper for hashing
        combined = salt + api_key + pepper
        return self.hasher.hash(combined)
    
    def verify_api_key(
        self, provided_key: str, salt: str, stored_hash: str, pepper: str
    ) -> bool:
        """
        Verify an API key against stored hash.
        
        Args:
            provided_key: API key to verify
            salt: Salt stored with the client
            stored_hash: Argon2 hash stored in database
            pepper: Global pepper from config
            
        Returns:
            True if API key matches, False otherwise
        """
        try:
            combined = salt + provided_key + pepper
            self.hasher.verify(stored_hash, combined)
            return True
        except VerifyMismatchError:
            return False
        except Exception as e:
            logger.error("Error verifying API key", error=str(e))
            return False
    
    def create_client(self, name: str) -> Tuple[Dict[str, Any], str]:
        """
        Create a new client with generated API key.
        
        Args:
            name: Client name
            
        Returns:
            Tuple of (client_data, api_key) where api_key is only returned once
        """
        business_logger.log_operation("client_service", "create_client", name=name)
        
        # Generate client ID, API key, and salt
        client_id = str(uuid.uuid4())
        api_key = self.generate_api_key()
        salt = self.generate_salt()
        
        # Hash the API key with salt and pepper
        api_key_hash = self.hash_api_key(api_key, salt, self.pepper)
        
        # Create client document
        client_doc = {
            "clientId": client_id,
            "name": name,
            "enabled": True,
            "salt": salt,
            "hash": api_key_hash
        }
        
        # Save to database
        db_id = db_create(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            client_doc
        )
        
        if not db_id:
            business_logger.log_error(
                "client_service",
                "create_client",
                "Failed to create client in database"
            )
            raise RuntimeError("Failed to create client in database")
        
        logger.info("Client created successfully", client_id=client_id, name=name)
        
        # Get the created client document to retrieve full metadata
        from utilities.cosmos_connector import get_document_by_id
        created_client = get_document_by_id(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            db_id
        )
        
        # Return client data (without API key in doc) and API key
        # separately
        client_data = {
            "clientId": client_id,
            "name": name,
            "enabled": True,
            "_metadata": (
                created_client.get("_metadata", {}) if created_client else {}
            )
        }
        
        return client_data, api_key
    
    def list_clients(self) -> list[Dict[str, Any]]:
        """
        List all clients (excluding API keys).
        
        Returns:
            List of client dictionaries
        """
        business_logger.log_operation("client_service", "list_clients")
        
        clients = db_read(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={},
            projection={"clientId": 1, "name": 1, "enabled": 1, "_metadata": 1}
        )
        
        result = []
        for client in clients:
            result.append({
                "clientId": client.get("clientId"),
                "name": client.get("name"),
                "enabled": client.get("enabled", True),
                "_metadata": client.get("_metadata", {})
            })
        
        logger.info("Listed clients", count=len(result))
        return result
    
    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a client by ID.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Client dictionary or None if not found
        """
        business_logger.log_operation("client_service", "get_client", client_id=client_id)
        
        client = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"clientId": client_id},
            projection={"clientId": 1, "name": 1, "enabled": 1, "_metadata": 1}
        )
        
        if not client:
            logger.warning("Client not found", client_id=client_id)
            return None
        
        return {
            "clientId": client.get("clientId"),
            "name": client.get("name"),
            "enabled": client.get("enabled", True),
            "_metadata": client.get("_metadata", {})
        }
    
    def get_client_for_auth(
        self, client_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a client by ID with authentication data (salt and hash).
        
        Used for API key verification.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Client dictionary with salt and hash, or None if not found
        """
        business_logger.log_operation(
            "client_service", "get_client_for_auth", client_id=client_id
        )
        
        client = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"clientId": client_id},
            projection={"clientId": 1, "enabled": 1, "salt": 1, "hash": 1}
        )
        
        if not client:
            logger.warning("Client not found for auth", client_id=client_id)
            return None
        
        if not client.get("enabled", True):
            logger.warning("Client is disabled", client_id=client_id)
            return None
        
        return {
            "clientId": client.get("clientId"),
            "enabled": client.get("enabled", True),
            "salt": client.get("salt"),
            "hash": client.get("hash")
        }
    
    def update_client(
        self,
        client_id: str,
        name: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """
        Update a client's name and/or enabled status.
        
        Args:
            client_id: Client identifier
            name: New name (optional)
            enabled: New enabled status (optional)
            
        Returns:
            True if update successful, False otherwise
        """
        business_logger.log_operation(
            "client_service",
            "update_client",
            client_id=client_id,
            name=name,
            enabled=enabled
        )
        
        # First verify client exists
        client = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"clientId": client_id}
        )
        
        if not client:
            logger.warning("Client not found for update", client_id=client_id)
            return False
        
        # Build update document
        updates = {}
        if name is not None:
            updates["name"] = name
        if enabled is not None:
            updates["enabled"] = enabled
        
        if not updates:
            logger.warning("No updates provided", client_id=client_id)
            return False
        
        # Get the MongoDB _id for the update
        db_id = str(client["_id"])
        
        # Update the client
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            db_id,
            updates
        )
        
        if success:
            logger.info(
                "Client updated successfully",
                client_id=client_id,
                updates=updates
            )
        else:
            logger.error("Failed to update client", client_id=client_id)
        
        return success
    
    def delete_client(self, client_id: str) -> bool:
        """
        Soft delete a client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            True if deletion successful, False otherwise
        """
        business_logger.log_operation(
            "client_service", "delete_client", client_id=client_id
        )
        
        # First verify client exists
        client = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"clientId": client_id}
        )
        
        if not client:
            logger.warning("Client not found for deletion", client_id=client_id)
            return False
        
        # Get the MongoDB _id for the deletion
        from bson import ObjectId
        db_id = str(client["_id"])
        
        # Soft delete the client
        success = db_delete(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            db_id
        )
        
        if success:
            logger.info("Client deleted successfully", client_id=client_id)
        else:
            logger.error("Failed to delete client", client_id=client_id)
        
        return success
    
    def toggle_client_enabled(self, client_id: str) -> Optional[bool]:
        """
        Toggle the enabled status of a client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            New enabled status, or None if client not found
        """
        business_logger.log_operation(
            "client_service", "toggle_client_enabled", client_id=client_id
        )
        
        # Get current client
        client = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"clientId": client_id}
        )
        
        if not client:
            logger.warning("Client not found for toggle", client_id=client_id)
            return None
        
        # Toggle enabled status
        new_enabled = not client.get("enabled", True)
        
        # Get the MongoDB _id for the update
        db_id = str(client["_id"])
        
        # Update the client
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            db_id,
            {"enabled": new_enabled}
        )
        
        if success:
            logger.info(
                "Client enabled status toggled",
                client_id=client_id,
                enabled=new_enabled
            )
            return new_enabled
        else:
            logger.error("Failed to toggle client enabled status", client_id=client_id)
            return None
    
    def rotate_client_key(
        self, client_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Rotate a client's API key (generate new salt and key, update hash).
        
        Args:
            client_id: Client identifier
            
        Returns:
            Tuple of (client_id, api_key) or (None, None) if client not found
        """
        business_logger.log_operation(
            "client_service", "rotate_client_key", client_id=client_id
        )
        
        # Get current client
        client = db_find_one(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            query={"clientId": client_id}
        )
        
        if not client:
            logger.warning("Client not found for key rotation", client_id=client_id)
            return None, None
        
        # Generate new salt and API key
        new_api_key = self.generate_api_key()
        new_salt = self.generate_salt()
        
        # Hash the new API key with salt and pepper
        new_hash = self.hash_api_key(new_api_key, new_salt, self.pepper)
        
        # Get the MongoDB _id for the update
        db_id = str(client["_id"])
        
        # Update the client with new salt and hash
        success = db_update(
            self.mongo_client,
            self.db_name,
            self.collection_name,
            db_id,
            {
                "salt": new_salt,
                "hash": new_hash
            }
        )
        
        if success:
            logger.info("Client key rotated successfully", client_id=client_id)
            return client_id, new_api_key
        else:
            logger.error("Failed to rotate client key", client_id=client_id)
            return None, None


# Singleton instance
_client_service: Optional[ClientService] = None


def get_client_service() -> ClientService:
    """Get or create the singleton client service instance"""
    global _client_service
    if _client_service is None:
        _client_service = ClientService()
    return _client_service

