"""
Roura Agent Anthropic Provider - LLM provider for Claude models.

© Roura.io
"""
from __future__ import annotations

import json
import os
from typing import Any, Generator, Optional

from .base import LLMProvider, LLMResponse, ToolCall, ProviderType


class AnthropicProvider(LLMProvider):
    """
    Anthropic LLM provider with tool use support.

    Supports Claude 3, Claude 3.5, and Claude 4 models.
    """

    # Models with tool use support
    TOOL_CAPABLE_MODELS = {
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    }

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    API_VERSION = "2023-06-01"
    MAX_TOKENS = 4096

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        max_tokens: int = MAX_TOKENS,
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (default: ANTHROPIC_API_KEY env var)
            model: Model name (default: claude-sonnet-4-20250514)
            base_url: API base URL
            timeout: Request timeout in seconds
            max_tokens: Maximum tokens in response
        """
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._model = model or os.getenv("ANTHROPIC_MODEL", self.DEFAULT_MODEL)
        self._base_url = (
            base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        ).rstrip("/")
        self._timeout = timeout
        self._max_tokens = max_tokens

        if not self._api_key:
            from ..errors import RouraError, ErrorCode
            raise RouraError(
                ErrorCode.API_KEY_NOT_SET,
                message="Anthropic API key not configured",
            )

    @property
    def model_name(self) -> str:
        """Get the current model name."""
        return self._model

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.ANTHROPIC

    def supports_tools(self) -> bool:
        """Check if current model supports tool use."""
        # All Claude 3+ models support tool use
        return "claude-3" in self._model.lower() or "claude-sonnet-4" in self._model.lower()

    def supports_vision(self) -> bool:
        """Check if current model supports vision/image input."""
        # All Claude 3+ models support vision
        return "claude-3" in self._model.lower() or "claude-sonnet-4" in self._model.lower()

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def _convert_messages(self, messages: list[dict]) -> tuple[Optional[str], list[dict]]:
        """
        Convert messages to Anthropic format.

        Anthropic uses a separate system parameter, not a system message.
        Also handles tool results differently.

        Returns:
            Tuple of (system_prompt, converted_messages)
        """
        system_prompt = None
        converted = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""  # Ensure not None

            if role == "system":
                system_prompt = content
                continue

            if role == "tool":
                # Convert tool result to Anthropic format
                # Ensure content is a string
                tool_content = content if content else "OK"
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": tool_content,
                    }]
                })
                continue

            if role == "assistant" and msg.get("tool_calls"):
                # Assistant message with tool calls
                content_blocks = []
                if content:
                    content_blocks.append({"type": "text", "text": content})

                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    args_str = func.get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except json.JSONDecodeError:
                        args = {}

                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": args,
                    })

                converted.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
                continue

            # Regular message - skip empty content for non-user roles
            if not content and role != "user":
                continue

            # Ensure user messages have content
            if role == "user" and not content:
                content = "."  # Anthropic requires non-empty content

            converted.append({
                "role": role,
                "content": content,
            })

        # Anthropic requires messages to start with user role
        # and alternate between user and assistant
        return system_prompt, self._ensure_valid_message_order(converted)

    def _ensure_valid_message_order(self, messages: list[dict]) -> list[dict]:
        """
        Ensure messages follow Anthropic's requirements:
        - Must start with 'user' role
        - Must alternate between 'user' and 'assistant'
        - Consecutive same-role messages should be merged
        """
        if not messages:
            return messages

        result = []

        for msg in messages:
            if not result:
                # First message must be user
                if msg["role"] != "user":
                    # Prepend a user message
                    result.append({"role": "user", "content": "Continue."})
                result.append(msg)
            else:
                last_role = result[-1]["role"]
                current_role = msg["role"]

                if current_role == last_role:
                    # Merge consecutive same-role messages
                    last_content = result[-1]["content"]
                    new_content = msg["content"]

                    if isinstance(last_content, str) and isinstance(new_content, str):
                        result[-1]["content"] = last_content + "\n" + new_content
                    elif isinstance(last_content, list) and isinstance(new_content, list):
                        result[-1]["content"] = last_content + new_content
                    elif isinstance(last_content, str) and isinstance(new_content, list):
                        result[-1]["content"] = [{"type": "text", "text": last_content}] + new_content
                    elif isinstance(last_content, list) and isinstance(new_content, str):
                        result[-1]["content"] = last_content + [{"type": "text", "text": new_content}]
                else:
                    result.append(msg)

        return result

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert tool definitions to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })
            else:
                anthropic_tools.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {}),
                })
        return anthropic_tools

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        import httpx
        from ..errors import RouraError, ErrorCode

        system_prompt, converted_messages = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": converted_messages,
            "max_tokens": self._max_tokens,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools and self.supports_tools():
            payload["tools"] = self._convert_tools(tools)

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/v1/messages",
                    headers=self._get_headers(),
                    json=payload,
                )

                if response.status_code == 401:
                    raise RouraError(ErrorCode.API_KEY_INVALID, message="Invalid Anthropic API key")
                if response.status_code == 429:
                    raise RouraError(ErrorCode.RATE_LIMIT_EXCEEDED, message="Anthropic rate limit exceeded")

                response.raise_for_status()
                data = response.json()

            return self._parse_response(data)

        except RouraError:
            raise
        except httpx.TimeoutException as e:
            error = RouraError(ErrorCode.OLLAMA_TIMEOUT, message="Anthropic request timed out", cause=e)
            return LLMResponse(error=error.message)
        except httpx.HTTPError as e:
            return LLMResponse(error=f"Anthropic API error: {str(e)}")
        except Exception as e:
            return LLMResponse(error=f"Unexpected error: {str(e)}")

    def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Generator[LLMResponse, None, None]:
        """
        Streaming chat completion with tool use accumulation.

        Yields partial responses as tokens arrive.
        """
        import httpx

        system_prompt, converted_messages = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": converted_messages,
            "max_tokens": self._max_tokens,
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools and self.supports_tools():
            payload["tools"] = self._convert_tools(tools)

        content_buffer: list[str] = []
        tool_calls_buffer: dict[int, dict] = {}
        current_tool_idx = 0

        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/v1/messages",
                headers=self._get_headers(),
                json=payload,
                timeout=self._timeout,
            ) as response:
                if response.status_code == 401:
                    yield LLMResponse(error="Invalid Anthropic API key", done=True)
                    return
                if response.status_code == 429:
                    yield LLMResponse(error="Anthropic rate limit exceeded", done=True)
                    return
                if response.status_code == 400:
                    # Try to get error details from response
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("error", {}).get("message", "Bad request")
                        yield LLMResponse(error=f"Anthropic API error: {error_msg}", done=True)
                    except Exception:
                        yield LLMResponse(error="Anthropic API error: Bad request", done=True)
                    return

                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue

                    if line.startswith("data: "):
                        line = line[6:]

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("type", "")

                    if event_type == "content_block_start":
                        block = data.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_calls_buffer[current_tool_idx] = {
                                "id": block.get("id", f"call_{current_tool_idx}"),
                                "name": block.get("name", ""),
                                "input": "",
                            }

                    elif event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        delta_type = delta.get("type", "")

                        if delta_type == "text_delta":
                            content_buffer.append(delta.get("text", ""))
                        elif delta_type == "input_json_delta":
                            if current_tool_idx in tool_calls_buffer:
                                tool_calls_buffer[current_tool_idx]["input"] += delta.get("partial_json", "")

                    elif event_type == "content_block_stop":
                        block_idx = data.get("index", 0)
                        if block_idx in tool_calls_buffer or current_tool_idx in tool_calls_buffer:
                            current_tool_idx += 1

                    elif event_type == "message_stop":
                        break

                    # Yield partial response
                    yield LLMResponse(
                        content="".join(content_buffer),
                        done=False,
                    )

        except httpx.TimeoutException:
            yield LLMResponse(error="Anthropic request timed out", done=True)
            return
        except httpx.HTTPError as e:
            yield LLMResponse(error=f"Anthropic API error: {str(e)}", done=True)
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

    def _build_tool_calls(self, buffer: dict[int, dict]) -> list[ToolCall]:
        """Build ToolCall objects from accumulated buffer."""
        tool_calls = []

        for idx in sorted(buffer.keys()):
            tc_data = buffer[idx]

            # Parse input JSON
            input_str = tc_data.get("input", "{}")
            try:
                args = json.loads(input_str) if input_str else {}
            except json.JSONDecodeError:
                args = {}

            tool_calls.append(ToolCall(
                id=tc_data.get("id", f"call_{idx}"),
                name=tc_data.get("name", ""),
                arguments=args,
            ))

        return tool_calls

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse a non-streaming response."""
        content_parts = []
        tool_calls = []

        for idx, block in enumerate(data.get("content", [])):
            block_type = block.get("type", "")

            if block_type == "text":
                content_parts.append(block.get("text", ""))

            elif block_type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id", f"call_{idx}"),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))

        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            done=True,
        )

    def chat_with_images(
        self,
        prompt: str,
        images: list[dict],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Chat with image content using Claude's vision capabilities.

        Args:
            prompt: Text prompt to accompany images
            images: List of image dicts in Anthropic format:
                    {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}
                    or {"type": "image", "source": {"type": "url", "url": "..."}}
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with the model's response
        """
        import httpx
        from ..errors import RouraError, ErrorCode

        if not self.supports_vision():
            return LLMResponse(error=f"Model {self._model} does not support vision")

        # Build message content with images and text
        content = []
        for img in images:
            if img.get("type") == "image":
                content.append(img)

        # Add text prompt
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/v1/messages",
                    headers=self._get_headers(),
                    json=payload,
                )

                if response.status_code == 401:
                    raise RouraError(ErrorCode.API_KEY_INVALID, message="Invalid Anthropic API key")
                if response.status_code == 429:
                    raise RouraError(ErrorCode.RATE_LIMIT_EXCEEDED, message="Anthropic rate limit exceeded")

                response.raise_for_status()
                data = response.json()

            return self._parse_response(data)

        except RouraError:
            raise
        except httpx.TimeoutException as e:
            return LLMResponse(error="Vision request timed out")
        except httpx.HTTPError as e:
            return LLMResponse(error=f"Anthropic API error: {str(e)}")
        except Exception as e:
            return LLMResponse(error=f"Unexpected error: {str(e)}")
