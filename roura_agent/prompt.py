"""
Roura Agent Prompt - Interactive input with tab completion.

© Roura.io
"""
from __future__ import annotations

from typing import Optional, Callable
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from pathlib import Path


# Slash commands with descriptions
COMMANDS = {
    "/help": "Show help and available commands",
    "/status": "Show session info (version, model, project)",
    "/version": "Show version number",
    "/model": "Switch LLM provider (ollama, openai, anthropic)",
    "/upgrade": "Check for and install updates",
    "/restart": "Restart CLI (preserves session)",
    "/context": "Show loaded file context",
    "/undo": "Undo last file change",
    "/clear": "Clear conversation and start fresh",
    "/tools": "List available tools",
    "/agents": "List specialized agents",
    "/history": "Show session history",
    "/resume": "Resume a previous session",
    "/export": "Export current session",
    "/walkthrough": "Interactive tutorial",
    "/license": "View or enter license key",
    "/pricing": "View pricing and upgrade to PRO",
    "exit": "Quit roura-agent",
}

# Model/provider options for /model command
MODEL_OPTIONS = ["ollama", "openai", "anthropic", "claude", "gpt"]


class RouraCompleter(Completer):
    """Custom completer for Roura Agent commands."""

    def __init__(self):
        self.commands = COMMANDS
        self.model_options = MODEL_OPTIONS

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        word = document.get_word_before_cursor()

        # If line starts with /, complete commands
        if text.startswith("/"):
            # Check if we're completing the command itself or an argument
            parts = text.split()

            if len(parts) == 1 and not text.endswith(" "):
                # Completing the command name
                for cmd, desc in self.commands.items():
                    if cmd.startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=desc,
                        )
            elif len(parts) >= 1:
                # Completing command arguments
                cmd = parts[0]

                if cmd == "/model":
                    # Complete model/provider names
                    prefix = parts[1] if len(parts) > 1 and not text.endswith(" ") else ""
                    for opt in self.model_options:
                        if opt.startswith(prefix.lower()):
                            yield Completion(
                                opt,
                                start_position=-len(prefix) if prefix else 0,
                                display=opt,
                            )

                elif cmd == "/export":
                    # Complete export formats
                    prefix = parts[1] if len(parts) > 1 and not text.endswith(" ") else ""
                    for fmt in ["markdown", "json"]:
                        if fmt.startswith(prefix.lower()):
                            yield Completion(
                                fmt,
                                start_position=-len(prefix) if prefix else 0,
                                display=fmt,
                            )

        # Also complete "exit" and "quit"
        elif text and not text.startswith("/"):
            for cmd in ["exit", "quit"]:
                if cmd.startswith(text.lower()):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta="Quit roura-agent",
                    )


# Style for the prompt
PROMPT_STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
    "completion-menu": "bg:ansibrightblack ansiwhite",
    "completion-menu.completion": "bg:ansibrightblack ansiwhite",
    "completion-menu.completion.current": "bg:ansicyan ansiblack",
    "completion-menu.meta": "bg:ansibrightblack ansigray",
    "completion-menu.meta.current": "bg:ansicyan ansiblack",
})


class RouraPrompt:
    """Interactive prompt with history and tab completion."""

    def __init__(self, history_file: Optional[Path] = None):
        # Setup history file
        if history_file is None:
            history_dir = Path.home() / ".config" / "roura-agent"
            history_dir.mkdir(parents=True, exist_ok=True)
            history_file = history_dir / "history"

        self.session = PromptSession(
            completer=RouraCompleter(),
            history=FileHistory(str(history_file)),
            style=PROMPT_STYLE,
            complete_while_typing=False,  # Only complete on Tab
            enable_history_search=True,   # Ctrl+R to search history
        )

    def prompt(self, message: str = "> ") -> str:
        """
        Get input from user with tab completion.

        Args:
            message: The prompt message to display

        Returns:
            User input string

        Raises:
            EOFError: On Ctrl+D
            KeyboardInterrupt: On Ctrl+C
        """
        return self.session.prompt(HTML(f"<prompt>{message}</prompt>"))


# Global instance for reuse
_prompt_instance: Optional[RouraPrompt] = None


def get_prompt() -> RouraPrompt:
    """Get or create the global prompt instance."""
    global _prompt_instance
    if _prompt_instance is None:
        _prompt_instance = RouraPrompt()
    return _prompt_instance


def prompt_input(message: str = "> ") -> str:
    """
    Convenience function to get input with completion.

    Falls back to regular input() if prompt_toolkit fails.
    """
    try:
        return get_prompt().prompt(message)
    except Exception:
        # Fallback to basic input
        return input(message)
