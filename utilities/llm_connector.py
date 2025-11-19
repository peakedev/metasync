import os
import time
import json
import threading
from typing import Tuple
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference import ChatCompletionsClient
from azure.core.pipeline.transport import RequestsTransport
from openai import AzureOpenAI
from anthropic import Anthropic
from urllib.parse import urlparse
from json_repair import repair_json_comprehensive
from config import config

# Centralize timeouts for both SDKs
_transport = RequestsTransport(
    connection_timeout=1000,
    read_timeout=1000,
)

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
    endpoint = mdl.get("endpoint")
    api_version = mdl.get("apiVersion")
    deployment = mdl.get("deployment")
    max_temperature = mdl.get("maxTemperature", 1)
    min_temperature = mdl.get("minTemperature", 0)
    # Ensure temperature is within the specified range
    temperature = max(min(temperature, max_temperature), min_temperature)
    
    if not (model_name and sdk and endpoint and api_version and deployment):
        raise ValueError(
            "Model config is incomplete; need name, sdk, endpoint, "
            "apiVersion, deployment."
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

    content = (system_prompt or "") + (user_content or "")
    messages = [{"role": "system", "content": content}]

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
        if sdk == "ChatCompletionsClient":
            client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
                transport=_transport,
            )
            response = client.complete(
                model=deployment,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response_text = response.choices[0].message["content"]
            usage = response.usage

        elif sdk == "AzureOpenAI":
            client = AzureOpenAI(
                api_version=api_version,
                azure_endpoint=endpoint,
                api_key=api_key,
            )
            response = client.chat.completions.create(
                model=deployment,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_tokens,
            )
            response_text = response.choices[0].message.content
            usage = response.usage

        elif sdk == "Anthropic":
            # Anthropic Claude via official SDK (https://api.anthropic.com)
            # Use streaming to avoid the 10-minute cap for long requests.
            client = Anthropic(api_key=api_key, base_url=endpoint)

            # Sanity check: Anthropic must use
            # https://api.anthropic.com
            try:
                host = urlparse(endpoint).netloc.lower()
            except Exception:
                host = ""
            if "anthropic.com" not in host:
                raise ValueError(
                    f"\nInvalid Anthropic endpoint '{endpoint}'. "
                    f"Use 'https://api.anthropic.com'."
                )

            # Anthropic separates `system` and `messages`. Keep system in
            # `system_prompt` and send user content as a user message.
            anthro_messages = [{"role": "user", "content": user_content or ""}]

            # Stream the response so long-running generations don't hit the
            # SDK's 10-minute non-streaming limit.
            response_text_parts = []
            try:
                with client.messages.stream(
                    model=deployment,  # e.g., "claude-3-7-sonnet-20250219"
                    system=system_prompt or "",
                    messages=anthro_messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                ) as stream:
                    for text in stream.text_stream:
                        response_text_parts.append(text)
                    final_msg = stream.get_final_message()
            except Exception as e:
                # Add helpful hints for common 404 causes
                print(f"            ❌ Error during Anthropic request:")
                raise

            response_text = (
                "".join(response_text_parts) if response_text_parts else None
            )

            # Usage mapping
            usage = getattr(final_msg, "usage", None)
            prompt_tokens = (
                getattr(usage, "input_tokens", None) if usage else None
            )
            completion_tokens = (
                getattr(usage, "output_tokens", None) if usage else None
            )
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        elif sdk == "test":
            # Fake test SDK that returns a dummy response without making API calls
            # Returns valid JSON for better compatibility with processing logic
            response_text = '{"test": "response", "message": "This is a dummy response from the test SDK"}'
            
            # Create a simple object to mimic usage structure
            class FakeUsage:
                prompt_tokens = 1
                completion_tokens = 1
                total_tokens = 2
            
            usage = FakeUsage()

        else:
            raise ValueError(f"Unsupported SDK type: {sdk}")

        if response_text is None:
            raise RuntimeError("LLM returned empty response content.")

        prompt_tokens = (
            getattr(usage, "prompt_tokens", None)
            if sdk != "Anthropic" else prompt_tokens
        )
        completion_tokens = (
            getattr(usage, "completion_tokens", None)
            if sdk != "Anthropic" else completion_tokens
        )
        total_tokens = (
            getattr(usage, "total_tokens", None)
            if sdk != "Anthropic" else total_tokens
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