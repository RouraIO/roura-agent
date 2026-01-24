"""
Roura Agent Streaming - Token streaming with ESC interrupt support.
"""
from __future__ import annotations

import sys
import select
import termios
import tty
from typing import Generator, Optional, Callable
from dataclasses import dataclass

import httpx
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from .ollama import get_base_url, get_model


@dataclass
class StreamResult:
    """Result of a streaming operation."""
    content: str
    interrupted: bool
    error: Optional[str] = None


def check_for_escape() -> bool:
    """Check if ESC key was pressed (non-blocking)."""
    if sys.stdin.isatty():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            # Non-blocking check
            if select.select([sys.stdin], [], [], 0.0)[0]:
                char = sys.stdin.read(1)
                if char == '\x1b':  # ESC
                    return True
        except Exception:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return False


def stream_generate(
    prompt: str,
    system: Optional[str] = None,
    on_token: Optional[Callable[[str], None]] = None,
) -> StreamResult:
    """
    Stream a generation from Ollama with ESC interrupt support.

    Args:
        prompt: The user prompt
        system: Optional system prompt
        on_token: Optional callback for each token

    Returns:
        StreamResult with content, interrupted flag, and optional error
    """
    base_url = get_base_url()
    model = get_model()

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }

    if system:
        payload["system"] = system

    content_parts = []
    interrupted = False

    try:
        with httpx.stream(
            "POST",
            f"{base_url}/api/generate",
            json=payload,
            timeout=120.0,
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                # Check for ESC interrupt
                if check_for_escape():
                    interrupted = True
                    break

                if line:
                    import json
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            content_parts.append(token)
                            if on_token:
                                on_token(token)

                        # Check if done
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

        return StreamResult(
            content="".join(content_parts),
            interrupted=interrupted,
        )

    except httpx.TimeoutException:
        return StreamResult(
            content="".join(content_parts),
            interrupted=False,
            error="Request timed out",
        )
    except httpx.HTTPError as e:
        return StreamResult(
            content="".join(content_parts),
            interrupted=False,
            error=str(e),
        )


def stream_chat(
    messages: list[dict],
    on_token: Optional[Callable[[str], None]] = None,
) -> StreamResult:
    """
    Stream a chat completion from Ollama with ESC interrupt support.

    Args:
        messages: List of message dicts with role and content
        on_token: Optional callback for each token

    Returns:
        StreamResult with content, interrupted flag, and optional error
    """
    base_url = get_base_url()
    model = get_model()

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    content_parts = []
    interrupted = False

    try:
        with httpx.stream(
            "POST",
            f"{base_url}/api/chat",
            json=payload,
            timeout=120.0,
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                # Check for ESC interrupt
                if check_for_escape():
                    interrupted = True
                    break

                if line:
                    import json
                    try:
                        data = json.loads(line)
                        message = data.get("message", {})
                        token = message.get("content", "")
                        if token:
                            content_parts.append(token)
                            if on_token:
                                on_token(token)

                        # Check if done
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

        return StreamResult(
            content="".join(content_parts),
            interrupted=interrupted,
        )

    except httpx.TimeoutException:
        return StreamResult(
            content="".join(content_parts),
            interrupted=False,
            error="Request timed out",
        )
    except httpx.HTTPError as e:
        return StreamResult(
            content="".join(content_parts),
            interrupted=False,
            error=str(e),
        )


class StreamingChat:
    """
    Rich-enabled streaming chat with ESC interrupt.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.buffer = ""

    def stream_response(
        self,
        messages: list[dict],
        show_cursor: bool = True,
    ) -> StreamResult:
        """
        Stream a response with live Rich rendering.

        Press ESC to interrupt.
        """
        self.buffer = ""

        def on_token(token: str):
            self.buffer += token

        # Show interrupt hint
        self.console.print("[dim]Press ESC to interrupt[/dim]", end="\r")

        with Live(
            Text("▊", style="bold cyan"),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            result = stream_chat(messages, on_token=on_token)

            # Update display as we stream
            def update_display():
                if self.buffer:
                    # Render as markdown for nice formatting
                    try:
                        live.update(Markdown(self.buffer + ("▊" if not result.interrupted else "")))
                    except Exception:
                        live.update(Text(self.buffer + ("▊" if not result.interrupted else "")))

            # Final update
            update_display()

        # Print final content
        if result.content:
            try:
                self.console.print(Markdown(result.content))
            except Exception:
                self.console.print(result.content)

        if result.interrupted:
            self.console.print("\n[yellow]Interrupted[/yellow]")

        if result.error:
            self.console.print(f"[red]Error: {result.error}[/red]")

        return result
