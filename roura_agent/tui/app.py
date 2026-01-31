"""
Roura Agent TUI Application - Textual-based terminal interface.

Features:
- Split pane layout with chat and diff views
- Real-time streaming display
- Per-hunk diff approval
- Keyboard shortcuts
- File tree sidebar

© Roura.io
"""
from __future__ import annotations

from typing import Optional

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Footer,
        Header,
        Input,
        Label,
        Static,
        TextArea,
    )
except ImportError:
    raise ImportError(
        "TUI requires textual. Install with: pip install roura-agent[tui]"
    )

from ..branding import Colors
from ..constants import VERSION
from .keybindings import KeyBindings, load_keybindings


class ChatPane(Static):
    """Chat/conversation pane showing agent responses."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: list[tuple[str, str]] = []  # (role, content)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the chat."""
        self.messages.append((role, content))
        self._render_messages()

    def _render_messages(self) -> None:
        """Render all messages."""
        lines = []
        for role, content in self.messages[-20:]:  # Show last 20 messages
            if role == "user":
                lines.append(f"[bold cyan]You:[/bold cyan] {content}")
            elif role == "assistant":
                lines.append(f"[bold green]Agent:[/bold green] {content}")
            else:
                lines.append(f"[dim]{role}:[/dim] {content}")
            lines.append("")

        self.update("\n".join(lines) if lines else "[dim]Start typing to chat...[/dim]")

    def clear(self) -> None:
        """Clear chat history."""
        self.messages.clear()
        self._render_messages()


class DiffPane(Static):
    """Diff viewer pane with syntax highlighting."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_diff: Optional[str] = None
        self.hunks: list[dict] = []
        self.current_hunk: int = 0

    def show_diff(self, diff_text: str) -> None:
        """Display a diff."""
        self.current_diff = diff_text
        self._render_diff()

    def _render_diff(self) -> None:
        """Render the diff with colors."""
        if not self.current_diff:
            self.update("[dim]No diff to display[/dim]")
            return

        lines = []
        for line in self.current_diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                lines.append(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                lines.append(f"[cyan]{line}[/cyan]")
            elif line.startswith("---") or line.startswith("+++"):
                lines.append(f"[bold]{line}[/bold]")
            else:
                lines.append(f"[dim]{line}[/dim]")

        self.update("\n".join(lines))

    def next_hunk(self) -> None:
        """Navigate to next hunk."""
        if self.hunks and self.current_hunk < len(self.hunks) - 1:
            self.current_hunk += 1
            self._render_diff()

    def prev_hunk(self) -> None:
        """Navigate to previous hunk."""
        if self.hunks and self.current_hunk > 0:
            self.current_hunk -= 1
            self._render_diff()

    def clear(self) -> None:
        """Clear the diff display."""
        self.current_diff = None
        self.hunks.clear()
        self.current_hunk = 0
        self._render_diff()


class OutputPane(Static):
    """Output pane for tool execution results."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_lines: list[str] = []

    def add_output(self, text: str) -> None:
        """Add output text."""
        self.output_lines.append(text)
        self._render_output()

    def _render_output(self) -> None:
        """Render output."""
        # Keep last 100 lines
        self.output_lines = self.output_lines[-100:]
        self.update("\n".join(self.output_lines) if self.output_lines else "[dim]No output[/dim]")

    def clear(self) -> None:
        """Clear output."""
        self.output_lines.clear()
        self._render_output()


