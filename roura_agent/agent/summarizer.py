"""
Roura Agent Context Summarizer - Manage context window by compressing old messages.

When the context approaches the token limit, this module:
1. Keeps the system prompt and recent messages
2. Summarizes older messages into a compressed form
3. Replaces old messages with the summary

© Roura.io
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .context import Message


@dataclass
class SummarizationConfig:
    """Configuration for context summarization."""

    # Trigger summarization at this percentage of max tokens
    trigger_threshold: float = 0.75

    # Keep this many recent messages (excluding system)
    keep_recent_messages: int = 10

    # Maximum tokens to use for the summary
    max_summary_tokens: int = 500


def estimate_message_tokens(messages: list[Message]) -> int:
    """Estimate total tokens for a list of messages."""
    return sum(msg.estimate_tokens() for msg in messages)


def should_summarize(
    messages: list[Message],
    max_context_tokens: int,
    config: Optional[SummarizationConfig] = None,
) -> bool:
    """
    Check if context should be summarized.

    Args:
        messages: Current message list
        max_context_tokens: Maximum context window size
        config: Summarization configuration

    Returns:
        True if summarization should be triggered
    """
    config = config or SummarizationConfig()
    current_tokens = estimate_message_tokens(messages)
    threshold = max_context_tokens * config.trigger_threshold

    return current_tokens > threshold


def create_summary_prompt(messages: list[Message]) -> str:
    """
    Create a prompt to summarize messages.

    Args:
        messages: Messages to summarize

    Returns:
        A prompt that can be sent to an LLM for summarization
    """
    parts = ["Summarize the following conversation concisely, keeping key information:\n"]

    for msg in messages:
        if msg.role == "system":
            continue  # Don't include system prompt in summary
        elif msg.role == "user":
            parts.append(f"User: {msg.content[:500]}...")
        elif msg.role == "assistant":
            content = msg.content[:500] if msg.content else "[tool calls]"
            parts.append(f"Assistant: {content}...")
        elif msg.role == "tool":
            parts.append(f"Tool result: {msg.content[:200]}...")

    parts.append("\nProvide a brief summary of what was discussed and accomplished.")

    return "\n".join(parts)


def create_local_summary(messages: list[Message]) -> str:
    """
    Create a simple local summary without using LLM.

    This is a fallback when we can't call the LLM for summarization.

    Args:
        messages: Messages to summarize

    Returns:
        A compact summary string
    """
    user_queries = []
    tools_used = set()
    files_mentioned = set()

    for msg in messages:
        if msg.role == "user":
            # Extract first line or first 100 chars
            first_line = msg.content.split("\n")[0][:100]
            user_queries.append(first_line)

        elif msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    if name:
                        tools_used.add(name)

        elif msg.role == "tool":
            # Try to extract file paths from tool results
            try:
                import json
                data = json.loads(msg.content)
                if isinstance(data, dict):
                    if "path" in data:
                        files_mentioned.add(data["path"])
                    if "files" in data and isinstance(data["files"], list):
                        for f in data["files"][:5]:
                            if isinstance(f, dict) and "path" in f:
                                files_mentioned.add(f["path"])
            except (json.JSONDecodeError, TypeError):
                pass

    parts = ["[Previous conversation summary]"]

    if user_queries:
        parts.append(f"User asked about: {'; '.join(user_queries[:5])}")

    if tools_used:
        parts.append(f"Tools used: {', '.join(sorted(tools_used))}")

    if files_mentioned:
        parts.append(f"Files involved: {', '.join(sorted(files_mentioned)[:10])}")

    return "\n".join(parts)


def summarize_context(
    messages: list[Message],
    config: Optional[SummarizationConfig] = None,
) -> list[Message]:
    """
    Summarize old messages to reduce context size.

    This function:
    1. Keeps the system message
    2. Summarizes older messages
    3. Keeps recent messages intact

    Args:
        messages: Current message list
        config: Summarization configuration

    Returns:
        New message list with summarized context
    """
    config = config or SummarizationConfig()

    if len(messages) <= config.keep_recent_messages + 1:
        return messages  # Nothing to summarize

    # Separate system message
    system_msg = None
    other_messages = []

    for msg in messages:
        if msg.role == "system" and system_msg is None:
            system_msg = msg
        else:
            other_messages.append(msg)

    # Keep recent messages
    if len(other_messages) <= config.keep_recent_messages:
        return messages  # Nothing to summarize

    to_summarize = other_messages[:-config.keep_recent_messages]
    to_keep = other_messages[-config.keep_recent_messages:]

    # Create summary
    summary_text = create_local_summary(to_summarize)

    # Create summary message
    summary_msg = Message(
        role="system",
        content=summary_text,
    )

    # Build new message list
    result = []
    if system_msg:
        result.append(system_msg)
    result.append(summary_msg)
    result.extend(to_keep)

    return result


class ContextSummarizer:
    """
    Manages context summarization for an agent.

    Usage:
        summarizer = ContextSummarizer()
        if summarizer.should_summarize(context.messages, context.max_context_tokens):
            context.messages = summarizer.summarize(context.messages)
    """

    def __init__(self, config: Optional[SummarizationConfig] = None):
        self.config = config or SummarizationConfig()

    def should_summarize(
        self,
        messages: list[Message],
        max_context_tokens: int,
    ) -> bool:
        """Check if summarization should be triggered."""
        return should_summarize(messages, max_context_tokens, self.config)

    def summarize(self, messages: list[Message]) -> list[Message]:
        """Summarize messages to reduce context size."""
        return summarize_context(messages, self.config)

    def get_stats(self, messages: list[Message], max_context_tokens: int) -> dict:
        """Get context statistics."""
        current_tokens = estimate_message_tokens(messages)
        return {
            "message_count": len(messages),
            "estimated_tokens": current_tokens,
            "max_tokens": max_context_tokens,
            "usage_percent": int((current_tokens / max_context_tokens) * 100),
            "should_summarize": self.should_summarize(messages, max_context_tokens),
        }
