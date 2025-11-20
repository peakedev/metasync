"""
LLM SDK Plugin System

This package provides a modular, extensible architecture for LLM SDK
integrations. Each SDK is implemented as a separate plugin that inherits
from BaseLLMSDK.
"""

from llm_sdks.registry import SDKRegistry

__all__ = ['SDKRegistry']
