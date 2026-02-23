"""
Google Gemini SDK

This SDK provides an interface to Google's Gemini models (e.g., Gemini 2.0 Flash)
via the Unified Google Gen AI library, supporting text generation and token tracking.
"""

import threading
from typing import Generator, Tuple, Dict, Any
from google import genai
from google.genai import types
from llm_sdks.base_sdk import BaseLLMSDK


class GeminiSDK(BaseLLMSDK):
    """Gemini SDK implementation using the google-genai library."""

    # Reuse HTTP clients to avoid per-request TCP/TLS overhead
    _clients: dict = {}
    _lock = threading.Lock()

    def _get_client(self, api_key: str):
        """Get or create a cached Gemini client."""
        client = self._clients.get(api_key)
        if client is not None:
            return client
        with self._lock:
            client = self._clients.get(api_key)
            if client is None:
                client = genai.Client(api_key=api_key)
                self._clients[api_key] = client
            return client

    def get_name(self) -> str:
        """
        Return the SDK name as stored in the database.
        """
        return "Gemini"
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate SDK-specific configuration requirements.
        """
        # Note: Gemini usually requires 'name' (model ID)
        # Deployment and endpoint are optional depending on whether 
        # using Vertex AI or the standard Developer API.
        required_fields = ['name']
        missing_fields = [field for field in required_fields if not config.get(field)]
        
        if missing_fields:
            raise ValueError(
                f"GeminiSdk requires the following fields: {', '.join(missing_fields)}"
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
        Execute a chat completion request using Google Gemini.
        """
        # 1. Validate configuration
        self.validate_config(config)
        
        # 2. Extract configuration values
        model_id = config.get('name')
        
        # 3. Get cached client (reuses TCP/TLS connections)
        client = self._get_client(api_key)
        
        # 4. Prepare messages and config
        # Google Gemini separates System Instruction from Content
        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        # 5. Make the API call
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=user_content,
                config=gen_config
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {str(e)}")
        
        # 6. Extract response text
        response_text = response.text
        
        # 7. Validate response is not empty
        if not response_text:
            raise RuntimeError("GeminiSdk returned empty response content.")
        
        # 8. Extract token usage from usage_metadata
        # Field names in google-genai: prompt_token_count, candidates_token_count, total_token_count
        usage = response.usage_metadata
        prompt_tokens = usage.prompt_token_count or 0
        completion_tokens = usage.candidates_token_count or 0
        total_tokens = usage.total_token_count or (prompt_tokens + completion_tokens)
        
        # 9. Return standardized tuple
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
        Execute streaming completion using the Google Gen AI SDK.
        """
        # 1. Validate configuration
        self.validate_config(config)
        model_id = config.get('name')

        # 2. Get cached client (reuses TCP/TLS connections)
        client = self._get_client(api_key)

        # 3. Prepare generation config
        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # 4. Make the streaming API call
        response_stream = client.models.generate_content_stream(
            model=model_id,
            contents=user_content,
            config=gen_config
        )

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        # 5. Iterate through the stream
        for chunk in response_stream:
            # Yield text if present in this chunk
            if chunk.text:
                yield chunk.text
            
            # 6. Extract usage from metadata
            # In Gemini, usage_metadata is populated in the final chunk(s)
            if chunk.usage_metadata:
                prompt_tokens = chunk.usage_metadata.prompt_token_count or 0
                completion_tokens = chunk.usage_metadata.candidates_token_count or 0
                total_tokens = chunk.usage_metadata.total_token_count or (prompt_tokens + completion_tokens)

        # 7. Return the final token counts as per your Generator signature
        return (prompt_tokens, completion_tokens, total_tokens)