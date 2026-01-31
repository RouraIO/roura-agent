"""
Tests for LLM providers (OpenAI, Anthropic, Ollama).

These tests use mocked HTTP responses to verify provider behavior.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Iterator

from roura_agent.llm.base import (
    LLMProvider,
    LLMResponse,
    ToolCall,
    ProviderType,
    get_provider,
    detect_available_providers,
    provider_registry,
)


# =============================================================================
# OpenAI Provider Tests
# =============================================================================


class TestOpenAIProvider:
    """Tests for OpenAI provider."""

    @pytest.fixture
    def mock_env(self, monkeypatch):
        """Set up environment for OpenAI."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")

    def test_initialization_with_api_key(self, mock_env):
        """Test provider initializes with API key."""
        from roura_agent.llm.openai import OpenAIProvider

        provider = OpenAIProvider()
        assert provider.model_name == "gpt-4o"
        assert provider.provider_type == ProviderType.OPENAI

    def test_initialization_without_api_key_raises(self, monkeypatch):
        """Test provider raises error without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)

        from roura_agent.llm.openai import OpenAIProvider
        from roura_agent.errors import RouraError

        with pytest.raises(RouraError):
            OpenAIProvider()

    def test_supports_tools(self, mock_env):
        """Test tool support detection."""
        from roura_agent.llm.openai import OpenAIProvider

        provider = OpenAIProvider()
        assert provider.supports_tools() is True

    @patch("httpx.Client")
    def test_chat_returns_content(self, mock_client_class, mock_env):
        """Test non-streaming chat returns content."""
        from roura_agent.llm.openai import OpenAIProvider

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Hello! How can I help you?",
                    "role": "assistant",
                }
            }]
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = OpenAIProvider()
        response = provider.chat([{"role": "user", "content": "Hello"}])

        assert response.content == "Hello! How can I help you?"
        assert response.done is True
        assert len(response.tool_calls) == 0

    @patch("httpx.Client")
    def test_chat_returns_tool_calls(self, mock_client_class, mock_env):
        """Test non-streaming chat returns tool calls."""
        from roura_agent.llm.openai import OpenAIProvider

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "",
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "fs.read",
                            "arguments": '{"path": "/tmp/test.txt"}'
                        }
                    }]
                }
            }]
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = OpenAIProvider()
        response = provider.chat([{"role": "user", "content": "Read the file"}])

        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "fs.read"
        assert response.tool_calls[0].arguments == {"path": "/tmp/test.txt"}

    @patch("httpx.Client")
    def test_chat_handles_401_error(self, mock_client_class, mock_env):
        """Test chat handles invalid API key."""
        from roura_agent.llm.openai import OpenAIProvider
        from roura_agent.errors import RouraError

        mock_response = Mock()
        mock_response.status_code = 401

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = OpenAIProvider()

        with pytest.raises(RouraError):
            provider.chat([{"role": "user", "content": "Hello"}])

    @patch("httpx.stream")
    def test_chat_stream_yields_content(self, mock_stream, mock_env):
        """Test streaming chat yields partial content."""
        from roura_agent.llm.openai import OpenAIProvider

        # Simulate streaming response
        lines = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter(lines)
        mock_response.raise_for_status = Mock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_stream.return_value = mock_response

        provider = OpenAIProvider()
        responses = list(provider.chat_stream([{"role": "user", "content": "Hi"}]))

        # Should have multiple partial responses
        assert len(responses) >= 1
        # Final response should have accumulated content
        final = responses[-1]
        assert "Hello" in final.content
        assert final.done is True


# =============================================================================
# Anthropic Provider Tests
# =============================================================================


class TestAnthropicProvider:
    """Tests for Anthropic provider."""

    @pytest.fixture
    def mock_env(self, monkeypatch):
        """Set up environment for Anthropic."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-456")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    def test_initialization_with_api_key(self, mock_env):
        """Test provider initializes with API key."""
        from roura_agent.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.model_name == "claude-sonnet-4-20250514"
        assert provider.provider_type == ProviderType.ANTHROPIC

    def test_initialization_without_api_key_raises(self, monkeypatch):
        """Test provider raises error without API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

        from roura_agent.llm.anthropic import AnthropicProvider
        from roura_agent.errors import RouraError

        with pytest.raises(RouraError):
            AnthropicProvider()

    def test_supports_tools(self, mock_env):
        """Test tool support detection."""
        from roura_agent.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.supports_tools() is True

    def test_convert_messages_extracts_system(self, mock_env):
        """Test message conversion extracts system prompt."""
        from roura_agent.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        system, converted = provider._convert_messages(messages)

        assert system == "You are helpful."
        assert len(converted) == 1
        assert converted[0]["role"] == "user"

    @patch("httpx.Client")
    def test_chat_returns_content(self, mock_client_class, mock_env):
        """Test non-streaming chat returns content."""
        from roura_agent.llm.anthropic import AnthropicProvider

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {"type": "text", "text": "Hello! I'm Claude."}
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = AnthropicProvider()
        response = provider.chat([{"role": "user", "content": "Hello"}])

        assert response.content == "Hello! I'm Claude."
        assert response.done is True

    @patch("httpx.Client")
    def test_chat_returns_tool_use(self, mock_client_class, mock_env):
        """Test non-streaming chat returns tool use."""
        from roura_agent.llm.anthropic import AnthropicProvider

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {"type": "text", "text": "I'll read that file."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "fs.read",
                    "input": {"path": "/tmp/test.txt"}
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = AnthropicProvider()
        response = provider.chat([{"role": "user", "content": "Read the file"}])

        assert "read that file" in response.content.lower()
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "fs.read"
        assert response.tool_calls[0].arguments == {"path": "/tmp/test.txt"}

    @patch("httpx.Client")
    def test_chat_handles_401_error(self, mock_client_class, mock_env):
        """Test chat handles invalid API key."""
        from roura_agent.llm.anthropic import AnthropicProvider
        from roura_agent.errors import RouraError

        mock_response = Mock()
        mock_response.status_code = 401

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = AnthropicProvider()

        with pytest.raises(RouraError):
            provider.chat([{"role": "user", "content": "Hello"}])


# =============================================================================
# Provider Registry Tests
# =============================================================================


class TestProviderRegistry:
    """Tests for provider registry and auto-detection."""

    def test_ollama_registered(self):
        """Test Ollama provider is registered."""
        assert provider_registry.is_available(ProviderType.OLLAMA)

    def test_openai_registered(self):
        """Test OpenAI provider is registered."""
        assert provider_registry.is_available(ProviderType.OPENAI)

    def test_anthropic_registered(self):
        """Test Anthropic provider is registered."""
        assert provider_registry.is_available(ProviderType.ANTHROPIC)

    def test_list_providers(self):
        """Test listing registered providers."""
        providers = provider_registry.list_providers()
        assert ProviderType.OLLAMA in providers
        assert ProviderType.OPENAI in providers
        assert ProviderType.ANTHROPIC in providers


class TestGetProvider:
    """Tests for get_provider factory function."""

    def test_get_provider_with_explicit_type(self, monkeypatch):
        """Test getting provider with explicit type."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        # Skip license check for testing
        provider = get_provider(ProviderType.OPENAI, check_license=False)
        assert provider.provider_type == ProviderType.OPENAI

    def test_get_provider_auto_detects_openai(self, monkeypatch):
        """Test auto-detection uses OpenAI when key is set and Ollama unavailable."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)

        # Mock Ollama as unavailable so cloud provider is used
        # Keep the original is_available for other providers
        original_is_available = provider_registry.is_available
        def mock_is_available(pt):
            if pt == ProviderType.OLLAMA:
                return False
            return original_is_available(pt)

        with patch.object(provider_registry, 'is_available', side_effect=mock_is_available):
            provider = get_provider(check_license=False)
            assert provider.provider_type == ProviderType.OPENAI

    def test_get_provider_auto_detects_anthropic(self, monkeypatch):
        """Test auto-detection uses Anthropic when only that key is set and Ollama unavailable."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)

        # Mock Ollama as unavailable so cloud provider is used
        original_is_available = provider_registry.is_available
        def mock_is_available(pt):
            if pt == ProviderType.OLLAMA:
                return False
            return original_is_available(pt)

        with patch.object(provider_registry, 'is_available', side_effect=mock_is_available):
            provider = get_provider(check_license=False)
            assert provider.provider_type == ProviderType.ANTHROPIC

    def test_get_provider_falls_back_to_ollama(self, monkeypatch):
        """Test auto-detection falls back to Ollama."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")

        provider = get_provider(check_license=False)
        assert provider.provider_type == ProviderType.OLLAMA


class TestDetectAvailableProviders:
    """Tests for provider availability detection."""

    def test_detects_openai_with_key(self, monkeypatch):
        """Test OpenAI detected when key is set."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        available = detect_available_providers()
        assert ProviderType.OPENAI in available

    def test_detects_anthropic_with_key(self, monkeypatch):
        """Test Anthropic detected when key is set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        available = detect_available_providers()
        assert ProviderType.ANTHROPIC in available

    def test_no_openai_without_key(self, monkeypatch):
        """Test OpenAI not detected without key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        available = detect_available_providers()
        assert ProviderType.OPENAI not in available
