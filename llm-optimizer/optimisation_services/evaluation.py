from typing import Dict, List, Any, Tuple, TypedDict
from utils.model_connector import generate_result
from processing.rendered_text import render_text
import json
import logging
from enum import Enum

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EvalType(Enum):
    STYLE = "style"
    CONTENT = "content"

class MetaData(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    run_time: float

def create_meta_data() -> MetaData:
    """Create initial metadata structure."""
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "run_time": 0
    }

def update_meta_data(base: MetaData, new: Dict[str, int]) -> MetaData:
    """Update metadata with new values."""
    return {
        key: base[key] + new.get(key, 0)
        for key in base.keys()
    }

def prepare_assessment_variables(
    original: Dict[str, Any],
    output_json: Dict[str, Any],
    eval_param: Dict[str, Any],
    rendered: bool = False
) -> Dict[str, str]:
    """Prepare variables for assessment based on evaluation type."""
    if eval_param["evalType"] == EvalType.STYLE.value and rendered:
        rendered_output = render_text(output_json)
        return {
            "output": rendered_output,
            "evalVariables": json.dumps(eval_param["evalVariables"], ensure_ascii=False, indent=2)
        }

    return {
        "original": json.dumps(original, ensure_ascii=False, indent=2),
        "output": json.dumps(output_json, ensure_ascii=False, indent=2),
        "evalVariables": json.dumps(eval_param["evalVariables"], ensure_ascii=False, indent=2)
    }

def run_single_assessment(
    client: Any,
    model: str,
    prompt_template: str,
    variables: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run a single assessment with error handling."""
    try:
        formatted_prompt = prompt_template.format(**variables)
        messages = [{"role": "user", "content": formatted_prompt}]
        return generate_result(client, model, messages)
    except KeyError as e:
        logger.error(f"Missing variable for prompt: {e}")
        raise ValueError(f"Missing variable for prompt: {e}")
    except Exception as e:
        logger.error(f"Assessment failed: {str(e)}")
        raise

def run_assessments(
    client_eval: Any,
    model_eval: str,
    original: Dict[str, Any],
    output_json: Dict[str, Any],
    eval_params: List[Dict[str, Any]],
    rendered: bool = False
) -> Tuple[List[Dict[str, Any]], MetaData]:
    """Run multiple assessments and aggregate results."""
    results = []
    meta_data = create_meta_data()

    for param in eval_params:
        try:
            variables = prepare_assessment_variables(
                original,
                output_json,
                param,
                rendered
            )

            eval_result, eval_meta = run_single_assessment(
                client_eval,
                model_eval,
                param["evalPrompt"],
                variables
            )

            results.append({
                "evalType": param["evalType"],
                **{k: eval_result.get(k, None) for k in param["evalVariables"].keys()},
                "evalWeight": param.get("evalWeight", 1)
            })

            meta_data = update_meta_data(meta_data, eval_meta)

        except Exception as e:
            logger.error(f"Failed to process evaluation parameter: {str(e)}")
            continue

    return results, meta_data
