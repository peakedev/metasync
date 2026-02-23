"""
Azure OpenAI SDK

Implementation for Azure OpenAI API using the official OpenAI Python SDK.
"""

import threading
from typing import Tuple, Dict, Any, Generator
from openai import AzureOpenAI

from llm_sdks.base_sdk import BaseLLMSDK


class AzureOpenAISDK(BaseLLMSDK):
    """Azure OpenAI SDK implementation."""

    # Reuse HTTP clients to avoid per-request TCP/TLS overhead
    _clients: Dict[tuple, AzureOpenAI] = {}
    _lock = threading.Lock()

    def _get_client(
        self, api_version: str, azure_endpoint: str,
        api_key: str
    ) -> AzureOpenAI:
        """Get or create a cached AzureOpenAI client."""
        key = (azure_endpoint, api_version, api_key)
        client = self._clients.get(key)
        if client is not None:
            return client
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                client = AzureOpenAI(
                    api_version=api_version,
                    azure_endpoint=azure_endpoint,
                    api_key=api_key,
                )
                self._clients[key] = client
            return client

    def get_name(self) -> str:
        """Return the SDK name as stored in the database."""
        return "AzureOpenAI"

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration for AzureOpenAI.

        Required fields:
        - endpoint: Azure OpenAI endpoint URL
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
                "AzureOpenAI requires the following fields: "
                f"{', '.join(missing_fields)}"
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
        Execute completion using Azure OpenAI SDK.

        Args:
            config: Model configuration with endpoint, apiVersion,
                    and deployment
            system_prompt: System prompt to send
            user_content: User content to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: Azure OpenAI API key

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

        # Get cached client (reuses TCP/TLS connections)
        client = self._get_client(api_version, endpoint, api_key)

        # Make the API call
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )

        # Extract response and usage
        response_text = response.choices[0].message.content
        usage = response.usage

        if response_text is None:
            msg = "AzureOpenAI returned empty response content."
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
        Execute streaming completion using Azure OpenAI SDK.

        Args:
            config: Model configuration with endpoint, apiVersion,
                    and deployment
            system_prompt: System prompt to send
            user_content: User content to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: Azure OpenAI API key

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

        # Get cached client (reuses TCP/TLS connections)
        client = self._get_client(api_version, endpoint, api_key)

        # Make the streaming API call
        # IMPORTANT: stream_options={"include_usage": True} is required to get token counts
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True}
        )

        # Stream the response chunks
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            
            # Extract usage from the final chunk if available
            if hasattr(chunk, 'usage') and chunk.usage:
                prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                completion_tokens = getattr(chunk.usage, "completion_tokens", 0)
                total_tokens = getattr(chunk.usage, "total_tokens", 0)

        return (prompt_tokens, completion_tokens, total_tokens)