class StatusBar(Static):
    """Status bar showing current state."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.status = "Ready"
        self.model = "Not connected"
        self.files_count = 0

    def set_status(self, status: str) -> None:
        """Update status."""
        self.status = status
        self._render()

    def set_model(self, model: str) -> None:
        """Update model info."""
        self.model = model
        self._render()

    def set_files(self, count: int) -> None:
        """Update file count."""
        self.files_count = count
        self._render()

    def _render(self) -> None:
        """Render the status bar."""
        self.update(
            f"[bold]{self.status}[/bold] | "
            f"Model: [cyan]{self.model}[/cyan] | "
            f"Files: {self.files_count}"
        )


class MainScreen(Screen):
    """Main TUI screen with split panes."""

    CSS = """
    MainScreen {
        layout: grid;
        grid-size: 2 3;
        grid-rows: 1fr 1fr 3;
    }

    #chat-pane {
        column-span: 1;
        row-span: 2;
        border: solid green;
        padding: 1;
        overflow-y: auto;
    }

    #diff-pane {
        column-span: 1;
        row-span: 1;
        border: solid cyan;
        padding: 1;
        overflow-y: auto;
    }

    #output-pane {
        column-span: 1;
        row-span: 1;
        border: solid yellow;
        padding: 1;
        overflow-y: auto;
    }

    #input-container {
        column-span: 2;
        dock: bottom;
        height: 3;
    }

    #input-field {
        width: 100%;
    }

    .pane-title {
        dock: top;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the layout."""
        yield Container(
            Label("Chat", classes="pane-title"),
            ChatPane(id="chat-pane"),
            id="chat-container",
        )
        yield Container(
            Label("Diff", classes="pane-title"),
            DiffPane(id="diff-pane"),
            id="diff-container",
        )
        yield Container(
            Label("Output", classes="pane-title"),
            OutputPane(id="output-pane"),
            id="output-container",
        )
        yield Container(
            Input(placeholder="Type a message...", id="input-field"),
            id="input-container",
        )


class RouraApp(App):
    """
    Roura Agent TUI Application.

    A split-pane terminal interface for interacting with the AI agent.
    """

    TITLE = f"Roura Agent v{VERSION}"
    CSS_PATH = None  # Using inline CSS

    BINDINGS = [
        Binding("ctrl+c", "cancel", "Cancel"),
        Binding("ctrl+d", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("f1", "help", "Help"),
        Binding("f2", "toggle_diff", "Toggle Diff"),
        Binding("f3", "toggle_output", "Toggle Output"),
        Binding("escape", "dismiss", "Dismiss"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        dock: top;
    }

    Footer {
        dock: bottom;
    }

    #main-container {
        height: 100%;
        width: 100%;
    }

    #left-pane {
        width: 50%;
        height: 100%;
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }

    #right-pane {
        width: 50%;
        height: 100%;
    }

    #diff-pane {
        height: 50%;
        border: solid $secondary;
        padding: 1;
        overflow-y: auto;
    }

    #output-pane {
        height: 50%;
        border: solid $warning;
        padding: 1;
        overflow-y: auto;
    }

    #input-area {
        dock: bottom;
        height: 3;
        padding: 0 1;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.keybindings = load_keybindings()
        self.diff_visible = True
        self.output_visible = True

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()

        with Horizontal(id="main-container"):
            with Vertical(id="left-pane"):
                yield Label("Chat", classes="pane-title")
                yield ChatPane(id="chat")

            with Vertical(id="right-pane"):
                with Container(id="diff-container"):
                    yield Label("Diff", classes="pane-title")
                    yield DiffPane(id="diff")

                with Container(id="output-container"):
                    yield Label("Output", classes="pane-title")
                    yield OutputPane(id="output")

        with Container(id="input-area"):
            yield Input(placeholder="Type a message... (Ctrl+D to quit)", id="input")

        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount."""
        # Focus the input
        self.query_one("#input", Input).focus()

        # Set initial status
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.set_status("Ready")
        status_bar.set_model("Not connected")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        message = event.value.strip()
        if not message:
            return

        # Clear input
        event.input.value = ""

        # Add to chat
        chat = self.query_one("#chat", ChatPane)
        chat.add_message("user", message)

        # Update status
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.set_status("Processing...")

        # TODO: Send to agent and stream response
        # For now, just echo
        chat.add_message("assistant", f"Echo: {message}")
        status_bar.set_status("Ready")

    def action_cancel(self) -> None:
        """Handle cancel action."""
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.set_status("Cancelled")

    def action_clear(self) -> None:
        """Clear all panes."""
        self.query_one("#chat", ChatPane).clear()
        self.query_one("#diff", DiffPane).clear()
        self.query_one("#output", OutputPane).clear()

    def action_toggle_diff(self) -> None:
        """Toggle diff pane visibility."""
        container = self.query_one("#diff-container", Container)
        container.display = not container.display
        self.diff_visible = container.display

    def action_toggle_output(self) -> None:
        """Toggle output pane visibility."""
        container = self.query_one("#output-container", Container)
        container.display = not container.display
        self.output_visible = container.display

    def action_help(self) -> None:
        """Show help."""
        output = self.query_one("#output", OutputPane)
        output.add_output("=== Keyboard Shortcuts ===")
        for binding in self.keybindings.bindings[:10]:
            output.add_output(f"  {binding.key}: {binding.description}")

    def show_diff(self, diff_text: str) -> None:
        """Show a diff in the diff pane."""
        diff_pane = self.query_one("#diff", DiffPane)
        diff_pane.show_diff(diff_text)

    def add_output(self, text: str) -> None:
        """Add output to the output pane."""
        output_pane = self.query_one("#output", OutputPane)
        output_pane.add_output(text)

    def add_chat_message(self, role: str, content: str) -> None:
        """Add a message to the chat pane."""
        chat = self.query_one("#chat", ChatPane)
        chat.add_message(role, content)


def run_tui():
    """Run the TUI application."""
    app = RouraApp()
    app.run()


if __name__ == "__main__":
    run_tui()
