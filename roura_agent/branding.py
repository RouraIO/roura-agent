"""
Roura Agent Branding - Centralized branding constants and styling.

This module provides consistent branding across the entire application:
- ASCII logo
- Color palette
- Text styles
- Panel formatting

Usage:
    from roura_agent.branding import LOGO, Colors, Styles
    console.print(LOGO)
    console.print(f"[{Colors.PRIMARY}]Text[/{Colors.PRIMARY}]")

"""
from __future__ import annotations

# ASCII Art Logo - Main brand identifier
LOGO = """
[cyan]
 ██████╗  ██████╗ ██╗   ██╗██████╗  █████╗
 ██╔══██╗██╔═══██╗██║   ██║██╔══██╗██╔══██╗
 ██████╔╝██║   ██║██║   ██║██████╔╝███████║
 ██╔══██╗██║   ██║██║   ██║██╔══██╗██╔══██║
 ██║  ██║╚██████╔╝╚██████╔╝██║  ██║██║  ██║
 ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
[/cyan]"""

# Import version from constants (single source of truth)
from .constants import VERSION as _VERSION


# Dynamic logo - use function to get at runtime
def get_logo() -> str:
    """Get the ASCII logo."""
    return """
[cyan]
 ██████╗  ██████╗ ██╗   ██╗██████╗  █████╗
 ██╔══██╗██╔═══██╗██║   ██║██╔══██╗██╔══██╗
 ██████╔╝██║   ██║██║   ██║██████╔╝███████║
 ██╔══██╗██║   ██║██║   ██║██╔══██╗██╔══██║
 ██║  ██║╚██████╔╝╚██████╔╝██║  ██║██║  ██║
 ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
[/cyan]"""

# Compact logo for tight spaces
LOGO_COMPACT = "[cyan bold]◆ ROURA[/cyan bold] [dim]• roura.io[/dim]"

# Single-line brand text
BRAND_NAME = "Roura Agent"
BRAND_TAGLINE = "Local AI Coding Assistant"
BRAND_COMPANY = "Roura.io"
BRAND_URL = "https://roura.io"

# BRAND_VERSION imported above as _VERSION for logo
BRAND_VERSION = _VERSION


class Colors:
    """Roura Agent color palette.

    These colors are designed to work well on both light and dark terminals.
    Use Rich markup syntax: [color]text[/color]
    """
    # Primary brand colors
    PRIMARY: str = "cyan"
    PRIMARY_BOLD: str = "bold cyan"
    SECONDARY: str = "blue"
    ACCENT: str = "magenta"

    # Semantic colors
    SUCCESS: str = "green"
    WARNING: str = "yellow"
    ERROR: str = "red"
    INFO: str = "blue"

    # Risk level colors (for tool risk classification)
    RISK_SAFE: str = "green"
    RISK_MODERATE: str = "yellow"
    RISK_DANGEROUS: str = "red"

    # UI element colors
    PROMPT: str = "bold cyan"
    DIM: str = "dim"
    MUTED: str = "dim white"
    HIGHLIGHT: str = "bold white"

    # Diff colors
    DIFF_ADD: str = "green"
    DIFF_REMOVE: str = "red"
    DIFF_CONTEXT: str = "dim"
    DIFF_HEADER: str = "bold"
    DIFF_HUNK: str = "cyan"

    # Panel borders
    BORDER_PRIMARY: str = "cyan"
    BORDER_WARNING: str = "yellow"
    BORDER_ERROR: str = "red"
    BORDER_SUCCESS: str = "green"
    BORDER_INFO: str = "blue"


class Icons:
    """Unicode icons for consistent visual language."""
    # Status icons
    SUCCESS: str = "\u2713"
    ERROR: str = "\u2717"
    WARNING: str = "\u26a0"
    INFO: str = "\u2139"

    # Tool icons
    TOOL_RUN: str = "\u25b6"
    TOOL_DONE: str = "\u2713"
    TOOL_FAIL: str = "\u2717"
    TOOL_SKIP: str = "\u2298"

    # Navigation
    ARROW_RIGHT: str = "\u2192"
    ARROW_LEFT: str = "\u2190"
    ARROW_UP: str = "\u2191"
    ARROW_DOWN: str = "\u2193"

    # Misc
    ROCKET: str = "\U0001f680"
    GEAR: str = "\u2699"
    FOLDER: str = "\U0001f4c1"
    FILE: str = "\U0001f4c4"
    LIGHTNING: str = "\u26a1"
    THINKING: str = "\U0001f4ad"
    LOCK: str = "\U0001f512"
    KEY: str = "\U0001f511"
    CLOCK: str = "\u23f1"
    FORBIDDEN: str = "\U0001f6ab"
    EYE: str = "\U0001f441"

    # Cursor
    CURSOR_BLOCK: str = "\u2588"
    CURSOR_LINE: str = "\u2502"

    # Approval
    APPROVE: str = "\U0001f44d"
    REJECT: str = "\U0001f44e"


class Styles:
    """Pre-composed style strings for common UI patterns."""
    # Headers
    HEADER: str = "bold"
    SUBHEADER: str = "bold dim"

    # Prompts
    USER_PROMPT: str = "bold cyan"
    ASSISTANT: str = "white"

    # Tool display
    TOOL_NAME: str = "bold"
    TOOL_ARG: str = "dim"
    TOOL_RESULT_SUCCESS: str = "green"
    TOOL_RESULT_ERROR: str = "red"

    # Panel titles
    PANEL_TITLE: str = "bold"
    PANEL_TITLE_ERROR: str = "bold red"
    PANEL_TITLE_WARNING: str = "bold yellow"
    PANEL_TITLE_SUCCESS: str = "bold green"


