"""
Utilities - Core utility modules for database, LLM, and JSON operations

This package provides shared utilities for:
- Database connections and operations (cosmos_connector)
- LLM API integrations (llm_connector)
- JSON repair and validation (json_repair)
- Secure credential management (keyring_handler)

Note: Imports are available but not eagerly loaded to avoid circular dependencies.
Import directly from submodules as needed:
    from utilities.cosmos_connector import get_mongo_client
    from utilities.llm_connector import complete_with_model
    from utilities.json_repair import repair_json_comprehensive
    from utilities.keyring_handler import get_secret
"""

__all__ = [
    # Database operations
    "get_mongo_client",
    "ClientManager",
    "db_create",
    "db_read",
    "db_update",
    "db_delete",
    "db_find_one",
    "get_document_by_id",
    "safe_operation",
    # LLM operations
    "complete_with_model",
    # JSON utilities
    "repair_json_comprehensive",
    "validate_json",
    # Security
    "get_secret"
]

__version__ = "1.0.0"


# Lazy imports to avoid circular dependencies
def __getattr__(name):
    """Lazy import utilities to avoid circular dependencies with config."""
    if name == "get_mongo_client":
        from utilities.cosmos_connector import get_mongo_client
        return get_mongo_client
    elif name == "ClientManager":
        from utilities.cosmos_connector import ClientManager
        return ClientManager
    elif name == "db_create":
        from utilities.cosmos_connector import db_create
        return db_create
    elif name == "db_read":
        from utilities.cosmos_connector import db_read
        return db_read
    elif name == "db_update":
        from utilities.cosmos_connector import db_update
        return db_update
    elif name == "db_delete":
        from utilities.cosmos_connector import db_delete
        return db_delete
    elif name == "db_find_one":
        from utilities.cosmos_connector import db_find_one
        return db_find_one
    elif name == "get_document_by_id":
        from utilities.cosmos_connector import get_document_by_id
        return get_document_by_id
    elif name == "safe_operation":
        from utilities.cosmos_connector import safe_operation
        return safe_operation
    elif name == "complete_with_model":
        from utilities.llm_connector import complete_with_model
        return complete_with_model
    elif name == "repair_json_comprehensive":
        from utilities.json_repair import repair_json_comprehensive
        return repair_json_comprehensive
    elif name == "validate_json":
        from utilities.json_repair import validate_json
        return validate_json
    elif name == "get_secret":
        from utilities.keyring_handler import get_secret
        return get_secret
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

