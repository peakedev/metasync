from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from opti_inqueue_handler import write_queue
from opti_outqueue_handler import write_run
from opti_prompt_handler import update_prompt
from optimisation_services.evaluation import render_text

# Define operation states and transitions
class OperationState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"

class OperationType(str, Enum):
    PROCESS = "process"
    ASSESSMENT = "assessment"
    META_PROMPT = "meta_prompt"

@dataclass
class OperationContext:
    """Context object to track operation state and data"""
    operation_type: OperationType
    client_reference: Dict[str, Any]
    data: Dict[str, Any]
    models: Dict[str, str]
    iteration: int
    max_iteration: int
    test_id: str
    run_id: str
    qid: str
    status: OperationState = OperationState.PENDING

def validate_operation(context: OperationContext) -> bool:
    """Validate operation context before processing"""
    required_fields = {
        OperationType.PROCESS: ["data", "models.core_model"],
        OperationType.ASSESSMENT: ["data.processing", "models.assessment_model"],
        OperationType.META_PROMPT: ["data.evaluation", "models.meta_model"]
    }

    fields = required_fields.get(context.operation_type, [])
    return all(nested_get(context.__dict__, field) for field in fields)

def nested_get(dict_obj: Dict, key_path: str) -> Any:
    """Safely get nested dictionary values"""
    keys = key_path.split('.')
    for key in keys:
        if not isinstance(dict_obj, dict) or key not in dict_obj:
            return None
        dict_obj = dict_obj[key]
    return dict_obj

def process_operation(operation: Dict[str, Any], client) -> None:
    """Main operation processor with improved error handling"""
    try:
        # Create operation context
        # Support both old "data" and new "responseData" field names
        response_data = operation.get(
            "responseData", operation.get("data", {})
        )
        client_ref = operation.get("clientReference", {})
        context = OperationContext(
            operation_type=OperationType(client_ref.get("operation")),
            client_reference=client_ref,
            data=response_data,
            models=client_ref.get("models", {}),
            iteration=client_ref.get("iteration", 0),
            max_iteration=client_ref.get("max_iteration", 0),
            test_id=client_ref.get("test_id"),
            run_id=client_ref.get("run_id"),
            qid=client_ref.get("qid")
        )

        # Validate operation
        if not validate_operation(context):
            raise ValueError(
                f"Invalid operation context for {context.operation_type}"
            )

        # Process based on type
        handlers = {
            OperationType.PROCESS: handle_processing,
            OperationType.ASSESSMENT: handle_assessment,
            OperationType.META_PROMPT: handle_metaprompt
        }

        handler = handlers.get(context.operation_type)
        if not handler:
            raise ValueError(
                f"Unknown operation type: {context.operation_type}"
            )

        handler(context, client)

    except Exception as e:
        logger.error(f"Operation processing failed: {str(e)}", exc_info=True)
        # Update operation status to failed
        if context:
            context.status = OperationState.FAILED
            context.client_reference.update({
            "placeholders": {
                "status": context.status
            }
        })
            context.status = OperationState.FAILED
            write_run(context.test_id, context.run_id, context.data, client)
        raise

def handle_processing(context: OperationContext, client) -> None:
    """Handle processing operation with improved error handling"""
    try:
        # Update status
        context.status = OperationState.IN_PROGRESS

        # Process content
        processed_json = nested_get(context.data, "processing.fr.content")
        if not processed_json:
            raise ValueError("Missing processing content")

        rendered_output = render_text(processed_json)

        # Update client reference
        context.client_reference.update({
            "operation": OperationType.ASSESSMENT.value,
            "placeholders": {
                "output_json": processed_json,
                "output_rendered": rendered_output,
                "status": OperationState.IN_PROGRESS.value
            }
        })

        # Queue assessment job
        write_queue(
            client,
            context.qid,
            data=rendered_output,
            client_reference=context.client_reference,
            operation=OperationType.ASSESSMENT.value,
            model=context.models.get("assessment_model"),
            prompts_array=[{
                "name": "assessment",
                "version": context.test_id,
                "type": "system"
            }]
        )

    except Exception as e:
        context.status = OperationState.FAILED
        logger.error(f"Processing handling failed: {str(e)}", exc_info=True)
        raise

def handle_assessment(context: OperationContext, client) -> None:
    """
    Handle assessment operation and transition to meta prompt if needed.

    Args:
        context: Operation context containing assessment data
        client: MongoDB client instance
    """
    try:
        # Update status
        context.status = OperationState.IN_PROGRESS

        # Extract and validate assessment data
        evaluation_data = nested_get(context.data, "evaluation")
        if not evaluation_data:
            raise ValueError("Missing evaluation data")

        feedback_summary = evaluation_data.get("errors", [])
        avg_score = evaluation_data.get("total_score")

        # Update client reference with assessment results
        context.client_reference.update({
            "assessment": evaluation_data,
            "AVG_total_score": avg_score,
            "new_metaprompt": feedback_summary,
        })

        # Write assessment results
        write_run(context.test_id, context.run_id, context.data, client)

        # Check if max iterations reached
        if context.iteration >= context.max_iteration:
            context.status = OperationState.COMPLETE
            context.client_reference["status"] = "complete"
            write_run(context.test_id, context.run_id, context.data, client)
            return

        # Prepare for next iteration
        next_iteration = context.iteration + 1
        next_qid = f"{context.test_id}.{context.run_id}.{next_iteration}"

        # Update prompt with feedback
        update_prompt(
            client=client,
            prompt_text=feedback_summary,
            version=next_qid,
            prompt_name="meta_prompt",
            prompt_type="system"
        )

        # Queue meta prompt job
        write_queue(
            mongo_client=client,
            queue_id=next_qid,
            data=context.client_reference.get("placeholders", {}).get("last_input_prompt", ""),
            client_reference=context.client_reference,
            prompts_array=[
                {
                    "name": "meta_prompt",
                    "version": context.test_id,
                    "type": "system"
                },
                {
                    "name": "meta_prompt",
                    "version": next_qid,
                    "type": "user"
                }
            ],
            operation=OperationType.META_PROMPT.value,
            model=context.models.get("meta_model")
        )

    except Exception as e:
        context.status = OperationState.FAILED
        logger.error(f"Assessment handling failed: {str(e)}", exc_info=True)
        raise

def handle_metaprompt(context: OperationContext, client) -> None:
    """
    Handle meta prompt operation and transition to next processing iteration.

    Args:
        context: Operation context containing meta prompt data
        client: MongoDB client instance
    """
    try:
        # Update status
        context.status = OperationState.IN_PROGRESS

        # Update client reference for next iteration
        context.client_reference.update({
            "operation": OperationType.PROCESS.value,
            "placeholders": {
                "previous_input_prompt": context.client_reference.get("placeholders", {}).get("improved_input_prompt", ""),
                "improved_input_prompt": context.data,
                "status": OperationState.IN_PROGRESS.value
            }
        })

        # Update prompt with improvements
        update_prompt(
            client=client,
            prompt_text=context.data,
            version=context.qid,
            prompt_name="improved_prompt",
            prompt_type="system"
        )

        # Queue next processing job
        write_queue(
            mongo_client=client,
            queue_id=context.qid,
            data=context.client_reference.get("input", ""),
            client_reference=context.client_reference,
            prompts_array=[{
                "name": "improved_prompt",
                "version": context.qid,
                "type": "system"
            }],
            operation=OperationType.PROCESS.value,
            model=context.models.get("core_model")
        )

    except Exception as e:
        context.status = OperationState.FAILED
        logger.error(f"Meta prompt handling failed: {str(e)}", exc_info=True)
        raise
