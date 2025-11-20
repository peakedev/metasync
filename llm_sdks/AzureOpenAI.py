"""
Azure OpenAI SDK

Implementation for Azure OpenAI API using the official OpenAI Python SDK.
"""

from typing import Tuple, Dict, Any
from openai import AzureOpenAI

from llm_sdks.base_sdk import BaseLLMSDK


class AzureOpenAISDK(BaseLLMSDK):
    """Azure OpenAI SDK implementation."""

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

        # Create client
        client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=endpoint,
            api_key=api_key,
        )

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
