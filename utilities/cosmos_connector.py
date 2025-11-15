from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import OperationFailure
import time
from datetime import datetime
import keyring
import os
import sys
from pathlib import Path
import warnings
import socket
import threading
from typing import Optional, Dict, Any
import urllib.parse

from api.core.logging import get_logger, DatabaseLogger

# Suppress PyMongo warnings for Cosmos DB compatibility
warnings.filterwarnings("ignore", category=UserWarning, module="pymongo")
warnings.filterwarnings("ignore", message=".*CosmosDB.*")
warnings.filterwarnings("ignore", message=".*cosmosdb.*")

db_logger = DatabaseLogger()


class ClientManager:
    # Singleton class that manages MongoDB client instances by connection string.
    # Ensures one client instance per unique connection string is reused across the application.
    # Thread-safe for concurrent access.
    _instance: Optional['ClientManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._clients: Dict[str, MongoClient] = {}
                    cls._instance._client_lock = threading.Lock()
        return cls._instance
    
    def get_client(self, connection_string: str) -> MongoClient:
        # Check if client already exists (fast path, no lock needed)
        if connection_string in self._clients:
            return self._clients[connection_string]
        
        # Need to create new client, acquire lock
        with self._client_lock:
            # Double-check pattern: another thread might have created it while we waited
            if connection_string in self._clients:
                return self._clients[connection_string]
            
            # Create new client and cache it
            client = MongoClient(connection_string)
            self._clients[connection_string] = client
            return client
    
    def close_client(self, connection_string: str) -> bool:

        with self._client_lock:
            if connection_string in self._clients:
                client = self._clients.pop(connection_string)
                client.close()
                return True
            return False
    
    def close_all(self) -> None:
        # Close all cached clients and clear the cache.
        with self._client_lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()

def get_mongo_client(connection_string: str):
    # Create a MongoDB client from connection string.
    
    # Uses ClientManager to cache and reuse clients for the same connection string.
    # This ensures only one client instance per connection string across the entire application.
    
    client_manager = ClientManager()
    return client_manager.get_client(connection_string)

def safe_operation(operation_func, retries=5):
    # Execute a database operation with retry logic for rate limiting.
    for attempt in range(retries):
        try:
            result = operation_func()
            db_logger.log_operation("database_operation", "unknown", attempt=attempt + 1, success=True)
            return result
        except OperationFailure as e:
            if e.code == 16500:  # Rate limited
                wait_time = int(e.details.get("RetryAfterMs", 1000)) / 1000
                db_logger.log_error("database_operation", "unknown", f"Rate limited (429). Waiting {wait_time}s", 
                                  attempt=attempt + 1, wait_time=wait_time)
                time.sleep(wait_time)
            else:
                db_logger.log_error("database_operation", "unknown", str(e), attempt=attempt + 1)
                raise
    db_logger.log_error("database_operation", "unknown", "Too many retries for operation", retries=retries)
    raise RuntimeError("Too many retries for operation")

def db_read(connection_string_or_client, db_name: str, collection_name: str, query: dict = None, limit: int = None, include_deleted: bool = False, projection: dict = None):
    # Read documents from a collection.
    # Can accept either connection string or already-initialized client
    if isinstance(connection_string_or_client, str):
        client_manager = ClientManager()
        mongo_client = client_manager.get_client(connection_string_or_client)
    else:
        mongo_client = connection_string_or_client
    
    db = mongo_client[db_name]
    collection = db[collection_name]
    
    try:
        if query is None:
            query = {}
        
        # Filter out soft-deleted items by default
        if not include_deleted:
            query["_metadata.isDeleted"] = {"$ne": True}
        
        def read_operation():
            cursor = collection.find(query, projection)
            if limit:
                cursor = cursor.limit(limit)
            return list(cursor)
        
        return safe_operation(read_operation)
    except Exception as e:
        print(f"Error reading objects from collection '{collection_name}': {e}")
        return []

def db_find_one(connection_string_or_client, db_name: str, collection_name: str, query: dict = None, projection: dict = None, include_deleted: bool = False):
    # Find a single document from a collection.
    # Can accept either connection string or already-initialized client
    if isinstance(connection_string_or_client, str):
        client_manager = ClientManager()
        mongo_client = client_manager.get_client(connection_string_or_client)
    else:
        mongo_client = connection_string_or_client
    
    db = mongo_client[db_name]
    collection = db[collection_name]
    
    try:
        if query is None:
            query = {}
        
        # Filter out soft-deleted items by default
        if not include_deleted:
            query["_metadata.isDeleted"] = {"$ne": True}
        
        def find_one_operation():
            return collection.find_one(query, projection)
        
        return safe_operation(find_one_operation)
    except Exception as e:
        print(f"Error finding document in collection '{collection_name}': {e}")
        return None

def get_document_by_id(connection_string_or_client, db_name: str, collection_name: str, doc_id: str) -> Optional[dict]:
    # Get a document by its _id.
    try:
        from bson import ObjectId
        return db_find_one(connection_string_or_client, db_name, collection_name, {"_id": ObjectId(doc_id)})
    except Exception as e:
        print(f"Error getting document {doc_id} from {collection_name}: {e}")
        return None

def db_create(connection_string_or_client, db_name: str, collection_name: str, document: dict, user_name: str = None, user_id: str = None):
    # Create a new document in the database.
    # Can accept either connection string or already-initialized client
    if isinstance(connection_string_or_client, str):
        client_manager = ClientManager()
        mongo_client = client_manager.get_client(connection_string_or_client)
    else:
        mongo_client = connection_string_or_client
    
    db = mongo_client[db_name]
    collection = db[collection_name]
    
    try:
        if "_metadata" not in document:
            document["_metadata"] = {}
        
        # Set up standard metadata fields
        document["_metadata"]["isDeleted"] = False
        document["_metadata"]["createdAt"] = datetime.now().isoformat()
        document["_metadata"]["deletedAt"] = None
        document["_metadata"]["updatedAt"] = None
        document["_metadata"]["archivedAt"] = None
        document["_metadata"]["createdBy"] = None
        document["_metadata"]["updatedBy"] = None
        document["_metadata"]["deletedBy"] = None
        
        # Track who created it if user info provided
        if user_name and user_id:
            document["_metadata"]["createdBy"] = {
                "userName": user_name,
                "userId": user_id
            }
        
        def create_operation():
            result = collection.insert_one(document)
            return str(result.inserted_id)
        
        return safe_operation(create_operation)
    except Exception as e:
        print(f"Error creating object in collection '{collection_name}': {e}")
        return None

def db_update(connection_string_or_client, db_name: str, collection_name: str, db_id: str, updates: dict, array_filters: list = None, user_name: str = None, user_id: str = None):
    # Update a document by its _id.
    # Can accept either connection string or already-initialized client
    if isinstance(connection_string_or_client, str):
        client_manager = ClientManager()
        mongo_client = client_manager.get_client(connection_string_or_client)
    else:
        mongo_client = connection_string_or_client
    
    db = mongo_client[db_name]
    collection = db[collection_name]
    
    try:
        from bson import ObjectId
        
        update_doc = {"$set": updates}
        update_doc["$set"]["_metadata.updatedAt"] = datetime.now().isoformat()
        
        # Track who updated it if user info provided
        if user_name and user_id:
            update_doc["$set"]["_metadata.updatedBy"] = {
                "userName": user_name,
                "userId": user_id
            }
        
        def update_operation():
            if array_filters:
                result = collection.update_one(
                    {"_id": ObjectId(db_id)},
                    update_doc,
                    array_filters=array_filters
                )
            else:
                result = collection.update_one(
                    {"_id": ObjectId(db_id)},
                    update_doc
                )
            return result.modified_count > 0
        
        return safe_operation(update_operation)
    except Exception as e:
        print(f"Error updating object {db_id} in collection '{collection_name}': {e}")
        return False

def db_delete(connection_string_or_client, db_name: str, collection_name: str, db_id: str, user_name: str = None, user_id: str = None):
    # Soft delete a document by setting isDeleted = true.
    # Can accept either connection string or already-initialized client
    if isinstance(connection_string_or_client, str):
        client_manager = ClientManager()
        mongo_client = client_manager.get_client(connection_string_or_client)
    else:
        mongo_client = connection_string_or_client
    
    db = mongo_client[db_name]
    collection = db[collection_name]
    
    try:
        from bson import ObjectId
        
        def delete_operation():
            delete_updates = {
                "_metadata.isDeleted": True,
                "_metadata.deletedAt": datetime.now().isoformat(),
                "_metadata.updatedAt": datetime.now().isoformat()
            }
            
            # Track who deleted it if user info provided
            if user_name and user_id:
                delete_updates["_metadata.deletedBy"] = {
                    "userName": user_name,
                    "userId": user_id
                }
            
            result = collection.update_one(
                {"_id": ObjectId(db_id)},
                {"$set": delete_updates}
            )
            return result.modified_count > 0
        
        return safe_operation(delete_operation)
    except Exception as e:
        print(f"Error deleting object {db_id} in collection '{collection_name}': {e}")
        return False

def clear_collection(mongo_client, db_name: str, collection_name: str) -> Dict[str, Any]:
    # Clear all items from a collection.
    try:
        print(f"🧹 Clearing '{collection_name}' collection...")
        
        db = mongo_client[db_name]
        collection = db[collection_name]
        
        # Count before deletion
        def count_operation():
            return collection.count_documents({})
        
        total_count = safe_operation(count_operation)
        print(f"🗑️ Found {total_count} items in '{collection_name}' collection")
        
        if total_count == 0:
            print(f"📭 Collection '{collection_name}' is already empty")
            return {
                "success": True,
                "message": "Collection was already empty",
                "deleted_count": 0
            }
        
        def delete_operation():
            return collection.delete_many({})
        
        result = safe_operation(delete_operation)
        deleted_count = result.deleted_count
        
        print(f"✅ Deleted {deleted_count} items from '{collection_name}' collection")
        
        return {
            "success": True,
            "message": f"Successfully deleted {deleted_count} items",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        print(f"❌ Error clearing '{collection_name}': {e}")
        return {
            "success": False,
            "error": str(e),
            "deleted_count": 0
        }
