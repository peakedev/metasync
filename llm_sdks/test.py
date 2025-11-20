"""
Test SDK

Mock SDK for testing that returns dummy responses without making API calls.
"""

import time
from typing import Tuple, Dict, Any, Generator

from llm_sdks.base_sdk import BaseLLMSDK


class TestSDK(BaseLLMSDK):
    """Test/mock SDK returning dummy responses for testing."""

    def get_name(self) -> str:
        """Return the SDK name as stored in the database."""
        return "test"

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration for test SDK.

        Test SDK has minimal requirements - just needs a deployment
        field.
        """
        if not config.get('deployment'):
            raise ValueError("Test SDK requires 'deployment' field")

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
        Return a dummy JSON response without making API calls.

        Args:
            config: Model configuration (minimal requirements)
            system_prompt: System prompt (ignored in test SDK)
            user_content: User content (ignored in test SDK)
            temperature: Sampling temperature (ignored in test SDK)
            max_tokens: Maximum tokens (ignored in test SDK)
            api_key: API key (not needed for test SDK)

        Returns:
            Tuple of (response_text, prompt_tokens, completion_tokens,
                      total_tokens)
        """
        # Validate config
        self.validate_config(config)

        # Return valid JSON for compatibility with processing logic
        response_text = (
            '{"test": "response", "message": '
            '"This is a dummy response from the test SDK"}'
        )

        # Return minimal token counts
        prompt_tokens = 1
        completion_tokens = 1
        total_tokens = 2

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
        Stream a dummy lorem ipsum response character by character.

        Args:
            config: Model configuration (minimal requirements)
            system_prompt: System prompt (ignored in test SDK)
            user_content: User content (ignored in test SDK)
            temperature: Sampling temperature (ignored in test SDK)
            max_tokens: Maximum tokens (ignored in test SDK)
            api_key: API key (not needed for test SDK)

        Yields:
            Individual characters from the lorem ipsum text

        Returns:
            Tuple of (prompt_tokens, completion_tokens, total_tokens)
        """
        # Validate config
        self.validate_config(config)

        # Long lorem ipsum text for streaming
        lorem_ipsum = (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do "
            "eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut "
            "enim ad minim veniam, quis nostrud exercitation ullamco laboris "
            "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor "
            "in reprehenderit in voluptate velit esse cillum dolore eu fugiat "
            "nulla pariatur. Excepteur sint occaecat cupidatat non proident, "
            "sunt in culpa qui officia deserunt mollit anim id est laborum."
        )

        # Stream character by character with small delay
        for char in lorem_ipsum:
            yield char
            time.sleep(0.01)  # 10ms delay between characters

        # Return token counts
        prompt_tokens = 10
        completion_tokens = 50
        total_tokens = 60

        return (prompt_tokens, completion_tokens, total_tokens)
