"""
Test SDK

Mock SDK for testing that returns dummy responses without making API calls.
"""

from typing import Tuple, Dict, Any

from llm_sdks.base_sdk import BaseLLMSDK


class TestSDK(BaseLLMSDK):
    """Test/mock SDK that returns dummy responses for testing."""
    
    def get_name(self) -> str:
        """Return the SDK name as stored in the database."""
        return "test"
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration for test SDK.
        
        Test SDK has minimal requirements - just needs a deployment field.
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
            Tuple of (response_text, prompt_tokens, completion_tokens, total_tokens)
        """
        # Validate config
        self.validate_config(config)
        
        # Return a valid JSON response for compatibility with processing logic
        response_text = '{"test": "response", "message": "This is a dummy response from the test SDK"}'
        
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

