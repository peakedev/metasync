# LLM SDK Plugin System

A modular, extensible architecture for integrating multiple LLM SDKs in MetaSync. Each SDK is implemented as a separate plugin that inherits from `BaseLLMSDK`.

## Architecture Overview

The SDK system consists of three main components:

1. **Base SDK Interface** (`base_sdk.py`) - Abstract base class defining the interface all SDKs must implement
2. **SDK Registry** (`registry.py`) - Auto-discovers and manages SDK implementations
3. **Individual SDK Implementations** - One file per SDK, named after the SDK identifier

### How It Works

1. Each SDK is implemented in its own Python file in the `llm-sdks/` directory
2. The filename matches the SDK identifier (e.g., `ChatCompletionsClient.py`, `AzureOpenAI.py`)
3. The registry automatically discovers and loads all SDK implementations at runtime
4. The `llm_connector.py` uses the registry to dynamically dispatch requests to the appropriate SDK

## Supported SDKs

Currently supported SDKs:

- **ChatCompletionsClient** - Azure AI Inference SDK
- **AzureOpenAI** - Azure OpenAI API via official OpenAI SDK
- **Anthropic** - Anthropic Claude API with streaming support
- **test** - Mock SDK for testing (no API calls)

## Adding a New SDK

Follow these steps to add support for a new LLM SDK:

### Step 1: Create SDK Implementation File

Create a new Python file in `/llm-sdks/` named exactly as the SDK identifier (e.g., `MySdk.py` for SDK name "MySdk").

```python
"""
Your SDK Name

Brief description of what this SDK does.
"""

from typing import Tuple, Dict, Any
from llm_sdks.base_sdk import BaseLLMSDK

# Import your SDK's client library here
# from your_sdk import Client


class YourSDKClass(BaseLLMSDK):
    """Your SDK implementation with descriptive docstring."""
    
    def get_name(self) -> str:
        """
        Return the SDK name as stored in the database.
        
        This MUST match exactly what's in the 'sdk' field of model documents.
        """
        return "MySdk"  # This becomes the SDK identifier
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate SDK-specific configuration requirements.
        
        Check that all required fields for this SDK are present.
        Raise ValueError with a descriptive message if validation fails.
        """
        required_fields = ['endpoint', 'apiVersion', 'deployment']
        missing_fields = [field for field in required_fields if not config.get(field)]
        
        if missing_fields:
            raise ValueError(
                f"MySdk requires the following fields: {', '.join(missing_fields)}"
            )
        
        # Add any additional validation logic here
        # For example, validate endpoint format, check version compatibility, etc.
    
    def complete(
        self,
        config: Dict[str, Any],
        system_prompt: str,
        user_content: str,
        temperature: float,
        max_tokens: int,
        api_key: str = None
    ) -> Tuple[str, int, int, int]:
        """
        Execute a chat completion request.
        
        Args:
            config: Model configuration dictionary with fields like:
                   - name: Model name
                   - endpoint: API endpoint URL
                   - apiVersion: API version string
                   - deployment: Deployment/model identifier
                   - maxTemperature, minTemperature: Temperature limits (handled by llm_connector)
            system_prompt: System prompt/instruction for the model
            user_content: User message content
            temperature: Sampling temperature (already clamped to min/max by llm_connector)
            max_tokens: Maximum tokens to generate
            api_key: API key for authentication (None for test SDKs)
            
        Returns:
            Tuple of (response_text, prompt_tokens, completion_tokens, total_tokens)
            
        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If the API call fails or returns empty response
        """
        # 1. Validate configuration
        self.validate_config(config)
        
        # 2. Extract configuration values
        endpoint = config.get('endpoint')
        api_version = config.get('apiVersion')
        deployment = config.get('deployment')
        
        # 3. Initialize your SDK client
        # client = Client(
        #     endpoint=endpoint,
        #     api_key=api_key,
        #     api_version=api_version
        # )
        
        # 4. Prepare messages/prompts according to your SDK's format
        # Some SDKs combine system + user into one message
        # Others separate them (like Anthropic)
        
        # 5. Make the API call
        # response = client.complete(
        #     model=deployment,
        #     messages=[...],
        #     temperature=temperature,
        #     max_tokens=max_tokens
        # )
        
        # 6. Extract response text
        # response_text = response.choices[0].message.content
        
        # 7. Validate response is not empty
        # if response_text is None:
        #     raise RuntimeError("MySdk returned empty response content.")
        
        # 8. Extract token usage
        # Different SDKs use different field names for token counts
        # prompt_tokens = response.usage.input_tokens  # or prompt_tokens
        # completion_tokens = response.usage.output_tokens  # or completion_tokens
        # total_tokens = prompt_tokens + completion_tokens
        
        # 9. Return standardized tuple
        # return (
        #     response_text,
        #     prompt_tokens,
        #     completion_tokens,
        #     total_tokens,
        # )
        
        # Example placeholder return
        raise NotImplementedError("Complete this implementation")
```

