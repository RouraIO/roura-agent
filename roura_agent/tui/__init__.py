"""
Roura Agent TUI - Textual-based terminal user interface.

The TUI provides a rich, interactive interface with:
- Split panes for code and output
- Diff viewer with syntax highlighting
- Keyboard shortcuts for common operations
- Real-time streaming display

Requires: pip install roura-agent[tui]

© Roura.io
"""
from __future__ import annotations

# Check if textual is available
try:
    import textual  # noqa: F401
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

if TEXTUAL_AVAILABLE:
    from .app import RouraApp
    from .keybindings import KeyBindings, load_keybindings

    __all__ = [
        "RouraApp",
        "KeyBindings",
        "load_keybindings",
        "TEXTUAL_AVAILABLE",
    ]
else:
    __all__ = ["TEXTUAL_AVAILABLE"]


def check_tui_available() -> bool:
    """Check if TUI dependencies are available."""
    return TEXTUAL_AVAILABLE


def launch_tui():
    """
    Launch the TUI application.

    Raises:
        ImportError: If textual is not installed
    """
    if not TEXTUAL_AVAILABLE:
        raise ImportError(
            "TUI requires textual. Install with: pip install roura-agent[tui]"
        )

    from .app import RouraApp
    app = RouraApp()
    app.run()
