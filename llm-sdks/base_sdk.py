"""
Base SDK Interface

Defines the abstract interface that all LLM SDK implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any


class BaseLLMSDK(ABC):
    """
    Abstract base class for LLM SDK implementations.
    
    All SDK plugins must inherit from this class and implement the required methods.
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return the SDK name as it appears in the database.
        
        This name must match exactly what's stored in the 'sdk' field of model documents.
        
        Returns:
            str: The SDK identifier (e.g., "ChatCompletionsClient", "AzureOpenAI", "Anthropic", "test")
        """
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate SDK-specific configuration requirements.
        
        Check that all required fields for this SDK are present and valid.
        Should raise ValueError with a descriptive message if validation fails.
        
        Args:
            config: Model configuration dictionary with fields like:
                   - name: Model name
                   - endpoint: API endpoint URL
                   - apiVersion: API version string
                   - deployment: Deployment/model identifier
                   - maxTemperature: Maximum temperature limit
                   - minTemperature: Minimum temperature limit
                   
        Raises:
            ValueError: If required fields are missing or invalid
        """
        pass
    
    @abstractmethod
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
            config: Model configuration dictionary
            system_prompt: System prompt/instruction for the model
            user_content: User message content
            temperature: Sampling temperature (already clamped to min/max)
            max_tokens: Maximum tokens to generate
            api_key: API key for authentication (None for test SDK)
            
        Returns:
            Tuple of (response_text, prompt_tokens, completion_tokens, total_tokens)
            - response_text: The generated text response
            - prompt_tokens: Number of tokens in the prompt
            - completion_tokens: Number of tokens in the completion
            - total_tokens: Total tokens used
            
        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If the API call fails or returns empty response
        """
        pass

