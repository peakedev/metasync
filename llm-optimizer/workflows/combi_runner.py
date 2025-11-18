import itertools
import logging
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities.cosmos_connector import db_find_one, db_update
from workflows.iteration_runner_workers import iterations_loop

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class ModelCombination:
    """Data class for model combination configuration."""
    meta_model: str
    core_model: str
    assessment_model: str

    def to_dict(self) -> Dict[str, str]:
        """Convert combination to dictionary format."""
        return {
            "meta_model": self.meta_model,
            "core_model": self.core_model,
            "assessment_model": self.assessment_model
        }

def generate_sets(*models: str) -> List[ModelCombination]:
    """
    Generate all possible combinations of models.

    Args:
        *models: Variable number of model names

    Returns:
        List of ModelCombination objects representing all possible combinations
    """
    try:
        return [ModelCombination(*combo)
                for combo in itertools.product(models, repeat=3)]

    except Exception as e:
        logger.error(f"Failed to generate model combinations: {str(e)}")
        raise

def ensure_run_exists(
    mongo_client,
    db_name: str,
    test_id: str,
    run_combi: str,
    combo: ModelCombination
) -> None:
    """
    Ensure run configuration exists in database.

    Args:
        mongo_client: MongoDB client instance
        db_name: Name of the database
        test_id: Test identifier
        run_combi: Run combination identifier
        combo: ModelCombination object

    Raises:
        ConnectionError: If database operations fail
    """
    try:
        doc = db_find_one(
            mongo_client, db_name, "runs", {"test_id": test_id},
            {"runs.run": 1}
        )
        if not any(
            run.get("run") == run_combi for run in doc.get("runs", [])
        ):
            log_entry = {
                "run": run_combi,
                **combo.to_dict(),
                "iterations": []
            }
            # Update the existing document to add the new run
            db_update(
                mongo_client,
                db_name,
                "runs",
                str(doc["_id"]),
                {"$push": {"runs": log_entry}}
            )
            logger.info(
                f"Created new run configuration for {run_combi}"
            )
    except Exception as e:
        logger.error(f"Failed to ensure run existence: {str(e)}")
        raise

def batch_loop(
    mongo_client,
    db_name: str,
    test_id: str,
    model1: str,
    model2: str,
    model3: str,
    model4: str,
    input_text: Optional[Dict] = None,
    iterations: int = 5,
    temperature: float = 1.0
) -> None:
    """
    Execute batch processing loop for all model combinations.

    Args:
        mongo_client: MongoDB client instance
        db_name: Name of the database
        test_id: Test identifier
        model1-4: Model names
        input_text: Input text for processing
        annexes: Additional reference materials
        iterations: Number of iterations per combination
        temperature: Temperature parameter for models
        max_tokens: Maximum tokens for processing

    Raises:
        ValueError: If invalid parameters are provided
        ConnectionError: If database operations fail
    """
    try:
        sets = generate_sets(model1, model2, model3, model4)
        total_sets = len(sets)

        for idx, combo in enumerate(sets, 1):
            run_combi = f"run_{idx}"
            logger.info(f"🚀 Starting {run_combi} ({idx}/{total_sets}) with configuration: {combo}")

            ensure_run_exists(mongo_client, db_name, test_id, run_combi, combo)

            try:
                iterations_loop(
                    mongo_client=mongo_client,
                    db_name=db_name,
                    test_id=test_id,
                    run_combi=run_combi,
                    combo=combo.to_dict(),
                    input_text=input_text,
                    max_iterations=iterations,
                    temperature=temperature,
                )
            except Exception as e:
                logger.error(f"Failed during iteration loop for {run_combi}: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Batch loop failed: {str(e)}")
        raise
