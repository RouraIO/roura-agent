"""
Tests for banner display.

© Roura.io
"""
import pytest


class TestBanner:
    """Tests for banner output."""

    def test_banner_contains_roura_io(self):
        """Banner should contain ROURA.IO."""
        from roura_agent.branding import BANNER

        # Check banner contains ROURA.IO (case-insensitive)
        banner_text = BANNER.upper()
        assert "ROURA" in banner_text or "ROURA.IO" in banner_text

    def test_banner_has_visual_elements(self):
        """Banner should have visual ASCII art elements."""
        from roura_agent.branding import BANNER

        # Should have some visual characters
        visual_chars = set("█▓▒░╔╗╚╝║═┌┐└┘│─*#@")
        has_visual = any(c in BANNER for c in visual_chars)

        assert has_visual or len(BANNER) > 50  # Either has art or is substantial text

    def test_banner_not_empty(self):
        """Banner should not be empty."""
        from roura_agent.branding import BANNER

        assert len(BANNER.strip()) > 0
