"""
Roura Agent Streaming - Live token streaming with ESC interrupt support.

© Roura.io
"""
from __future__ import annotations

import select
import sys
import termios
import tty
from dataclasses import dataclass
from typing import Callable, Optional

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

from .ollama import get_base_url, get_model


@dataclass
class StreamResult:
    """Result of a streaming operation."""
    content: str
    interrupted: bool
    error: Optional[str] = None


def check_for_escape() -> bool:
    """Check if ESC key was pressed (non-blocking, drains buffer)."""
    if not sys.stdin.isatty():
        return False

    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            # Drain all pending input and check for ESC
            found_escape = False
            while select.select([sys.stdin], [], [], 0)[0]:
                char = sys.stdin.read(1)
                if char == '\x1b':  # ESC
                    found_escape = True
                    # Drain any remaining escape sequence chars
                    while select.select([sys.stdin], [], [], 0.01)[0]:
                        sys.stdin.read(1)
                    break
            return found_escape
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass
    return False


class LiveStream:
    """
    Live streaming display with Rich.

    Shows tokens as they arrive with a blinking cursor effect.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.buffer = ""
        self.interrupted = False
        self.cursor_visible = True
        self._tick = 0

    def _render(self, show_cursor: bool = True, show_hint: bool = True) -> Text:
        """Render current buffer with optional cursor."""
        # Blink cursor every few ticks
        self._tick += 1
        cursor = "█" if (self._tick // 2) % 2 == 0 and show_cursor else " "

        content = Text()
        content.append(self.buffer)
        if show_cursor:
            content.append(cursor, style="bold cyan")

        return content

    def _render_with_hint(self) -> Group:
        """Render with ESC hint."""
        content = self._render(show_cursor=True)
        hint = Text("\n[dim]Press ESC to interrupt[/dim]", style="dim")
        return Group(content, hint)


def stream_chat_live(
    messages: list[dict],
    console: Optional[Console] = None,
) -> StreamResult:
    """
    Stream a chat completion with live token display.

    Shows each token as it arrives, with ESC to interrupt.
    """
    console = console or Console()
    base_url = get_base_url()
    model = get_model()

    if not model:
        return StreamResult(
            content="",
            interrupted=False,
            error="OLLAMA_MODEL not set",
        )

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    buffer = []
    interrupted = False
    error = None

    # Create live display
    with Live(
        Spinner("dots", text="Thinking...", style="cyan"),
        console=console,
        refresh_per_second=20,
        transient=True,
    ) as live:
        try:
            with httpx.stream(
                "POST",
                f"{base_url}/api/chat",
                json=payload,
                timeout=120.0,
            ) as response:
                response.raise_for_status()

                first_token = True
                tick = 0

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
                                buffer.append(token)
                                current_text = "".join(buffer)

                                # Update display with cursor
                                tick += 1
                                cursor = "█" if (tick // 2) % 2 == 0 else " "

                                display = Text()
                                display.append(current_text)
                                display.append(cursor, style="bold cyan")

                                if first_token:
                                    first_token = False

                                # Add hint at bottom
                                hint = Text("\n\nPress ESC to interrupt", style="dim")
                                live.update(Group(display, hint))

                            # Check if done
                            if data.get("done", False):
                                break

                        except json.JSONDecodeError:
                            continue

        except httpx.TimeoutException:
            error = "Request timed out"
        except httpx.HTTPError as e:
            error = str(e)
        except Exception as e:
            error = str(e)

    content = "".join(buffer)

    # Print final content with markdown formatting
    if content and not error:
        console.print()
        try:
            console.print(Markdown(content))
        except Exception:
            console.print(content)

    if interrupted:
        console.print("\n[yellow]⚡ Interrupted[/yellow]")

    if error:
        console.print(f"\n[red]Error: {error}[/red]")

    return StreamResult(
        content=content,
        interrupted=interrupted,
        error=error,
    )


def stream_generate_live(
    prompt: str,
    system: Optional[str] = None,
    console: Optional[Console] = None,
) -> StreamResult:
    """
    Stream a generation with live token display.
    """
    console = console or Console()
    base_url = get_base_url()
    model = get_model()

    if not model:
        return StreamResult(
            content="",
            interrupted=False,
            error="OLLAMA_MODEL not set",
        )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }

    if system:
        payload["system"] = system

    buffer = []
    interrupted = False
    error = None

    with Live(
        Spinner("dots", text="Thinking...", style="cyan"),
        console=console,
        refresh_per_second=20,
        transient=True,
    ) as live:
        try:
            with httpx.stream(
                "POST",
                f"{base_url}/api/generate",
                json=payload,
                timeout=120.0,
            ) as response:
                response.raise_for_status()

                tick = 0

                for line in response.iter_lines():
                    if check_for_escape():
                        interrupted = True
                        break

                    if line:
                        import json
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")

                            if token:
                                buffer.append(token)
                                current_text = "".join(buffer)

                                tick += 1
                                cursor = "█" if (tick // 2) % 2 == 0 else " "

                                display = Text()
                                display.append(current_text)
                                display.append(cursor, style="bold cyan")

                                hint = Text("\n\nPress ESC to interrupt", style="dim")
                                live.update(Group(display, hint))

                            if data.get("done", False):
                                break

                        except json.JSONDecodeError:
                            continue

        except httpx.TimeoutException:
            error = "Request timed out"
        except httpx.HTTPError as e:
            error = str(e)
        except Exception as e:
            error = str(e)

    content = "".join(buffer)

    if content and not error:
        console.print()
        try:
            console.print(Markdown(content))
        except Exception:
            console.print(content)

    if interrupted:
        console.print("\n[yellow]⚡ Interrupted[/yellow]")

    if error:
        console.print(f"\n[red]Error: {error}[/red]")

    return StreamResult(
        content=content,
        interrupted=interrupted,
        error=error,
    )


# Legacy compatibility
def stream_chat(
    messages: list[dict],
    on_token: Optional[Callable[[str], None]] = None,
) -> StreamResult:
    """
    Stream a chat completion (callback-based, for backward compatibility).
    """
    base_url = get_base_url()
    model = get_model()

    if not model:
        return StreamResult(
            content="",
            interrupted=False,
            error="OLLAMA_MODEL not set",
        )

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
