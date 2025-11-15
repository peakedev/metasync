from typing import Any, Optional
from utils.model_connector import generate_result

def generate_prompt(
    client: Any,
    mdl: str,
    previous_prompt: str,
    meta_prompt: str,
    feedback: Optional[str] = None
) -> str:
    """
    Generates an optimized prompt based on previous prompt and meta-prompt template.

    Args:
        client: The API client instance for model interaction
        mdl: The model identifier to use for generation
        previous_prompt: The original prompt to be optimized
        meta_prompt: Template string containing placeholders for feedback and prompt
        feedback: Optional feedback to incorporate into the optimization

    Returns:
        str: The generated optimized prompt

    Raises:
        ValueError: If meta_prompt doesn't contain required placeholders
        TypeError: If required arguments are of wrong type
    """
    # Validate inputs
    if not isinstance(meta_prompt, str) or not isinstance(previous_prompt, str):
        raise TypeError("meta_prompt and previous_prompt must be strings")

    if "{prompt}" not in meta_prompt or "{feedback}" not in meta_prompt:
        raise ValueError("meta_prompt must contain {prompt} and {feedback} placeholders")

    # Ensure feedback is either string or None
    feedback_str = str(feedback) if feedback is not None else ""

    try:
        messages = [{
            "role": "user",
            "content": meta_prompt.format(
                feedback=feedback_str,
                prompt=previous_prompt,
            )
        }]

        return generate_result(client, mdl, messages, expect_json=False)

    except KeyError as e:
        raise ValueError(f"Invalid placeholder in meta_prompt: {e}")
    except Exception as e:
        raise RuntimeError(f"Error generating prompt: {str(e)}")
