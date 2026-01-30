"""
Roura Agent LLM Base - Abstract base classes for LLM providers.

© Roura.io
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generator, Optional, Type


class ProviderType(Enum):
    """Supported LLM provider types."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]

    def __repr__(self) -> str:
        return f"ToolCall({self.name}, {self.arguments})"


@dataclass
class LLMResponse:
    """Response from an LLM, may contain content and/or tool calls."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False
    interrupted: bool = False
    error: Optional[str] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0

    @property
    def has_content(self) -> bool:
        """Check if response has text content."""
        return bool(self.content.strip())


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        """
        Non-streaming chat completion.

        Args:
            messages: List of message dicts with role and content
            tools: Optional list of tool definitions in JSON Schema format

        Returns:
            LLMResponse with content and/or tool_calls
        """
        pass

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Generator[LLMResponse, None, None]:
        """
        Streaming chat completion.

        Yields partial LLMResponse objects as tokens arrive.
        The final response will have done=True and include any tool_calls.

        Args:
            messages: List of message dicts with role and content
            tools: Optional list of tool definitions in JSON Schema format

        Yields:
            Partial LLMResponse objects
        """
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        """
        Check if the current model supports native tool calling.

        Returns:
            True if native tool calling is supported
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the current model name."""
        pass

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type. Override in subclasses."""
        raise NotImplementedError

    def supports_vision(self) -> bool:
        """
        Check if the current model supports vision/image input.

        Returns:
            True if vision is supported
        """
        return False

    def chat_with_images(
        self,
        prompt: str,
        images: list[dict],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Chat with image content.

        Args:
            prompt: Text prompt to accompany images
            images: List of image dicts in provider format (e.g., Anthropic format)
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with the model's response

        Raises:
            NotImplementedError: If vision is not supported
        """
        if not self.supports_vision():
            raise NotImplementedError(f"{self.__class__.__name__} does not support vision")
        raise NotImplementedError("Subclass must implement chat_with_images")


class ProviderRegistry:
    """
    Registry for LLM providers.

    Allows dynamic registration and discovery of providers.
    """

    def __init__(self):
        self._providers: dict[ProviderType, Type[LLMProvider]] = {}
        self._factories: dict[ProviderType, Callable[..., LLMProvider]] = {}

    def register(
        self,
        provider_type: ProviderType,
        provider_class: Optional[Type[LLMProvider]] = None,
        factory: Optional[Callable[..., LLMProvider]] = None,
    ) -> None:
        """
        Register a provider class or factory.

        Args:
            provider_type: The type identifier for this provider
            provider_class: Optional provider class to register
            factory: Optional factory function that creates provider instances
        """
        if provider_class:
            self._providers[provider_type] = provider_class
        if factory:
            self._factories[provider_type] = factory

    def get_class(self, provider_type: ProviderType) -> Optional[Type[LLMProvider]]:
        """Get a registered provider class."""
        return self._providers.get(provider_type)

    def get_factory(self, provider_type: ProviderType) -> Optional[Callable[..., LLMProvider]]:
        """Get a registered factory function."""
        return self._factories.get(provider_type)

    def create(
        self,
        provider_type: ProviderType,
        **kwargs,
    ) -> LLMProvider:
        """
        Create a provider instance.

        Args:
            provider_type: Type of provider to create
            **kwargs: Arguments passed to provider constructor

        Returns:
            Configured LLMProvider instance

        Raises:
            ValueError: If provider type is not registered
        """
        # Try factory first
        if factory := self._factories.get(provider_type):
            return factory(**kwargs)

        # Fall back to class
        if provider_class := self._providers.get(provider_type):
            return provider_class(**kwargs)

        raise ValueError(f"Unknown provider type: {provider_type.value}")

    def list_providers(self) -> list[ProviderType]:
        """List all registered provider types."""
        types = set(self._providers.keys()) | set(self._factories.keys())
        return sorted(types, key=lambda t: t.value)

    def is_available(self, provider_type: ProviderType) -> bool:
        """Check if a provider type is registered."""
        return provider_type in self._providers or provider_type in self._factories


# Global provider registry
provider_registry = ProviderRegistry()


def _check_provider_license(provider_type: ProviderType) -> None:
    """
    Check if the provider is allowed by the current license.

    Raises:
        LicenseError: If provider requires a higher tier
    """
    from ..licensing import is_feature_enabled, require_feature

    feature_map = {
        ProviderType.OPENAI: "provider.openai",
        ProviderType.ANTHROPIC: "provider.anthropic",
        ProviderType.OLLAMA: "provider.ollama",
    }

    feature = feature_map.get(provider_type)
    if feature:
        require_feature(feature)


def get_provider(
    provider_type: Optional[ProviderType] = None,
    check_license: bool = True,
    **kwargs,
) -> LLMProvider:
    """
    Factory function to create an LLM provider.

    This is the main entry point for getting a provider instance.
    It supports auto-detection based on available credentials/configuration.

    Args:
        provider_type: Type of provider (auto-detect if None)
        check_license: Whether to check license for provider access (default: True)
        **kwargs: Provider-specific configuration

    Returns:
        Configured LLMProvider instance

    Raises:
        ValueError: If no suitable provider is available
        LicenseError: If provider requires a higher license tier

    Example:
        >>> provider = get_provider(ProviderType.OLLAMA, model="llama3.1:8b")
        >>> provider = get_provider()  # Auto-detect
    """
    import os
    from ..licensing import is_feature_enabled

    if provider_type is not None:
        if check_license:
            _check_provider_license(provider_type)
        return provider_registry.create(provider_type, **kwargs)

    # Auto-detection based on environment
    # Priority: Ollama (local-first) > Anthropic > OpenAI
    # We prefer local models to keep data private and reduce costs

    # Default to Ollama first (local-first philosophy)
    if provider_registry.is_available(ProviderType.OLLAMA):
        if os.getenv("OLLAMA_MODEL"):
            try:
                return provider_registry.create(ProviderType.OLLAMA, **kwargs)
            except Exception:
                pass  # Fall through to cloud providers

    # Fall back to cloud providers if local is not available
    if os.getenv("ANTHROPIC_API_KEY") and provider_registry.is_available(ProviderType.ANTHROPIC):
        if not check_license or is_feature_enabled("provider.anthropic"):
            return provider_registry.create(ProviderType.ANTHROPIC, **kwargs)

    if os.getenv("OPENAI_API_KEY") and provider_registry.is_available(ProviderType.OPENAI):
        if not check_license or is_feature_enabled("provider.openai"):
            return provider_registry.create(ProviderType.OPENAI, **kwargs)

    # Last resort: try Ollama anyway
    if provider_registry.is_available(ProviderType.OLLAMA):
        return provider_registry.create(ProviderType.OLLAMA, **kwargs)

    raise ValueError(
        "No LLM provider available. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
        "or ensure Ollama is running."
    )


def detect_available_providers() -> list[ProviderType]:
    """
    Detect which providers are available based on configuration.

    Returns:
        List of available provider types
    """
    import os

    available = []

    # Check Ollama
    if provider_registry.is_available(ProviderType.OLLAMA):
        try:
            import httpx
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            response = httpx.get(f"{base_url}/api/tags", timeout=2.0)
            if response.status_code == 200:
                available.append(ProviderType.OLLAMA)
        except Exception:
            pass

    # Check OpenAI
    if os.getenv("OPENAI_API_KEY") and provider_registry.is_available(ProviderType.OPENAI):
        available.append(ProviderType.OPENAI)

    # Check Anthropic
    if os.getenv("ANTHROPIC_API_KEY") and provider_registry.is_available(ProviderType.ANTHROPIC):
        available.append(ProviderType.ANTHROPIC)

    return available