### Step 2: Install Required Dependencies

Add any SDK-specific dependencies to `requirements.txt`:

```bash
# Add to requirements.txt
your-sdk-package>=1.0.0
```

### Step 3: Test Your Implementation

Create a test model in the database with your SDK configuration:

```json
{
  "name": "my-test-model",
  "sdk": "MySdk",
  "endpoint": "https://api.example.com",
  "apiType": "mytype",
  "apiVersion": "2024-01-01",
  "deployment": "my-deployment",
  "service": "my-service",
  "key": "MY_API_KEY",
  "maxToken": 100000,
  "minTemperature": 0,
  "maxTemperature": 1,
  "cost": {
    "tokens": 1000,
    "currency": "USD",
    "input": 0.001,
    "output": 0.002
  }
}
```

### Step 4: Verify Auto-Discovery

Your SDK should be automatically discovered by the registry. You can verify with:

```python
from llm_sdks.registry import SDKRegistry

# List all available SDKs
print(SDKRegistry.list_sdks())  # Should include "MySdk"

# Get your SDK instance
sdk = SDKRegistry.get_sdk("MySdk")
print(sdk.get_name())  # Should print "MySdk"
```

## SDK Interface Requirements

All SDKs MUST implement the following methods:

### `get_name() -> str`

Returns the SDK identifier as a string. This MUST match:
- The filename (minus `.py` extension)
- The `sdk` field value in model database documents
- The name used when creating models via the API

### `validate_config(config: Dict[str, Any]) -> None`

Validates SDK-specific configuration. Should raise `ValueError` with a clear message if validation fails.

Common fields to validate:
- `endpoint` - API endpoint URL
- `apiVersion` - API version string
- `deployment` - Model/deployment identifier

### `complete(...) -> Tuple[str, int, int, int]`

Executes the completion request and returns a standardized tuple.

**Parameters:**
- `config` - Full model configuration dictionary
- `system_prompt` - System-level instructions
- `user_content` - User message content
- `temperature` - Sampling temperature (already validated and clamped)
- `max_tokens` - Maximum tokens to generate
- `api_key` - Authentication key (or None for test SDKs)

**Returns:**
Tuple of `(response_text, prompt_tokens, completion_tokens, total_tokens)`

**Important Notes:**
- Temperature is already clamped to `minTemperature`/`maxTemperature` by `llm_connector`
- The timer, JSON repair, and error handling are handled by `llm_connector`
- Your implementation only needs to focus on the API call itself

## Best Practices

### 1. Error Handling

Always provide clear error messages:

```python
if not api_key:
    raise ValueError("MySdk requires an API key for authentication")

if response is None:
    raise RuntimeError("MySdk returned empty response content.")
```

### 2. Message Formatting

Different SDKs handle system prompts differently:

**Combined approach** (ChatCompletionsClient, AzureOpenAI):
```python
content = (system_prompt or "") + (user_content or "")
messages = [{"role": "system", "content": content}]
```

