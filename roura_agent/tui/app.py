"""
Roura Agent TUI Application - Textual-based terminal interface.

Features:
- Split pane layout with chat and diff views
- Real-time streaming display
- Per-hunk diff approval
- Keyboard shortcuts
- File tree sidebar
- /review command for code review

© Roura.io
"""
from __future__ import annotations

import asyncio
from pathlib import Path
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

        # Handle slash commands
        if message.startswith("/"):
            await self._handle_command(message)
        else:
            # TODO: Send to agent and stream response
            # For now, just echo
            chat.add_message("assistant", f"Echo: {message}")

        status_bar.set_status("Ready")

    async def _handle_command(self, message: str) -> None:
        """Handle slash commands."""
        parts = message.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        chat = self.query_one("#chat", ChatPane)
        output = self.query_one("#output", OutputPane)

        if command == "/review":
            await self._run_review(args)
        elif command == "/help":
            self._show_command_help()
        elif command == "/clear":
            self.action_clear()
            chat.add_message("system", "Cleared all panes")
        else:
            chat.add_message("system", f"Unknown command: {command}")
            chat.add_message("system", "Available: /review, /help, /clear")

    async def _run_review(self, args: str) -> None:
        """Run code review."""
        import tempfile

        chat = self.query_one("#chat", ChatPane)
        output = self.query_one("#output", OutputPane)
        status_bar = self.query_one("#status-bar", StatusBar)

        # Parse arguments
        target_path = Path.cwd()
        files = []

        if args:
            # Check if it's a path or file list
            parts = args.split()
            for part in parts:
                if "," in part:
                    # Comma-separated file list
                    files.extend(f.strip() for f in part.split(",") if f.strip())
                elif Path(part).exists():
                    target_path = Path(part).resolve()
                else:
                    files.append(part)

        chat.add_message("system", f"Starting code review...")
        output.add_output(f"📂 Target: {target_path}")
        if files:
            output.add_output(f"📄 Files: {', '.join(files)}")

        status_bar.set_status("Reviewing code...")

        try:
            from ..pro.ci import CIConfig, CIMode, CIRunner, CIExitCode
            from ..pro.billing import BillingManager, BillingPlan

            # Run review in background to not block UI
            result = await asyncio.to_thread(
                self._execute_review, target_path, files
            )

            # Display results
            output.add_output("")
            output.add_output("═" * 40)
            output.add_output("CODE REVIEW RESULTS")
            output.add_output("═" * 40)
            output.add_output(result.summary)
            output.add_output("")

            if result.issues:
                for issue in result.issues:
                    severity_icon = {
                        "error": "🔴",
                        "warning": "🟡",
                        "info": "🔵",
                    }.get(issue.severity, "○")

                    line_str = f":{issue.line}" if issue.line else ""
                    output.add_output(f"{severity_icon} {issue.file}{line_str}")
                    output.add_output(f"   {issue.message}")
                    if issue.suggestion:
                        output.add_output(f"   → {issue.suggestion}")
                    output.add_output("")

                error_count = sum(1 for i in result.issues if i.severity == "error")
                warning_count = sum(1 for i in result.issues if i.severity == "warning")
                info_count = sum(1 for i in result.issues if i.severity == "info")

                chat.add_message(
                    "assistant",
                    f"Review complete: {error_count} errors, {warning_count} warnings, {info_count} suggestions"
                )
            else:
                output.add_output("✅ No issues found!")
                chat.add_message("assistant", "Review complete: No issues found!")

        except Exception as e:
            chat.add_message("system", f"Review failed: {str(e)}")
            output.add_output(f"❌ Error: {str(e)}")

        status_bar.set_status("Ready")

    def _execute_review(self, target_path: Path, files: list[str]):
        """Execute the review synchronously (called in thread)."""
        import tempfile
        from ..pro.ci import CIConfig, CIMode, CIRunner
        from ..pro.billing import BillingManager, BillingPlan

        with tempfile.TemporaryDirectory() as tmp:
            billing = BillingManager(storage_path=Path(tmp) / "billing.json")
            billing.set_plan(BillingPlan.PRO)

            config = CIConfig(
                mode=CIMode.REVIEW,
                target_path=str(target_path),
                max_files=50,
            )

            runner = CIRunner(config, billing_manager=billing)

            if files:
                runner._selected_files = [target_path / f for f in files]

            return runner.run()

    def _show_command_help(self) -> None:
        """Show available commands."""
        output = self.query_one("#output", OutputPane)
        output.add_output("")
        output.add_output("═" * 40)
        output.add_output("AVAILABLE COMMANDS")
        output.add_output("═" * 40)
        output.add_output("")
        output.add_output("/review [path] [files]")
        output.add_output("   Review code for issues")
        output.add_output("   Examples:")
        output.add_output("     /review")
        output.add_output("     /review ./src")
        output.add_output("     /review App.swift,Utils.swift")
        output.add_output("")
        output.add_output("/clear")
        output.add_output("   Clear all panes")
        output.add_output("")
        output.add_output("/help")
        output.add_output("   Show this help")
        output.add_output("")

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
