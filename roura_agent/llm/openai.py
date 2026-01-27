"""
Roura Agent OpenAI Provider - LLM provider for OpenAI GPT models.

© Roura.io
"""
from __future__ import annotations

import json
import os
from typing import Any, Generator, Optional

from .base import LLMProvider, LLMResponse, ToolCall, ProviderType


class OpenAIProvider(LLMProvider):
    """
    OpenAI LLM provider with function calling support.

    Supports GPT-4, GPT-4-Turbo, and GPT-3.5-Turbo models.
    """

    # Models with function calling support
    FUNCTION_CALLING_MODELS = {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4-1106-preview",
        "gpt-4-0125-preview",
        "gpt-4",
        "gpt-4-0613",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-1106",
    }

    DEFAULT_MODEL = "gpt-4o"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        organization: Optional[str] = None,
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (default: OPENAI_API_KEY env var)
            model: Model name (default: gpt-4o)
            base_url: API base URL (for compatible APIs)
            timeout: Request timeout in seconds
            organization: OpenAI organization ID
        """
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model or os.getenv("OPENAI_MODEL", self.DEFAULT_MODEL)
        self._base_url = (
            base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self._timeout = timeout
        self._organization = organization or os.getenv("OPENAI_ORG_ID")

        if not self._api_key:
            from ..errors import RouraError, ErrorCode
            raise RouraError(
                ErrorCode.API_KEY_NOT_SET,
                message="OpenAI API key not configured",
            )

    @property
    def model_name(self) -> str:
        """Get the current model name."""
        return self._model

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.OPENAI

    def supports_tools(self) -> bool:
        """Check if current model supports function calling."""
        model_base = self._model.lower()
        return any(fc_model in model_base for fc_model in self.FUNCTION_CALLING_MODELS)

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        return headers

    def _convert_tools_to_functions(self, tools: list[dict]) -> list[dict]:
        """Convert tool definitions to OpenAI function format."""
        functions = []
        for tool in tools:
            if tool.get("type") == "function":
                functions.append(tool)
            else:
                # Wrap in function format
                functions.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    }
                })
        return functions

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        import httpx
        from ..errors import RouraError, ErrorCode

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        if tools and self.supports_tools():
            payload["tools"] = self._convert_tools_to_functions(tools)
            payload["tool_choice"] = "auto"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )

                if response.status_code == 401:
                    raise RouraError(ErrorCode.API_KEY_INVALID, message="Invalid OpenAI API key")
                if response.status_code == 429:
                    raise RouraError(ErrorCode.RATE_LIMIT_EXCEEDED, message="OpenAI rate limit exceeded")

                response.raise_for_status()
                data = response.json()

            return self._parse_response(data)

        except RouraError:
            raise
        except httpx.TimeoutException as e:
            error = RouraError(ErrorCode.OLLAMA_TIMEOUT, message="OpenAI request timed out", cause=e)
            return LLMResponse(error=error.message)
        except httpx.HTTPError as e:
            return LLMResponse(error=f"OpenAI API error: {str(e)}")
        except Exception as e:
            return LLMResponse(error=f"Unexpected error: {str(e)}")

    def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Generator[LLMResponse, None, None]:
        """
        Streaming chat completion with function call accumulation.

        Yields partial responses as tokens arrive.
        """
        import httpx
        from ..errors import RouraError, ErrorCode

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if tools and self.supports_tools():
            payload["tools"] = self._convert_tools_to_functions(tools)
            payload["tool_choice"] = "auto"

        content_buffer: list[str] = []
        tool_calls_buffer: dict[int, dict] = {}

        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload,
                timeout=self._timeout,
            ) as response:
                if response.status_code == 401:
                    yield LLMResponse(error="Invalid OpenAI API key", done=True)
                    return
                if response.status_code == 429:
                    yield LLMResponse(error="OpenAI rate limit exceeded", done=True)
                    return

                response.raise_for_status()

                for line in response.iter_lines():
                    if not line or line == "data: [DONE]":
                        continue

                    if line.startswith("data: "):
                        line = line[6:]

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")

                    # Accumulate content
                    if content := delta.get("content"):
                        content_buffer.append(content)

                    # Accumulate tool calls
                    if tool_calls := delta.get("tool_calls"):
                        self._accumulate_tool_calls(tool_calls, tool_calls_buffer)

                    # Yield partial response
                    yield LLMResponse(
                        content="".join(content_buffer),
                        done=finish_reason is not None,
                    )

                    if finish_reason:
                        break

        except httpx.TimeoutException:
            yield LLMResponse(error="OpenAI request timed out", done=True)
            return
        except httpx.HTTPError as e:
            yield LLMResponse(error=f"OpenAI API error: {str(e)}", done=True)
            return
        except Exception as e:
            yield LLMResponse(error=f"Unexpected error: {str(e)}", done=True)
            return

        # Build final tool calls
        final_tool_calls = self._build_tool_calls(tool_calls_buffer)

        # Yield final complete response
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

            # Update ID if provided
            if tc_id := tc.get("id"):
                buffer[idx]["id"] = tc_id

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

            # Use provided ID or generate one
            tc_id = tc_data.get("id") or f"call_{idx}"

            tool_calls.append(ToolCall(
                id=tc_id,
                name=func.get("name", ""),
                arguments=args,
            ))

        return tool_calls

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse a non-streaming response."""
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(error="No response from OpenAI")

        message = choices[0].get("message", {})
        content = message.get("content", "") or ""

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
