import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from pymongo.collection import Collection

from utilities.cosmos_connector import db_create, db_find_one
from opti_prompt_handler import migrate_prompts

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class TestConfig:
    """Data class for test configuration."""
    test_id: str
    base_prompt: str = ""
    meta_prompt: str = ""
    eval_parameters: list = None

    def __post_init__(self):
        """Initialize default values after instantiation."""
        if self.eval_parameters is None:
            self.eval_parameters = []

    def to_dict(self) -> Dict:
        """Convert configuration to dictionary format."""
        return {
            "test_id": self.test_id,
            "base_prompt": self.base_prompt,
            "meta_prompt": self.meta_prompt,
            "eval_parameters": self.eval_parameters,
        }

def init_run_db(mongo_client, db_name: str, test_config: Dict[str, any]) -> str:
    """
    Initialize or update run configuration in database.

    Args:
        mongo_client: MongoDB client instance
        db_name: Name of the database
        test_config: Configuration dictionary containing test parameters

    Returns:
        str: The test_id (potentially modified with version number)

    Raises:
        ValueError: If test_config doesn't contain required fields
        ConnectionError: If database operations fail
    """
    try:
        if not test_config.get("test_id"):
            raise ValueError("test_id is required in test_config")

        config = TestConfig(
            test_id = test_config["test_id"],
            base_prompt=test_config.get("base_prompt", ""),
            meta_prompt=test_config.get("meta_prompt", ""),
            eval_parameters=test_config.get("eval_parameters", [])
        )

        initial_doc = config.to_dict()
        existing = db_find_one(mongo_client, db_name, "runs", {"test_id": config.test_id})

        if existing:
            logger.info(f"Found existing configuration for test_id: {config.test_id}")
            if _needs_update(existing, initial_doc):
                new_test_id = f"{config.test_id}_{1}"
                initial_doc["test_id"] = new_test_id
                initial_doc["runs"] = []
                db_create(mongo_client, db_name, "runs", initial_doc)
                logger.info(f"Created new version with test_id: {new_test_id}")
                migrate_prompts(
                    mongo_client,
                    new_test_id)

                return new_test_id
        else:
            logger.info(f"Creating new configuration for test_id: {config.test_id}")
            initial_doc["runs"] = []
            db_create(mongo_client, db_name, "runs", initial_doc)
            migrate_prompts(
                    mongo_client,
                    config.test_id)

        return config.test_id

    except Exception as e:
        logger.error(f"Failed to initialize run configuration: {str(e)}")
        raise

def _needs_update(existing: Dict, new_config: Dict) -> bool:
    """
    Compare existing and new configurations to determine if update is needed.

    Args:
        existing: Existing configuration dictionary
        new_config: New configuration dictionary

    Returns:
        bool: True if update is needed, False otherwise
    """
    return any(
        key not in existing or existing[key] != value
        for key, value in new_config.items()
    )
