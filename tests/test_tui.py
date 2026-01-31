"""
Tests for the TUI module (keybindings only - no textual required).

© Roura.io
"""
import json
from pathlib import Path

import pytest

from roura_agent.tui.keybindings import (
    KeyBinding,
    KeyBindings,
)


class TestKeyBinding:
    """Tests for KeyBinding dataclass."""

    def test_create_binding(self):
        """Create a key binding."""
        binding = KeyBinding(key="ctrl+s", action="submit", description="Submit input")
        assert binding.key == "ctrl+s"
        assert binding.action == "submit"
        assert binding.description == "Submit input"

    def test_binding_without_description(self):
        """Create binding without description."""
        binding = KeyBinding(key="f1", action="help")
        assert binding.key == "f1"
        assert binding.action == "help"
        assert binding.description == ""


class TestKeyBindings:
    """Tests for KeyBindings collection."""

    def test_default_bindings(self):
        """Test default keybindings."""
        bindings = KeyBindings.default()
        assert len(bindings.bindings) > 0

        # Check some expected defaults
        cancel = bindings.get_action("ctrl+c")
        assert cancel == "cancel"

        exit_action = bindings.get_action("ctrl+d")
        assert exit_action == "exit"

    def test_get_binding(self):
        """Test getting a binding by key."""
        bindings = KeyBindings(bindings=[
            KeyBinding("f1", "help", "Show help"),
            KeyBinding("f2", "toggle", "Toggle something"),
        ])

        binding = bindings.get_binding("f1")
        assert binding is not None
        assert binding.action == "help"

        missing = bindings.get_binding("f999")
        assert missing is None

    def test_get_action(self):
        """Test getting action by key."""
        bindings = KeyBindings(bindings=[
            KeyBinding("ctrl+s", "save"),
        ])

        assert bindings.get_action("ctrl+s") == "save"
        assert bindings.get_action("ctrl+x") is None

    def test_set_binding(self):
        """Test setting/updating a binding."""
        bindings = KeyBindings(bindings=[])

        bindings.set_binding("f1", "help", "Show help")
        assert bindings.get_action("f1") == "help"

        # Update existing
        bindings.set_binding("f1", "info", "Show info")
        assert bindings.get_action("f1") == "info"

        # Should only have one binding for f1
        count = sum(1 for b in bindings.bindings if b.key == "f1")
        assert count == 1

    def test_remove_binding(self):
        """Test removing a binding."""
        bindings = KeyBindings(bindings=[
            KeyBinding("f1", "help"),
            KeyBinding("f2", "toggle"),
        ])

        removed = bindings.remove_binding("f1")
        assert removed is True
        assert bindings.get_action("f1") is None
        assert bindings.get_action("f2") == "toggle"

        # Remove non-existent
        removed = bindings.remove_binding("f1")
        assert removed is False

    def test_to_dict(self):
        """Test serialization to dict."""
        bindings = KeyBindings(bindings=[
            KeyBinding("f1", "help", "Show help"),
            KeyBinding("f2", "toggle"),
        ])

        data = bindings.to_dict()
        assert "bindings" in data
        assert len(data["bindings"]) == 2
        assert data["bindings"][0]["key"] == "f1"
        assert data["bindings"][0]["action"] == "help"
        assert data["bindings"][0]["description"] == "Show help"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "bindings": [
                {"key": "f1", "action": "help", "description": "Show help"},
                {"key": "f2", "action": "toggle"},
            ]
        }

        bindings = KeyBindings.from_dict(data)
        assert len(bindings.bindings) == 2
        assert bindings.get_action("f1") == "help"
        assert bindings.get_action("f2") == "toggle"

    def test_from_dict_empty(self):
        """Test deserialization from empty dict."""
        bindings = KeyBindings.from_dict({})
        assert len(bindings.bindings) == 0

    def test_save_and_load(self, tmp_path):
        """Test saving and loading bindings."""
        path = tmp_path / "keybindings.json"

        original = KeyBindings(bindings=[
            KeyBinding("f1", "help", "Show help"),
            KeyBinding("ctrl+s", "save"),
        ])

        original.save(path)
        assert path.exists()

        # Verify file content
        data = json.loads(path.read_text())
        assert len(data["bindings"]) == 2

        # Load and compare
        loaded = KeyBindings.load(path)
        assert len(loaded.bindings) == 2
        assert loaded.get_action("f1") == "help"
        assert loaded.get_action("ctrl+s") == "save"

    def test_load_missing_file(self, tmp_path):
        """Test loading from non-existent file returns defaults."""
        path = tmp_path / "nonexistent.json"
        bindings = KeyBindings.load(path)

        # Should return defaults
        defaults = KeyBindings.default()
        assert len(bindings.bindings) == len(defaults.bindings)

    def test_load_invalid_json(self, tmp_path):
        """Test loading from invalid JSON returns defaults."""
        path = tmp_path / "invalid.json"
        path.write_text("not valid json {{{")

        bindings = KeyBindings.load(path)

        # Should return defaults
        defaults = KeyBindings.default()
        assert len(bindings.bindings) == len(defaults.bindings)


class TestDefaultBindings:
    """Test the default keybinding set."""

    def test_has_cancel(self):
        """Default bindings include cancel."""
        bindings = KeyBindings.default()
        assert bindings.get_action("ctrl+c") == "cancel"

    def test_has_exit(self):
        """Default bindings include exit."""
        bindings = KeyBindings.default()
        assert bindings.get_action("ctrl+d") == "exit"

    def test_has_help(self):
        """Default bindings include help."""
        bindings = KeyBindings.default()
        assert bindings.get_action("f1") == "help"

    def test_has_undo(self):
        """Default bindings include undo."""
        bindings = KeyBindings.default()
        assert bindings.get_action("ctrl+z") == "undo"

    def test_has_diff_navigation(self):
        """Default bindings include diff navigation."""
        bindings = KeyBindings.default()
        assert bindings.get_action("n") == "next_hunk"
        assert bindings.get_action("y") == "approve_hunk"

    def test_has_pane_toggles(self):
        """Default bindings include pane toggles."""
        bindings = KeyBindings.default()
        assert bindings.get_action("f2") == "toggle_diff"
        assert bindings.get_action("f3") == "toggle_output"
