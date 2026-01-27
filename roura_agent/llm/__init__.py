"""
Roura Agent LLM - Abstraction layer for LLM providers.

© Roura.io
"""
from .base import (
    LLMProvider,
    LLMResponse,
    ToolCall,
    ProviderType,
    ProviderRegistry,
    provider_registry,
    get_provider,
    detect_available_providers,
)
from .ollama import OllamaProvider

# Register Ollama provider
provider_registry.register(ProviderType.OLLAMA, OllamaProvider)

# Lazy registration for optional providers
def _register_openai():
    """Register OpenAI provider if available."""
    try:
        from .openai import OpenAIProvider
        provider_registry.register(ProviderType.OPENAI, OpenAIProvider)
        return True
    except ImportError:
        return False

def _register_anthropic():
    """Register Anthropic provider if available."""
    try:
        from .anthropic import AnthropicProvider
        provider_registry.register(ProviderType.ANTHROPIC, AnthropicProvider)
        return True
    except ImportError:
        return False

# Try to register optional providers
_register_openai()
_register_anthropic()

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "ProviderType",
    "ProviderRegistry",
    "provider_registry",
    "get_provider",
    "detect_available_providers",
    "OllamaProvider",
]
