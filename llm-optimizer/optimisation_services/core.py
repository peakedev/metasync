from typing import Any, Dict, Optional, Tuple, Union
from utils.model_connector import generate_result
import json

def generate_core_result(
    client: Any,
    mdl: Dict[str, str],
    prompt: str,
    content: Union[Dict, str],
    annexes: Optional[Dict[str, Any]] = None,
    temperature: float = 1.0,
    max_tokens: int = 100000
) -> str:
    """
    Run Language Learning Model with given SDK, process and return results.

    Args:
        client: The API client instance for model interaction
        mdl: Dictionary containing model configuration including 'sdk' key
        prompt: System prompt or instruction for the model
        content: Main content to process (dictionary or string)
        annexes: Optional additional context as key-value pairs
        temperature: Sampling temperature (0.0-2.0), higher means more creative
        max_tokens: Maximum number of tokens in the response

    Returns:
        str: Generated result from the model

    Raises:
        ValueError: If invalid parameters are provided
        TypeError: If parameters are of wrong type
        RuntimeError: If model generation fails
    """
    # Input validation
    if not isinstance(mdl, dict) or 'sdk' not in mdl:
        raise ValueError("mdl must be a dictionary containing 'sdk' key")

    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")

    try:
        content_str = (
            json.dumps(content, ensure_ascii=False, indent=2)
            if not isinstance(content, str) else content
        )

        # Initialize messages based on SDK type
        if mdl['sdk'] == "Anthropic":
            messages = [{"role": "user", "content": content_str}]
            system_prompt = prompt
        else:  # OpenAI / Azure OpenAI style
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content_str}
            ]
            system_prompt = None

        # Add annexes if provided
        if annexes:
            for key, value in annexes.items():
                annex_content = (
                    f"Annexes - {key}:\n"
                    f"{json.dumps(value, ensure_ascii=False, indent=2)}"
                )
                messages.append({"role": "user", "content": annex_content})

        # Generate result with appropriate parameters
        return generate_result(
            client=client,
            mdl=mdl,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=(
                system_prompt if mdl['sdk'] == "Anthropic" else None
            )
        )

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid content format: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Error generating result: {str(e)}")