def format_status_line(model: str, tools_mode: str) -> str:
    """Format the status line shown below the logo."""
    return f"[{Colors.DIM}]Model: {model} | {tools_mode}[/{Colors.DIM}]"


def format_project_line(name: str, type_: str, branch: str | None = None) -> str:
    """Format the project info line."""
    line = f"[{Colors.PRIMARY_BOLD}]Project:[/{Colors.PRIMARY_BOLD}] {name} [{Colors.DIM}]({type_})[/{Colors.DIM}]"
    if branch:
        line += f" [{Colors.DIM}]• {branch}[/{Colors.DIM}]"
    return line


def format_tool_call(name: str, args_preview: str = "") -> str:
    """Format a tool call display."""
    if args_preview:
        return f"[{Colors.PRIMARY}]{Icons.TOOL_RUN}[/{Colors.PRIMARY}] [{Styles.TOOL_NAME}]{name}[/{Styles.TOOL_NAME}] [{Styles.TOOL_ARG}]{args_preview}[/{Styles.TOOL_ARG}]"
    return f"[{Colors.PRIMARY}]{Icons.TOOL_RUN}[/{Colors.PRIMARY}] [{Styles.TOOL_NAME}]{name}[/{Styles.TOOL_NAME}]"


def format_tool_result(success: bool, message: str = "") -> str:
    """Format a tool result display."""
    if success:
        icon = Icons.SUCCESS
        color = Colors.SUCCESS
    else:
        icon = Icons.ERROR
        color = Colors.ERROR

    if message:
        return f"  [{color}]{icon}[/{color}] [{Colors.DIM}]{message}[/{Colors.DIM}]"
    return f"  [{color}]{icon}[/{color}]"


def format_error(message: str, hint: str | None = None) -> str:
    """Format an error message with optional recovery hint."""
    error = f"[{Colors.ERROR}]Error:[/{Colors.ERROR}] {message}"
    if hint:
        error += f"\n[{Colors.DIM}]Hint: {hint}[/{Colors.DIM}]"
    return error


def format_warning(message: str) -> str:
    """Format a warning message."""
    return f"[{Colors.WARNING}]{Icons.WARNING}[/{Colors.WARNING}] {message}"


def format_success(message: str) -> str:
    """Format a success message."""
    return f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] {message}"


def format_info(message: str) -> str:
    """Format an info message."""
    return f"[{Colors.INFO}]{Icons.INFO}[/{Colors.INFO}] {message}"


def format_diff_line(line: str) -> str:
    """Format a single diff line with appropriate color."""
    if line.startswith("+") and not line.startswith("+++"):
        return f"[{Colors.DIFF_ADD}]{line}[/{Colors.DIFF_ADD}]"
    elif line.startswith("-") and not line.startswith("---"):
        return f"[{Colors.DIFF_REMOVE}]{line}[/{Colors.DIFF_REMOVE}]"
    elif line.startswith("@@"):
        return f"[{Colors.DIFF_HUNK}]{line}[/{Colors.DIFF_HUNK}]"
    elif line.startswith("diff ") or line.startswith("index "):
        return f"[{Colors.DIFF_HEADER}]{line}[/{Colors.DIFF_HEADER}]"
    return line


def format_diff(diff_text: str) -> str:
    """Format a full diff with colors."""
    return "\n".join(format_diff_line(line) for line in diff_text.splitlines())


def get_risk_color(risk_level: str) -> str:
    """Get the color for a risk level."""
    risk_map = {
        "safe": Colors.RISK_SAFE,
        "moderate": Colors.RISK_MODERATE,
        "dangerous": Colors.RISK_DANGEROUS,
    }
    return risk_map.get(risk_level.lower(), Colors.DIM)


# Keyboard shortcuts reference
KEYBOARD_SHORTCUTS = """
[bold]Keyboard Shortcuts[/bold]

[cyan]ESC[/cyan]       Interrupt current operation
[cyan]Ctrl+C[/cyan]    Cancel input / Exit
[cyan]Ctrl+D[/cyan]    Exit (EOF)
[cyan]Enter[/cyan]     Submit input
[cyan]Tab[/cyan]       Auto-complete (where supported)

[bold]Commands[/bold]

[cyan]/help[/cyan]     Show help
[cyan]/context[/cyan]  Show loaded file context
[cyan]/clear[/cyan]    Clear conversation
[cyan]/tools[/cyan]    List available tools
[cyan]/keys[/cyan]     Show this shortcuts panel
[cyan]exit[/cyan]      Quit the agent
"""


# Version info
def get_version_string() -> str:
    """Get formatted version string."""
    return f"{BRAND_NAME} v{BRAND_VERSION}"


def get_about() -> str:
    """Get about text for display."""
    return f"""
[{Colors.PRIMARY_BOLD}]{BRAND_NAME}[/{Colors.PRIMARY_BOLD}] v{BRAND_VERSION}
{BRAND_TAGLINE}

{BRAND_URL}

Local-first AI coding assistant that runs entirely on your machine.
Uses Ollama for LLM inference with native tool calling support.
"""
