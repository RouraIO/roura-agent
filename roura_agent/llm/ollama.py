"""
Roura Agent Ollama Provider - LLM provider with native tool calling support.

© Roura.io
"""
from __future__ import annotations

import json
import os
from typing import Any, Generator, Optional

import httpx

from .base import LLMProvider, LLMResponse, ToolCall, ProviderType
from ..errors import RouraError, ErrorCode, handle_connection_error


class OllamaProvider(LLMProvider):
    """
    Ollama LLM provider with native tool calling support.

    Supports both native tool calling (for compatible models) and
    fallback to text-based tool format.
    """

    # Models known to support native tool calling
    TOOL_CAPABLE_MODELS = {
        "qwen2.5-coder",
        "qwen2.5",
        "qwen2",
        "llama3.1",
        "llama3.2",
        "llama3.3",
        "mistral",
        "mixtral",
        "command-r",
        "command-r-plus",
        "firefunction",
        "mistral-nemo",
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        """
        Initialize Ollama provider.

        Args:
            base_url: Ollama API base URL (default: OLLAMA_BASE_URL env var)
            model: Model name (default: OLLAMA_MODEL env var)
            timeout: Request timeout in seconds
        """
        self._base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self._model = (model or os.getenv("OLLAMA_MODEL", "")).strip()
        self._timeout = timeout

        if not self._model:
            raise RouraError(ErrorCode.MODEL_NOT_SET)

    @property
    def model_name(self) -> str:
        """Get the current model name."""
        return self._model

    @property
    def base_url(self) -> str:
        """Get the base URL."""
        return self._base_url

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.OLLAMA

    def supports_tools(self) -> bool:
        """Check if current model supports native tool calling."""
        model_base = self._model.split(":")[0].lower()
        return any(capable in model_base for capable in self.TOOL_CAPABLE_MODELS)

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        if tools and self.supports_tools():
            payload["tools"] = tools

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()

            return self._parse_response(data)

        except httpx.TimeoutException as e:
            error = RouraError(ErrorCode.OLLAMA_TIMEOUT, cause=e)
            return LLMResponse(error=error.message)
        except httpx.ConnectError as e:
            error = RouraError(ErrorCode.OLLAMA_CONNECTION_FAILED, cause=e)
            return LLMResponse(error=error.message)
        except httpx.HTTPError as e:
            error = handle_connection_error(e, self._base_url)
            return LLMResponse(error=error.message)
        except Exception as e:
            error = RouraError(ErrorCode.UNEXPECTED_ERROR, message=str(e), cause=e)
            return LLMResponse(error=error.message)

    def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Generator[LLMResponse, None, None]:
        """
        Streaming chat with tool call accumulation.

        Yields partial responses as tokens arrive.
        Tool calls are accumulated and included in the final response.
        Yields periodic heartbeats during waiting to allow ESC interrupt checks.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }

        if tools and self.supports_tools():
            payload["tools"] = tools

        # Accumulators for streaming
        content_buffer: list[str] = []
        tool_calls_buffer: dict[int, dict] = {}

        # Yield initial "thinking" response so caller can start ESC checking
        yield LLMResponse(content="", done=False)

        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()

                line_buffer = ""
                # Use iter_bytes for more granular streaming with periodic yields
                for chunk in response.iter_bytes(chunk_size=256):
                    if chunk:
                        line_buffer += chunk.decode("utf-8", errors="replace")

                    # Process complete lines
                    while "\n" in line_buffer:
                        line, line_buffer = line_buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        message = data.get("message", {})

                        # Accumulate content
                        if content := message.get("content"):
                            content_buffer.append(content)

                        # Accumulate tool calls (may be streamed incrementally)
                        if raw_tool_calls := message.get("tool_calls"):
                            self._accumulate_tool_calls(raw_tool_calls, tool_calls_buffer)

                        # Yield partial response for display
                        yield LLMResponse(
                            content="".join(content_buffer),
                            done=data.get("done", False),
                        )

                        if data.get("done"):
                            # Build final tool calls and exit
                            final_tool_calls = self._build_tool_calls(tool_calls_buffer)
                            yield LLMResponse(
                                content="".join(content_buffer),
                                tool_calls=final_tool_calls,
                                done=True,
                            )
                            return

                    # Yield heartbeat after processing chunk (even if no complete line)
                    # This allows ESC checking during slow token generation
                    yield LLMResponse(content="".join(content_buffer), done=False)

        except httpx.TimeoutException as e:
            error = RouraError(ErrorCode.OLLAMA_TIMEOUT, cause=e)
            yield LLMResponse(error=error.message, done=True)
            return
        except httpx.ConnectError as e:
            error = RouraError(ErrorCode.OLLAMA_CONNECTION_FAILED, cause=e)
            yield LLMResponse(error=error.message, done=True)
            return
        except httpx.HTTPError as e:
            error = handle_connection_error(e, self._base_url)
            yield LLMResponse(error=error.message, done=True)
            return
        except Exception as e:
            error = RouraError(ErrorCode.OLLAMA_STREAMING_FAILED, message=str(e), cause=e)
            yield LLMResponse(error=error.message, done=True)
            return

        # Build final tool calls (fallback if stream ended without done=True)
        final_tool_calls = self._build_tool_calls(tool_calls_buffer)
        yield LLMResponse(
            content="".join(content_buffer),
            tool_calls=final_tool_calls,
            done=True,
        )

    def _accumulate_tool_calls(
        self,
        raw_calls: list[dict],
        buffer: dict[int, dict],
    ) -> None:
        """Accumulate tool call data from streaming chunks."""
        for tc in raw_calls:
            idx = tc.get("index", 0)

            if idx not in buffer:
                buffer[idx] = {
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": {"name": "", "arguments": ""},
                }

            # Accumulate function data
            if func := tc.get("function"):
                if name := func.get("name"):
                    buffer[idx]["function"]["name"] += name
                if args := func.get("arguments"):
                    buffer[idx]["function"]["arguments"] += args

    def _build_tool_calls(self, buffer: dict[int, dict]) -> list[ToolCall]:
        """Build ToolCall objects from accumulated buffer."""
        tool_calls = []

        for idx in sorted(buffer.keys()):
            tc_data = buffer[idx]
            func = tc_data.get("function", {})

            # Parse arguments JSON
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}

            # Generate ID if not provided
            tc_id = tc_data.get("id") or f"call_{idx}"

            tool_calls.append(ToolCall(
                id=tc_id,
                name=func.get("name", ""),
                arguments=args,
            ))

        return tool_calls

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse a non-streaming response."""
        message = data.get("message", {})
        content = message.get("content", "")

        tool_calls = []
        if raw_calls := message.get("tool_calls"):
            for idx, tc in enumerate(raw_calls):
                func = tc.get("function", {})

                # Parse arguments
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}

                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{idx}"),
                    name=func.get("name", ""),
                    arguments=args if isinstance(args, dict) else {},
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            done=True,
        )


def get_provider(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> OllamaProvider:
    """
    Get an Ollama provider instance.

    Convenience function for creating a provider with default settings.
    """
    return OllamaProvider(base_url=base_url, model=model)
