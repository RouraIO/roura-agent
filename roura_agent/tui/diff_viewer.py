"""
Roura Agent TUI Diff Viewer - Interactive diff display widget.

Features:
- Syntax-highlighted diff display
- Per-hunk navigation
- Approve/reject individual hunks
- Unified and split view modes

© Roura.io
"""
from __future__ import annotations

from typing import Optional

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, ScrollableContainer
    from textual.message import Message
    from textual.widget import Widget
    from textual.widgets import Label, Static
except ImportError:
    raise ImportError(
        "TUI requires textual. Install with: pip install roura-agent[tui]"
    )

from ..patch import DiffLine, Hunk, HunkStatus, Patch


class HunkWidget(Static):
    """Widget for displaying a single diff hunk."""

    class Approved(Message):
        """Hunk was approved."""
        def __init__(self, hunk_index: int) -> None:
            super().__init__()
            self.hunk_index = hunk_index

    class Rejected(Message):
        """Hunk was rejected."""
        def __init__(self, hunk_index: int) -> None:
            super().__init__()
            self.hunk_index = hunk_index

    BINDINGS = [
        Binding("y", "approve", "Approve"),
        Binding("n", "reject", "Reject"),
    ]

    def __init__(self, hunk: Hunk, index: int, **kwargs):
        super().__init__(**kwargs)
        self.hunk = hunk
        self.index = index
        self._render()

    def _render(self) -> None:
        """Render the hunk."""
        lines = []

        # Header
        status_color = {
            HunkStatus.PENDING: "yellow",
            HunkStatus.APPROVED: "green",
            HunkStatus.REJECTED: "red",
            HunkStatus.SKIPPED: "dim",
        }[self.hunk.status]

        header = self.hunk.format_header()
        lines.append(f"[bold {status_color}]{header}[/]")
        lines.append("")

        # Diff lines
        for diff_line in self.hunk.lines:
            if diff_line.type == "+":
                lines.append(f"[green]+{diff_line.content}[/green]")
            elif diff_line.type == "-":
                lines.append(f"[red]-{diff_line.content}[/red]")
            elif diff_line.type == " ":
                lines.append(f"[dim] {diff_line.content}[/dim]")
            else:
                lines.append(f"[yellow]\\{diff_line.content}[/yellow]")

        self.update("\n".join(lines))

    def action_approve(self) -> None:
        """Approve this hunk."""
        self.hunk.status = HunkStatus.APPROVED
        self._render()
        self.post_message(self.Approved(self.index))

    def action_reject(self) -> None:
        """Reject this hunk."""
        self.hunk.status = HunkStatus.REJECTED
        self._render()
        self.post_message(self.Rejected(self.index))


class DiffViewer(Widget):
    """
    Interactive diff viewer widget.

    Displays a patch with multiple hunks and allows navigation
    and per-hunk approval.
    """

    class AllApproved(Message):
        """All hunks were approved."""
        pass

    class AllRejected(Message):
        """All hunks were rejected."""
        pass

    BINDINGS = [
        Binding("j", "next_hunk", "Next Hunk"),
        Binding("k", "prev_hunk", "Previous Hunk"),
        Binding("a", "approve_all", "Approve All"),
        Binding("x", "reject_all", "Reject All"),
        Binding("enter", "confirm", "Confirm"),
    ]

    DEFAULT_CSS = """
    DiffViewer {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }

    DiffViewer .hunk {
        margin-bottom: 1;
        padding: 1;
        border: solid $secondary;
    }

    DiffViewer .hunk-focused {
        border: double $accent;
    }

    DiffViewer .file-header {
        text-style: bold;
        margin-bottom: 1;
    }

    DiffViewer .summary {
        dock: bottom;
        height: 2;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    def __init__(self, patch: Optional[Patch] = None, **kwargs):
        super().__init__(**kwargs)
        self.patch = patch
        self.current_hunk: int = 0
        self.hunk_widgets: list[HunkWidget] = []

    def compose(self) -> ComposeResult:
        """Create the widget layout."""
        if not self.patch:
            yield Label("[dim]No diff to display[/dim]")
            return

        # File header
        yield Label(
            f"[bold]{self.patch.new_file}[/bold] "
            f"[green]+{self.patch.total_added}[/green] "
            f"[red]-{self.patch.total_removed}[/red]",
            classes="file-header",
        )

        # Hunks container
        with ScrollableContainer():
            for i, hunk in enumerate(self.patch.hunks):
                widget = HunkWidget(hunk, i, classes="hunk")
                self.hunk_widgets.append(widget)
                yield widget

        # Summary
        yield self._make_summary()

    def _make_summary(self) -> Label:
        """Create the summary label."""
        if not self.patch:
            return Label("")

        approved = len(self.patch.approved_hunks)
        pending = len(self.patch.pending_hunks)
        total = len(self.patch.hunks)

        return Label(
            f"Hunks: {approved} approved, {pending} pending, {total} total | "
            f"[dim]j/k=navigate, y/n=approve/reject, a=approve all[/dim]",
            classes="summary",
        )

    def set_patch(self, patch: Patch) -> None:
        """Set a new patch to display."""
        self.patch = patch
        self.current_hunk = 0
        self.hunk_widgets.clear()
        self.refresh()

    def action_next_hunk(self) -> None:
        """Navigate to next hunk."""
        if not self.patch or not self.hunk_widgets:
            return

        if self.current_hunk < len(self.hunk_widgets) - 1:
            self.current_hunk += 1
            self._update_focus()

    def action_prev_hunk(self) -> None:
        """Navigate to previous hunk."""
        if not self.patch or not self.hunk_widgets:
            return

        if self.current_hunk > 0:
            self.current_hunk -= 1
            self._update_focus()

    def action_approve_all(self) -> None:
        """Approve all pending hunks."""
        if self.patch:
            self.patch.approve_all()
            for widget in self.hunk_widgets:
                widget._render()
            self.post_message(self.AllApproved())

    def action_reject_all(self) -> None:
        """Reject all pending hunks."""
        if self.patch:
            self.patch.reject_all()
            for widget in self.hunk_widgets:
                widget._render()
            self.post_message(self.AllRejected())

    def action_confirm(self) -> None:
        """Confirm current selections."""
        if not self.patch:
            return

        if self.patch.pending_hunks:
            # Still have pending hunks
            pass
        else:
            # All decided
            pass

    def _update_focus(self) -> None:
        """Update visual focus indicator."""
        for i, widget in enumerate(self.hunk_widgets):
            if i == self.current_hunk:
                widget.add_class("hunk-focused")
            else:
                widget.remove_class("hunk-focused")

    def on_hunk_widget_approved(self, event: HunkWidget.Approved) -> None:
        """Handle hunk approval."""
        # Auto-advance to next hunk
        if self.current_hunk < len(self.hunk_widgets) - 1:
            self.action_next_hunk()

    def on_hunk_widget_rejected(self, event: HunkWidget.Rejected) -> None:
        """Handle hunk rejection."""
        # Auto-advance to next hunk
        if self.current_hunk < len(self.hunk_widgets) - 1:
            self.action_next_hunk()
