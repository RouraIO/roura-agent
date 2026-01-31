"""
Roura Agent Ollama Provider - LLM provider with native tool calling support.

© Roura.io
"""
from __future__ import annotations

import json
import os
import queue
import threading
from collections.abc import Generator
from typing import Any, Optional

import httpx

from ..errors import ErrorCode, RouraError, handle_connection_error
from .base import LLMProvider, LLMResponse, ProviderType, ToolCall


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
        Uses threading to allow ESC interrupt even during initial connection.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }

        if tools and self.supports_tools():
            payload["tools"] = tools

        # Queue for thread communication
        data_queue: queue.Queue = queue.Queue()

        # Flag to signal thread to stop
        stop_flag = threading.Event()

        def stream_worker():
            """Background worker that streams from Ollama."""
            content_buffer: list[str] = []
            tool_calls_buffer: dict[int, dict] = {}

            try:
                with httpx.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload,
                    timeout=self._timeout,
                ) as response:
                    response.raise_for_status()

                    line_buffer = ""
                    for chunk in response.iter_bytes(chunk_size=256):
                        if stop_flag.is_set():
                            return

                        if chunk:
                            line_buffer += chunk.decode("utf-8", errors="replace")

                        # Process complete lines
                        while "\n" in line_buffer:
                            if stop_flag.is_set():
                                return

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

                            # Accumulate tool calls
                            if raw_tool_calls := message.get("tool_calls"):
                                self._accumulate_tool_calls(raw_tool_calls, tool_calls_buffer)

                            # Put response in queue
                            data_queue.put(LLMResponse(
                                content="".join(content_buffer),
                                done=data.get("done", False),
                            ))

                            if data.get("done"):
                                # Final response with tool calls
                                final_content = "".join(content_buffer)
                                final_tool_calls = self._build_tool_calls(tool_calls_buffer)

                                # Fallback: parse tool calls from content if none found
                                if not final_tool_calls and final_content:
                                    parsed = self._try_parse_json_tool_call(final_content)
                                    if parsed:
                                        final_tool_calls = parsed
                                        final_content = ""

                                data_queue.put(LLMResponse(
                                    content=final_content,
                                    tool_calls=final_tool_calls,
                                    done=True,
                                ))
                                return

                # Stream ended without done=True
                final_content = "".join(content_buffer)
                final_tool_calls = self._build_tool_calls(tool_calls_buffer)

                # Fallback: parse tool calls from content if none found
                if not final_tool_calls and final_content:
                    parsed = self._try_parse_json_tool_call(final_content)
                    if parsed:
                        final_tool_calls = parsed
                        final_content = ""

                data_queue.put(LLMResponse(
                    content=final_content,
                    tool_calls=final_tool_calls,
                    done=True,
                ))

            except httpx.TimeoutException as e:
                error = RouraError(ErrorCode.OLLAMA_TIMEOUT, cause=e)
                data_queue.put(LLMResponse(error=error.message, done=True))
            except httpx.ConnectError as e:
                error = RouraError(ErrorCode.OLLAMA_CONNECTION_FAILED, cause=e)
                data_queue.put(LLMResponse(error=error.message, done=True))
            except httpx.HTTPError as e:
                error = handle_connection_error(e, self._base_url)
                data_queue.put(LLMResponse(error=error.message, done=True))
            except Exception as e:
                if not stop_flag.is_set():
                    error = RouraError(ErrorCode.OLLAMA_STREAMING_FAILED, message=str(e), cause=e)
                    data_queue.put(LLMResponse(error=error.message, done=True))

        # Start background thread
        thread = threading.Thread(target=stream_worker, daemon=True)
        thread.start()

        # Yield responses from queue, with periodic heartbeats for ESC checking
        try:
            while True:
                try:
                    # Wait for data with very short timeout for responsive ESC checking
                    response = data_queue.get(timeout=0.02)  # 20ms for responsive ESC
                    yield response
                    if response.done:
                        return
                except queue.Empty:
                    # No data yet - yield heartbeat for ESC checking
                    yield LLMResponse(content="", done=False)

                    # Check if thread is still alive
                    if not thread.is_alive():
                        # Thread finished but queue is empty - should not happen normally
                        return
        finally:
            # Signal thread to stop on cleanup
            stop_flag.set()

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

        # Fallback: Try to parse tool calls from content if no native tool calls
        if not tool_calls and content:
            parsed = self._try_parse_json_tool_call(content)
            if parsed:
                tool_calls = parsed
                content = ""  # Clear content since it was a tool call

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            done=True,
        )

    def _try_parse_json_tool_call(self, content: str) -> list[ToolCall]:
        """
        Try to parse tool calls from JSON in content.

        Some models output tool calls as JSON text instead of using native format.
        This fallback detects and parses those.
        """
        import re

        tool_calls = []
        content = content.strip()

        # Quick check - if it doesn't look like JSON, skip
        if not (content.startswith("{") or content.startswith("[")):
            # Check for embedded JSON
            if '{"name"' not in content and '{"tool"' not in content:
                return tool_calls

        # Try to parse the whole content as JSON first
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                name = data.get("name") or data.get("tool") or data.get("function")
                args = data.get("arguments") or data.get("args") or data.get("parameters") or data.get("input") or {}
                if name:
                    tool_calls.append(ToolCall(
                        id="text_call_0",
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    ))
                    return tool_calls
            elif isinstance(data, list):
                # Handle array of tool calls
                for idx, item in enumerate(data):
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("tool") or item.get("function")
                        args = item.get("arguments") or item.get("args") or item.get("parameters") or item.get("input") or {}
                        if name:
                            tool_calls.append(ToolCall(
                                id=f"text_call_{idx}",
                                name=name,
                                arguments=args if isinstance(args, dict) else {},
                            ))
                return tool_calls
        except json.JSONDecodeError:
            pass

        # Try to find embedded JSON objects that look like tool calls
        json_pattern = r'\{[^{}]*"(?:name|tool|function)"[^{}]*:[^{}]*"[^"]+?"[^}]*\}'
        matches = re.findall(json_pattern, content, re.DOTALL)
        for idx, match in enumerate(matches):
            try:
                # Try to complete the JSON if it has nested braces
                data = json.loads(match)
                name = data.get("name") or data.get("tool") or data.get("function")
                args = data.get("arguments") or data.get("args") or data.get("parameters") or data.get("input") or {}
                if name:
                    tool_calls.append(ToolCall(
                        id=f"text_call_{idx}",
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    ))
            except json.JSONDecodeError:
                continue

        return tool_calls

    def _is_json_tool_response(self, content: str) -> bool:
        """Check if content looks like a JSON tool call that should not be displayed."""
        content = content.strip()
        if not content:
            return False

        # Quick patterns that indicate JSON tool output
        if content.startswith("{") and ('"name"' in content or '"tool"' in content or '"function"' in content):
            try:
                data = json.loads(content)
                if isinstance(data, dict) and (data.get("name") or data.get("tool") or data.get("function")):
                    return True
            except json.JSONDecodeError:
                pass

        return False


def get_provider(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> OllamaProvider:
    """
    Get an Ollama provider instance.

    Convenience function for creating a provider with default settings.
    """
    return OllamaProvider(base_url=base_url, model=model)
