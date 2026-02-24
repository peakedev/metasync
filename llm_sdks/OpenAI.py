"""
OpenAI SDK

Implementation for OpenAI-compatible APIs using the official
OpenAI Python SDK with a custom base_url. Supports any provider
that exposes an OpenAI-compatible chat completions endpoint
(e.g. Grok via Azure Foundry).
"""

import threading
from typing import Tuple, Dict, Any, Generator
from openai import OpenAI

from llm_sdks.base_sdk import BaseLLMSDK


class OpenAISDK(BaseLLMSDK):
    """OpenAI-compatible SDK implementation."""

    _clients: Dict[tuple, OpenAI] = {}
    _lock = threading.Lock()

    def _get_client(
        self, base_url: str, api_key: str
    ) -> OpenAI:
        """Get or create a cached OpenAI client."""
        key = (base_url, api_key)
        client = self._clients.get(key)
        if client is not None:
            return client
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                client = OpenAI(
                    base_url=base_url,
                    api_key=api_key,
                )
                self._clients[key] = client
            return client

    def get_name(self) -> str:
        """Return the SDK name as stored in the database."""
        return "OpenAI"

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration for OpenAI-compatible endpoints.

        Required fields:
        - endpoint: Base URL for the API
        - deployment: Model name / deployment identifier
        """
        required_fields = ['endpoint', 'deployment']
        missing_fields = [
            field for field in required_fields
            if not config.get(field)
        ]

        if missing_fields:
            msg = (
                "OpenAI SDK requires the following fields: "
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
        Execute completion using the OpenAI SDK.

        Args:
            config: Model configuration with endpoint and deployment
            system_prompt: System prompt to send
            user_content: User content to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: API key for authentication

        Returns:
            Tuple of (response_text, prompt_tokens,
                      completion_tokens, total_tokens)
        """
        self.validate_config(config)

        endpoint = config.get('endpoint')
        deployment = config.get('deployment')

        content = (system_prompt or "") + (user_content or "")
        messages = [{"role": "system", "content": content}]

        client = self._get_client(endpoint, api_key)

        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )

        response_text = response.choices[0].message.content
        usage = response.usage

        if response_text is None:
            msg = "OpenAI SDK returned empty response content."
            raise RuntimeError(msg)

        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(
            usage, "completion_tokens", None
        )
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
        Execute streaming completion using the OpenAI SDK.

        Args:
            config: Model configuration with endpoint and deployment
            system_prompt: System prompt to send
            user_content: User content to send
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: API key for authentication

        Yields:
            Text chunks as they arrive from the API

        Returns:
            Tuple of (prompt_tokens, completion_tokens,
                      total_tokens)
        """
        self.validate_config(config)

        endpoint = config.get('endpoint')
        deployment = config.get('deployment')

        content = (system_prompt or "") + (user_content or "")
        messages = [{"role": "system", "content": content}]

        client = self._get_client(endpoint, api_key)

        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

            if hasattr(chunk, 'usage') and chunk.usage:
                prompt_tokens = getattr(
                    chunk.usage, "prompt_tokens", 0
                )
                completion_tokens = getattr(
                    chunk.usage, "completion_tokens", 0
                )
                total_tokens = getattr(
                    chunk.usage, "total_tokens", 0
                )

        return (prompt_tokens, completion_tokens, total_tokens)
