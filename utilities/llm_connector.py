import time
import json
import threading
from typing import Tuple
from utilities.json_repair import repair_json_comprehensive
from config import config
from llm_sdks.registry import SDKRegistry

def complete_with_model(
    mdl: dict,
    system_prompt: str,
    user_content: str = "",
    temperature: float = 1,
    max_tokens: int = 100000,
    show_timer: bool = True
) -> Tuple[str, int, int, int]:
    """
    Normalize chat completions across Azure Inference and Azure OpenAI.

    Required mdl keys: name, sdk, endpoint, api_version, deployment.
    
    Returns:
        Tuple of (response_text, prompt_tokens, completion_tokens,
        total_tokens)
    """
    model_name = mdl.get("name")
    sdk = mdl.get("sdk")
    max_temperature = mdl.get("maxTemperature", 1)
    min_temperature = mdl.get("minTemperature", 0)
    # Ensure temperature is within the specified range
    temperature = max(min(temperature, max_temperature), min_temperature)
    
    if not (model_name and sdk):
        raise ValueError(
            "Model config is incomplete; need name and sdk."
        )
    
    # Skip API key check for test SDK
    if sdk != "test":
        # Get API key from config using the model name
        api_key = config.get_model_key(model_name)
        if not api_key:
            raise ValueError(
                f"API key not found in config for model '{model_name}'"
            )
    else:
        api_key = None  # Test SDK doesn't need an API key

    # --- timer start (moved from processing_service)
    stop_event = threading.Event()
    timer_thread = None
    start_time = time.time()  # Always define start_time for summary prints

    if show_timer:
        def _show_timer(start_time: float):
            while not stop_event.is_set():
                elapsed = time.time() - start_time
                print(
                    f"\r        ⏳ Input Prompt sent {int(elapsed)}s ago",
                    end=""
                )
                time.sleep(0.1)

        timer_thread = threading.Thread(target=_show_timer, args=(start_time,))
        timer_thread.start()
    # --- end timer start ---

    try:
        # Get SDK implementation from registry
        sdk_impl = SDKRegistry.get_sdk(sdk)
        if sdk_impl is None:
            raise ValueError(f"Unsupported SDK type: {sdk}")
        
        # Call the SDK's complete method
        response_text, prompt_tokens, completion_tokens, total_tokens = sdk_impl.complete(
            config=mdl,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key
        )

    except Exception:

        # Ensure timer stops on errors, then re-raise
        stop_event.set()
        if timer_thread:
            timer_thread.join()
        raise
    finally:
        # Stop timer on both success and error
        if not stop_event.is_set():
            stop_event.set()
            if timer_thread:
                timer_thread.join()

    # Parse and repair JSON response
    try:
        # First try to parse as JSON
        json.loads(response_text)
    except json.JSONDecodeError:
        try:
            # Try to repair the JSON using hardcoded logic
            repaired_json = repair_json_comprehensive(response_text)
            # Validate the repaired JSON
            json.loads(repaired_json)
            response_text = repaired_json
        except json.JSONDecodeError:
            # Return the original response - let the caller handle the error
            pass

    # Summary prints (previously in processing_service) - only in DEBUG
    # mode
    if show_timer:
        print(
            f"\n        ✅ Total time: {time.time() - start_time:.2f} seconds"
        )
        print(
            f"        ✅ Tokens In: {prompt_tokens}, "
            f"Out: {completion_tokens}, Total: {total_tokens}"
        )
        # print("\n     ✅ Response:\n", response_text)

    return (
        response_text,
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )