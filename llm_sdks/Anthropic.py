"""
Anthropic SDK

Implementation for Anthropic's Claude API using the official Anthropic
Python SDK.
"""

from typing import Tuple, Dict, Any, Generator
from anthropic import Anthropic
from urllib.parse import urlparse

from llm_sdks.base_sdk import BaseLLMSDK


class AnthropicSDK(BaseLLMSDK):
    """Anthropic Claude SDK with streaming support."""

    def get_name(self) -> str:
        """Return the SDK name as stored in the database."""
        return "Anthropic"

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration for Anthropic.

        Required fields:
        - endpoint: API endpoint URL (must be anthropic.com domain)
        - deployment: Model identifier
                     (e.g., "claude-3-7-sonnet-20250219")
        """
        required_fields = ['endpoint', 'deployment']
        missing_fields = [
            field for field in required_fields
            if not config.get(field)
        ]

        if missing_fields:
            msg = (
                "Anthropic requires the following fields: "
                f"{', '.join(missing_fields)}"
            )
            raise ValueError(msg)

        # Validate endpoint is Anthropic's official API
        endpoint = config.get('endpoint', '')
        try:
            host = urlparse(endpoint).netloc.lower()
        except Exception:
            host = ""

        if "anthropic.com" not in host:
            raise ValueError(
                f"Invalid Anthropic endpoint '{endpoint}'. "
                f"Use 'https://api.anthropic.com'."
            )

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
        Execute completion using Anthropic SDK with streaming.

        Uses streaming to avoid the 10-minute timeout for long
        requests. Anthropic separates system prompts from user messages.

        Args:
            config: Model configuration with endpoint and deployment
            system_prompt: System prompt (sent separately in Anthropic)
            user_content: User message content
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: Anthropic API key

        Returns:
            Tuple of (response_text, prompt_tokens, completion_tokens,
                      total_tokens)
        """
        # Validate config
        self.validate_config(config)

        endpoint = config.get('endpoint')
        deployment = config.get('deployment')

        # Create client
        client = Anthropic(api_key=api_key, base_url=endpoint)

        # Anthropic separates system and messages
        # Keep system in system_prompt and send user content as a user message
        anthro_messages = [{"role": "user", "content": user_content or ""}]

        # Stream the response to avoid 10-minute non-streaming limit
        response_text_parts = []
        try:
            with client.messages.stream(
                model=deployment,
                system=system_prompt or "",
                messages=anthro_messages,
                temperature=temperature,
                max_tokens=max_tokens
            ) as stream:
                for text in stream.text_stream:
                    response_text_parts.append(text)
                final_msg = stream.get_final_message()
        except Exception as e:
            # Re-raise with context
            raise RuntimeError(f"Anthropic API request failed: {e}")

        response_text = (
            "".join(response_text_parts) if response_text_parts else None
        )

        if response_text is None:
            raise RuntimeError("Anthropic returned empty response content.")

        # Extract usage information
        usage = getattr(final_msg, "usage", None)
        prompt_tokens = (
            getattr(usage, "input_tokens", None) if usage else None
        )
        completion_tokens = (
            getattr(usage, "output_tokens", None) if usage else None
        )
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

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
        Execute streaming completion using Anthropic SDK.

        Uses streaming to deliver chunks as they arrive from the API.
        Anthropic separates system prompts from user messages.

        Args:
            config: Model configuration with endpoint and deployment
            system_prompt: System prompt (sent separately in Anthropic)
            user_content: User message content
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: Anthropic API key

        Yields:
            Text chunks as they arrive from the API

        Returns:
            Tuple of (prompt_tokens, completion_tokens, total_tokens)
        """
        # Validate config
        self.validate_config(config)

        endpoint = config.get('endpoint')
        deployment = config.get('deployment')

        # Create client
        client = Anthropic(api_key=api_key, base_url=endpoint)

        # Anthropic separates system and messages
        # Keep system in system_prompt and send user content as a user message
        anthro_messages = [{"role": "user", "content": user_content or ""}]

        # Stream the response
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        try:
            with client.messages.stream(
                model=deployment,
                system=system_prompt or "",
                messages=anthro_messages,
                temperature=temperature,
                max_tokens=max_tokens
            ) as stream:
                for text in stream.text_stream:
                    yield text
                final_msg = stream.get_final_message()
        except Exception as e:
            # Re-raise with context
            raise RuntimeError(f"Anthropic API request failed: {e}")

        # Extract usage information
        usage = getattr(final_msg, "usage", None)
        prompt_tokens = (
            getattr(usage, "input_tokens", None) if usage else None
        )
        completion_tokens = (
            getattr(usage, "output_tokens", None) if usage else None
        )
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        return (prompt_tokens, completion_tokens, total_tokens)
