from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from typing import Dict, List, Optional, Tuple
from opti_inqueue_handler import build_client_reference, write_queue
from utilities.cosmos_connector import db_find_one

from dataclasses import dataclass
from enum import Enum


class IterationState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"

@dataclass
class IterationContext:
    test_id: str
    run_id: str
    iteration: int
    max_iterations: int
    models: Dict[str, str]
    temperature: float
    input_text: Optional[Dict]

def get_iteration_count(mongo_client, db_name: str, test_id: str, run_combi: str) -> int:
    """Get the number of completed iterations with improved error handling."""
    try:
        doc = db_find_one(mongo_client, db_name, "runs", {"test_id": test_id})
        if not doc:
            logger.warning(f"No document found for test_id: {test_id}")
            return 0

        for run in doc.get("runs", []):
            if run.get("run") == run_combi:
                iterations = run.get("iterations", [])
                # Only count completed iterations
                return len([it for it in iterations if it.get("status") == "complete"])
        return 0

    except Exception as e:
        logger.error(f"Failed to get iteration count: {str(e)}")
        return 0

def iterations_loop(
    mongo_client,
    db_name: str,
    test_id: str,
    run_combi: str,
    combo: Dict[str, str],
    input_text: Optional[Dict] = None,
    max_iterations: int = 5,
    temperature: float = 1.0,
) -> Tuple[Optional[Dict], Optional[List[Dict]], Optional[str]]:
    """Execute iterations loop with improved state management and validation."""
    try:
        # Create iteration context
        context = IterationContext(
            test_id=test_id,
            run_id=run_combi,
            iteration=get_iteration_count(mongo_client, db_name, test_id, run_combi),
            max_iterations=max_iterations,
            models=combo,
            temperature=temperature,
            input_text=input_text
        )

        # Validate context
        if not input_text:
            raise ValueError("Input text is required for optimization")

        if not all(model in combo for model in ["core_model", "assessment_model", "meta_model"]):
            raise ValueError("Missing required models in combo")

        if context.iteration >= max_iterations:
            logger.info(f"↪️ Skipping {run_combi}, already completed {context.iteration}/{max_iterations} iterations.")
            return None, None, None

        # Update iteration count and create queue ID
        context.iteration += 1
        queue_id = f"{test_id}.{run_combi}.{context.iteration}"

        # Build client reference with state
        client_reference = build_client_reference(
            mongo_client=mongo_client,
            db_name=db_name,
            test_id=test_id,
            input_text=input_text,
            run_id=run_combi,
            iteration_index=context.iteration,
            models=combo,
            max_iteration=max_iterations
        )

        # Get or create prompt
        prompt =  [{
                "promptName": "base_prompt",
                "promptVersion": test_id,
                "promptType": "system"
            }
        ]
        # Queue job with state tracking
        write_queue(
            mongo_client=mongo_client,
            queue_id=queue_id,
            data=input_text,
            client_reference={
                **client_reference,
                "state": IterationState.IN_PROGRESS.value
            },
            prompts_array=prompt,
            operation="processing",
            model=combo["core_model"],
            temperature=temperature,
        )

        logger.info(f"🧠 Added iteration {context.iteration}/{max_iterations} for {run_combi} to queue.")

    except Exception as e:
        logger.error(f"Failed to process iteration: {str(e)}", exc_info=True)
        raise
