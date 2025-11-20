"""
Azure AI Inference SDK (ChatCompletionsClient)

Implementation for Azure's AI Inference SDK using ChatCompletionsClient.
"""

from typing import Tuple, Dict, Any, Generator
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference import ChatCompletionsClient
from azure.core.pipeline.transport import RequestsTransport

from llm_sdks.base_sdk import BaseLLMSDK


# Centralize timeouts for Azure SDK
_transport = RequestsTransport(
    connection_timeout=1000,
    read_timeout=1000,
)


class ChatCompletionsClientSDK(BaseLLMSDK):
    """Azure AI Inference SDK implementation using ChatCompletionsClient."""

    def get_name(self) -> str:
        """Return the SDK name as stored in the database."""
        return "ChatCompletionsClient"

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration for ChatCompletionsClient.

        Required fields:
        - endpoint: API endpoint URL
        - apiVersion: API version string
        - deployment: Deployment name/model identifier
        """
        required_fields = ['endpoint', 'apiVersion', 'deployment']
        missing_fields = [
            field for field in required_fields
            if not config.get(field)
        ]

        if missing_fields:
            msg = (
                "ChatCompletionsClient requires the following "
                f"fields: {', '.join(missing_fields)}"
            )
            raise ValueError(msg)

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
        Execute completion using Azure ChatCompletionsClient.

        Args:
            config: Model configuration with endpoint, apiVersion,
                    and deployment
            system_prompt: System prompt to send
            user_content: User content to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: Azure API key

        Returns:
            Tuple of (response_text, prompt_tokens, completion_tokens,
                      total_tokens)
        """
        # Validate config
        self.validate_config(config)

        endpoint = config.get('endpoint')
        api_version = config.get('apiVersion')
        deployment = config.get('deployment')

        # Combine system prompt and user content into a single message
        content = (system_prompt or "") + (user_content or "")
        messages = [{"role": "system", "content": content}]

        # Create client
        client = ChatCompletionsClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
            api_version=api_version,
            transport=_transport,
        )

        # Make the API call
        response = client.complete(
            model=deployment,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Extract response and usage
        response_text = response.choices[0].message["content"]
        usage = response.usage

        if response_text is None:
            msg = "ChatCompletionsClient returned empty response content."
            raise RuntimeError(msg)

        # Extract token counts
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)

        return (
            response_text,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

    def stream(
        self,
        config: Dict[str, Any],
        system_prompt: str,
        user_content: str,
        temperature: float,
        max_tokens: int,
        api_key: str = None
    ) -> Generator[str, None, Tuple[int, int, int]]:
        """
        Execute streaming completion using Azure ChatCompletionsClient.

        Args:
            config: Model configuration with endpoint, apiVersion,
                    and deployment
            system_prompt: System prompt to send
            user_content: User content to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: Azure API key

        Yields:
            Text chunks as they arrive from the API

        Returns:
            Tuple of (prompt_tokens, completion_tokens, total_tokens)
        """
        # Validate config
        self.validate_config(config)

        endpoint = config.get('endpoint')
        api_version = config.get('apiVersion')
        deployment = config.get('deployment')

        # Combine system prompt and user content into a single message
        content = (system_prompt or "") + (user_content or "")
        messages = [{"role": "system", "content": content}]

        # Create client
        client = ChatCompletionsClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
            api_version=api_version,
            transport=_transport,
        )

        # Make the streaming API call
        response = client.complete(
            model=deployment,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        # Stream the response chunks
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    yield delta.content
            
            # Extract usage from the final chunk if available
            if hasattr(chunk, 'usage') and chunk.usage:
                prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                completion_tokens = getattr(chunk.usage, "completion_tokens", 0)
                total_tokens = getattr(chunk.usage, "total_tokens", 0)

        return (prompt_tokens, completion_tokens, total_tokens)