**Separated approach** (Anthropic):
```python
# System prompt goes to a separate parameter
messages = [{"role": "user", "content": user_content or ""}]
# Then pass system_prompt separately to the API call
```

### 3. Token Count Mapping

Different SDKs use different field names. Map them to our standard:

```python
# Azure SDKs
prompt_tokens = usage.prompt_tokens
completion_tokens = usage.completion_tokens
total_tokens = usage.total_tokens

# Anthropic
prompt_tokens = usage.input_tokens
completion_tokens = usage.output_tokens
total_tokens = prompt_tokens + completion_tokens
```

### 4. Streaming Support

For long-running requests, consider using streaming APIs if available:

```python
# Example: Anthropic streaming
response_parts = []
with client.messages.stream(...) as stream:
    for text in stream.text_stream:
        response_parts.append(text)
    final_msg = stream.get_final_message()
response_text = "".join(response_parts)
```

### 5. Configuration Validation

Be strict about required fields but flexible about optional ones:

```python
def validate_config(self, config: Dict[str, Any]) -> None:
    # Required fields
    required = ['endpoint', 'deployment']
    missing = [f for f in required if not config.get(f)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    
    # Optional validation
    endpoint = config.get('endpoint', '')
    if not endpoint.startswith('https://'):
        raise ValueError("Endpoint must use HTTPS")
```

## Testing Your SDK

### Unit Testing

Test your SDK implementation independently:

```python
# test_my_sdk.py
from llm_sdks.MySdk import YourSDKClass

def test_validate_config():
    sdk = YourSDKClass()
    
    # Should pass
    sdk.validate_config({
        'endpoint': 'https://api.example.com',
        'deployment': 'my-model'
    })
    
    # Should fail
    try:
        sdk.validate_config({'endpoint': 'https://api.example.com'})
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
```

### Integration Testing

Test with the full system using the test SDK as a reference:

1. Create a model with your SDK in the database
2. Create a job that uses your model
3. Run a worker to process the job
4. Verify the response and token counts

## Troubleshooting

### SDK Not Discovered

If your SDK doesn't appear in `SDKRegistry.list_sdks()`:

1. Check that the filename matches the SDK name returned by `get_name()`
2. Verify the class inherits from `BaseLLMSDK`
3. Check for syntax errors in your file
4. Restart the application to force re-discovery

### Import Errors

If you get import errors:

1. Ensure all required packages are installed (`pip install -r requirements.txt`)
2. Check that the `llm_sdks` directory has an `__init__.py` file
3. Verify your import statements are correct

### Validation Errors

If model creation fails with validation errors:

1. Check that `get_name()` returns the exact string used in the database
2. Verify all required fields are present in the model configuration
3. Check field name casing (e.g., `apiVersion` vs `api_version`)

## Architecture Benefits

This plugin architecture provides several benefits:

1. **Modularity** - Each SDK is self-contained and independent
2. **Extensibility** - Add new SDKs without modifying core code
3. **Maintainability** - SDK-specific logic stays in SDK files
4. **Testability** - Each SDK can be tested independently
5. **Auto-discovery** - No need to manually register new SDKs
6. **Zero-impact** - Adding SDKs doesn't affect existing ones

## Migration Notes

For developers familiar with the old system:

### Before (Hardcoded if-elif)
```python
if sdk == "ChatCompletionsClient":
    client = ChatCompletionsClient(...)
    response = client.complete(...)
elif sdk == "AzureOpenAI":
    client = AzureOpenAI(...)
    response = client.chat.completions.create(...)
# ... many more elif blocks
```

### After (Plugin System)
```python
sdk_impl = SDKRegistry.get_sdk(sdk)
response_text, prompt_tokens, completion_tokens, total_tokens = sdk_impl.complete(...)
```

All SDK-specific logic is now encapsulated in individual SDK files, making the codebase more maintainable and extensible.

## Support

For questions or issues with SDK development, please:

1. Review existing SDK implementations for reference
2. Check this documentation for best practices
3. Test with the `test` SDK to verify your setup
4. Consult the team for API-specific questions

