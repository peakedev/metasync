"""
SDK Registry

Auto-discovers and registers all available SDK implementations.
"""

import os
import importlib
import inspect
from typing import Dict, List, Optional
from pathlib import Path


class SDKRegistry:
    """
    Registry for LLM SDK implementations with auto-discovery.
    
    Automatically discovers and loads all SDK implementations from the llm-sdks directory.
    """
    
    _sdks: Dict[str, 'BaseLLMSDK'] = {}
    _initialized = False
    
    @classmethod
    def _initialize(cls):
        """
        Discover and register all SDK implementations.
        
        Scans the llm-sdks directory for Python files (excluding base_sdk.py, registry.py, and __init__.py)
        and automatically imports and registers any classes that inherit from BaseLLMSDK.
        """
        if cls._initialized:
            return
        
        # Import BaseLLMSDK for type checking
        from llm_sdks.base_sdk import BaseLLMSDK
        
        # Get the llm-sdks directory path
        sdk_dir = Path(__file__).parent
        
        # Find all Python files in the directory
        for file_path in sdk_dir.glob("*.py"):
            filename = file_path.name
            
            # Skip special files
            if filename in ['__init__.py', 'base_sdk.py', 'registry.py']:
                continue
            
            # Import the module
            module_name = filename[:-3]  # Remove .py extension
            try:
                module = importlib.import_module(f'llm_sdks.{module_name}')
                
                # Find all classes in the module that inherit from BaseLLMSDK
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if it's a subclass of BaseLLMSDK (but not BaseLLMSDK itself)
                    if issubclass(obj, BaseLLMSDK) and obj is not BaseLLMSDK:
                        # Instantiate the SDK
                        sdk_instance = obj()
                        sdk_name = sdk_instance.get_name()
                        cls._sdks[sdk_name] = sdk_instance
                        
            except Exception as e:
                print(f"Warning: Failed to load SDK from {filename}: {e}")
                continue
        
        cls._initialized = True
    
    @classmethod
    def get_sdk(cls, name: str) -> Optional['BaseLLMSDK']:
        """
        Get an SDK implementation by name.
        
        Args:
            name: SDK name (e.g., "ChatCompletionsClient", "AzureOpenAI", "Anthropic", "test")
            
        Returns:
            SDK instance or None if not found
        """
        cls._initialize()
        return cls._sdks.get(name)
    
    @classmethod
    def list_sdks(cls) -> List[str]:
        """
        Get a list of all registered SDK names.
        
        Returns:
            List of SDK names
        """
        cls._initialize()
        return sorted(cls._sdks.keys())
    
    @classmethod
    def get_all_sdks(cls) -> Dict[str, 'BaseLLMSDK']:
        """
        Get all registered SDK instances.
        
        Returns:
            Dictionary mapping SDK names to instances
        """
        cls._initialize()
        return cls._sdks.copy()

