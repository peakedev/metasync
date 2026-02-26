#!/usr/bin/env python3
"""
Configuration Factory - Centralized configuration management
"""

import os
from typing import Optional
from utilities.keyring_handler import get_secret
from utilities.cosmos_connector import get_mongo_client, db_read


def _model_name_to_attr_name(name: str) -> str:
    """Convert model name to attribute name."""
    attr_name = (
        name.lower().replace("-", "_").replace(".", "_").replace(" ", "_")
    )
    while "__" in attr_name:
        attr_name = attr_name.replace("__", "_")
    return f"{attr_name}_key"


def _key_to_env_var(key: str) -> str:
    """Convert kebab-case key reference to UPPER_SNAKE_CASE env var name."""
    return key.upper().replace("-", "_")


class ConfigFactory:
    """
    Singleton configuration factory.
    
    Provides centralized access to all environment variables.
    """
    _instance: Optional['ConfigFactory'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Always reload configuration from environment variables when
        # available. Fallback to hardcoded default + local keychain for
        # secure development.
        # Add password to keychain with security add-generic-password
        # -a "secret name" -s "service name" -w "secret value" 
        
        # Database configuration
        self.db_name = os.getenv("DB_NAME", "metasync-dev")
        try:
            self.db_connection_string = get_secret(
                "DB_CONNECTION_STRING", "mongodb", self.db_name
            )
        except ValueError:
            raise ValueError("DB Connection String is required")
        
        # LLM Keys (load keys based on DB models)
        try:
            mongo_client = get_mongo_client(self.db_connection_string)
            models = db_read(mongo_client, self.db_name, "models")
    
            for model in models:
                name = model.get("name")
                key = model.get("key")
                service = model.get("service")
                sdk = model.get("sdk")
        
                # Skip loading keys for test SDK models
                if sdk == "test":
                    continue
        
                if name and key and service:
                    attr_name = _model_name_to_attr_name(name)
                    env_var_name = _key_to_env_var(key)
                    try:
                        setattr(
                            self,
                        attr_name,
                        get_secret(env_var_name, service, name)
                    )
                    except Exception as e:
                        print(f"Warning: Could not load key for model '{name}': {e}")
        except Exception as e:
            # Log error but don't fail initialization if models can't be loaded
            print(f"Warning: Could not load models from database: {e}")     
        
        # Client Key Pepper
        self.api_key_pepper = get_secret(
            "API_KEY_PEPPER", "metasync", "api_key_pepper"
        )
        
        # Admin API Key
        self.admin_api_key = get_secret(
            "ADMIN_API_KEY", "metasync", "admin_api_key"
        )
        
        # Documentation authentication from container app secret
        self.docs_user = os.getenv("DOCS_USER", "user")
        try:
            self.docs_secret = get_secret("DOCS_SECRET", "docs", "password")
        except ValueError:
            raise ValueError(
                "DOCS_SECRET environment variable is required for production"
            )
        
        # # Worker configuration
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "10"))
        self.max_items_per_batch = int(os.getenv("MAX_ITEMS_PER_BATCH", "50"))
        self.num_llm_workers = int(os.getenv("NUM_LLM_WORKERS", "10"))
    
    @classmethod
    def reset(cls):
        """Reset the singleton instance for testing"""
        cls._instance = None
    
    def reload(self):
        """Reload configuration from environment variables"""
        self.__init__()
    
    def get_database_config(self) -> dict:
        """Get database configuration as dictionary"""
        return {
            'db_name': self.db_name,
        }
    
    def get_worker_config(self) -> dict:
        """Get worker configuration as dictionary"""
        return {
            'poll_interval': self.poll_interval,
            'max_items_per_batch': self.max_items_per_batch,
            'num_llm_workers': self.num_llm_workers
        }
    
    def get_all_config(self) -> dict:
        """Get all configuration as dictionary"""
        return {
            **self.get_database_config(),
            **self.get_worker_config(),
        }
    
    def get_model_key(
        self, key_ref: str, model_name: str = ""
    ) -> Optional[str]:
        """Get API key for a model using its key reference.

        Args:
            key_ref: The key reference from the model document
                (e.g. 'AZUREAIFOUNDRY_KEY').
            model_name: Optional model name, used as fallback
                to look up the cached attribute from init.

        Returns:
            The API key string or None if not found.
        """
        # Primary: look up env var from the model's key reference
        env_var_name = _key_to_env_var(key_ref)
        value = os.getenv(env_var_name)
        if value:
            return value

        # Fallback: try the cached attribute set during init
        if model_name:
            attr_name = _model_name_to_attr_name(model_name)
            cached = getattr(self, attr_name, None)
            if cached:
                return cached

        return None
    
    def __str__(self):
        """String representation for debugging"""
        return f"ConfigFactory(db_name={self.db_name})"

# Global configuration instance
config = ConfigFactory()
