"""
Roura Agent TUI Keybindings - Configurable keyboard shortcuts.

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class KeyBinding:
    """A single key binding."""
    key: str  # e.g., "ctrl+s", "f5", "escape"
    action: str  # e.g., "submit", "cancel", "toggle_pane"
    description: str = ""


@dataclass
class KeyBindings:
    """
    Collection of keybindings for the TUI.

    Default bindings:
    - Ctrl+C: Cancel current operation
    - Ctrl+D: Exit
    - Escape: Cancel/dismiss
    - Ctrl+L: Clear screen
    - Ctrl+S: Submit input (in chat)
    - F1: Help
    - F2: Toggle diff pane
    - F3: Toggle output pane
    - Ctrl+Z: Undo
    - Ctrl+/: Toggle focus between panes
    """

    bindings: list[KeyBinding] = field(default_factory=list)

    @classmethod
    def default(cls) -> 'KeyBindings':
        """Create default keybindings."""
        return cls(bindings=[
            # Core controls
            KeyBinding("ctrl+c", "cancel", "Cancel current operation"),
            KeyBinding("ctrl+d", "exit", "Exit application"),
            KeyBinding("escape", "dismiss", "Dismiss dialog/cancel"),
            KeyBinding("ctrl+l", "clear", "Clear screen"),

            # Input controls
            KeyBinding("ctrl+s", "submit", "Submit input"),
            KeyBinding("enter", "send", "Send message"),

            # Navigation
            KeyBinding("ctrl+slash", "toggle_focus", "Toggle focus between panes"),
            KeyBinding("tab", "next_pane", "Move to next pane"),
            KeyBinding("shift+tab", "prev_pane", "Move to previous pane"),

            # Pane controls
            KeyBinding("f2", "toggle_diff", "Toggle diff pane"),
            KeyBinding("f3", "toggle_output", "Toggle output pane"),
            KeyBinding("f4", "toggle_files", "Toggle file tree"),

            # Actions
            KeyBinding("ctrl+z", "undo", "Undo last change"),
            KeyBinding("ctrl+y", "redo", "Redo last change"),
            KeyBinding("f1", "help", "Show help"),
            KeyBinding("f5", "refresh", "Refresh view"),

            # Diff navigation
            KeyBinding("n", "next_hunk", "Next diff hunk"),
            KeyBinding("shift+n", "prev_hunk", "Previous diff hunk"),
            KeyBinding("y", "approve_hunk", "Approve current hunk"),
            KeyBinding("r", "reject_hunk", "Reject current hunk"),
            KeyBinding("a", "approve_all", "Approve all hunks"),
        ])

    def get_binding(self, key: str) -> Optional[KeyBinding]:
        """Get binding for a key."""
        for binding in self.bindings:
            if binding.key == key:
                return binding
        return None

    def get_action(self, key: str) -> Optional[str]:
        """Get action for a key."""
        binding = self.get_binding(key)
        return binding.action if binding else None

    def set_binding(self, key: str, action: str, description: str = "") -> None:
        """Set or update a binding."""
        # Remove existing binding for this key
        self.bindings = [b for b in self.bindings if b.key != key]
        self.bindings.append(KeyBinding(key, action, description))

    def remove_binding(self, key: str) -> bool:
        """Remove a binding. Returns True if removed."""
        original_len = len(self.bindings)
        self.bindings = [b for b in self.bindings if b.key != key]
        return len(self.bindings) < original_len

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "bindings": [
                {
                    "key": b.key,
                    "action": b.action,
                    "description": b.description,
                }
                for b in self.bindings
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'KeyBindings':
        """Create from dictionary."""
        bindings = []
        for b in data.get("bindings", []):
            bindings.append(KeyBinding(
                key=b["key"],
                action=b["action"],
                description=b.get("description", ""),
            ))
        return cls(bindings=bindings)

    def save(self, path: Path) -> None:
        """Save bindings to file."""
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> 'KeyBindings':
        """Load bindings from file."""
        if not path.exists():
            return cls.default()
        try:
            data = json.loads(path.read_text())
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return cls.default()


def get_keybindings_path() -> Path:
    """Get the path to the keybindings configuration file."""
    config_dir = Path.home() / ".config" / "roura-agent"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "keybindings.json"


def load_keybindings() -> KeyBindings:
    """Load keybindings from config file or return defaults."""
    return KeyBindings.load(get_keybindings_path())


def save_keybindings(bindings: KeyBindings) -> None:
    """Save keybindings to config file."""
    bindings.save(get_keybindings_path())
