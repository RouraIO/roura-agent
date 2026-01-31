"""
Roura Agent Patch - Diff-first editing with per-hunk approval.

Features:
- Parse unified diffs into hunks
- Per-hunk approval for granular control
- Apply patches partially (selected hunks only)
- Preview mode for dry-run
- Rollback support via undo stack

© Roura.io
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import unified_diff
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.text import Text


class HunkStatus(Enum):
    """Status of a hunk in the approval workflow."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass
class DiffLine:
    """A single line in a diff."""
    type: str  # "+", "-", " ", "\\"
    content: str
    old_line_num: Optional[int] = None
    new_line_num: Optional[int] = None


@dataclass
class Hunk:
    """
    A contiguous block of changes in a diff.

    Hunks are the atomic units of approval in per-hunk mode.
    """
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)
    header: str = ""
    status: HunkStatus = HunkStatus.PENDING
    context: str = ""  # Function/class context if available

    @property
    def added_lines(self) -> int:
        """Count of lines added by this hunk."""
        return sum(1 for line in self.lines if line.type == "+")

    @property
    def removed_lines(self) -> int:
        """Count of lines removed by this hunk."""
        return sum(1 for line in self.lines if line.type == "-")

    @property
    def changes(self) -> int:
        """Total line changes (added + removed)."""
        return self.added_lines + self.removed_lines

    def format_header(self) -> str:
        """Format the hunk header for display."""
        header = f"@@ -{self.old_start},{self.old_count} +{self.new_start},{self.new_count} @@"
        if self.context:
            header += f" {self.context}"
        return header

    def get_old_content(self) -> str:
        """Get the original content (lines to be removed/kept)."""
        lines = []
        for line in self.lines:
            if line.type in (" ", "-"):
                lines.append(line.content)
        return "\n".join(lines)

    def get_new_content(self) -> str:
        """Get the new content (lines to be added/kept)."""
        lines = []
        for line in self.lines:
            if line.type in (" ", "+"):
                lines.append(line.content)
        return "\n".join(lines)


@dataclass
class Patch:
    """
    A complete diff/patch for one or more files.
    """
    old_file: str
    new_file: str
    hunks: list[Hunk] = field(default_factory=list)
    file_mode: Optional[str] = None  # "create", "delete", "modify"

    @property
    def total_added(self) -> int:
        """Total lines added across all hunks."""
        return sum(h.added_lines for h in self.hunks)

    @property
    def total_removed(self) -> int:
        """Total lines removed across all hunks."""
        return sum(h.removed_lines for h in self.hunks)

    @property
    def approved_hunks(self) -> list[Hunk]:
        """Get hunks that have been approved."""
        return [h for h in self.hunks if h.status == HunkStatus.APPROVED]

    @property
    def pending_hunks(self) -> list[Hunk]:
        """Get hunks that are still pending."""
        return [h for h in self.hunks if h.status == HunkStatus.PENDING]

    def approve_all(self) -> None:
        """Approve all pending hunks."""
        for hunk in self.hunks:
            if hunk.status == HunkStatus.PENDING:
                hunk.status = HunkStatus.APPROVED

    def reject_all(self) -> None:
        """Reject all pending hunks."""
        for hunk in self.hunks:
            if hunk.status == HunkStatus.PENDING:
                hunk.status = HunkStatus.REJECTED


def parse_unified_diff(diff_text: str) -> list[Patch]:
    """
    Parse a unified diff into Patch objects with Hunks.

    Args:
        diff_text: The unified diff as a string

    Returns:
        List of Patch objects
    """
    patches = []
    current_patch: Optional[Patch] = None
    current_hunk: Optional[Hunk] = None

    lines = diff_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # File header: --- a/file
        if line.startswith("--- "):
            if current_patch and current_hunk:
                current_patch.hunks.append(current_hunk)
                current_hunk = None
            if current_patch:
                patches.append(current_patch)

            old_file = line[4:].strip()
            if old_file.startswith("a/"):
                old_file = old_file[2:]

            # Next line should be +++ b/file
            i += 1
            if i < len(lines) and lines[i].startswith("+++ "):
                new_file = lines[i][4:].strip()
                if new_file.startswith("b/"):
                    new_file = new_file[2:]
            else:
                new_file = old_file

            current_patch = Patch(old_file=old_file, new_file=new_file)
            i += 1
            continue

        # Hunk header: @@ -1,5 +1,6 @@
        hunk_match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)?", line)
        if hunk_match and current_patch is not None:
            if current_hunk:
                current_patch.hunks.append(current_hunk)

            current_hunk = Hunk(
                old_start=int(hunk_match.group(1)),
                old_count=int(hunk_match.group(2) or 1),
                new_start=int(hunk_match.group(3)),
                new_count=int(hunk_match.group(4) or 1),
                header=line,
                context=(hunk_match.group(5) or "").strip(),
            )
            i += 1
            continue

        # Diff content lines
        if current_hunk is not None and line:
            line_type = line[0] if line else " "
            content = line[1:] if len(line) > 1 else ""

            if line_type in ("+", "-", " ", "\\"):
                current_hunk.lines.append(DiffLine(
                    type=line_type,
                    content=content,
                ))

        i += 1

    # Add final hunk and patch
    if current_patch:
        if current_hunk:
            current_patch.hunks.append(current_hunk)
        patches.append(current_patch)

    return patches


def generate_unified_diff(
    old_content: str,
    new_content: str,
    old_file: str = "a/file",
    new_file: str = "b/file",
    context_lines: int = 3,
) -> str:
    """
    Generate a unified diff between two strings.

    Args:
        old_content: Original content
        new_content: New content
        old_file: Name for the old file in diff header
        new_file: Name for the new file in diff header
        context_lines: Number of context lines around changes

    Returns:
        Unified diff as a string
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Ensure both have trailing newlines for cleaner diffs
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    diff = unified_diff(
        old_lines,
        new_lines,
        fromfile=old_file,
        tofile=new_file,
        n=context_lines,
    )

    return "".join(diff)


class DiffRenderer:
    """
    Render diffs with Rich for terminal display.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def render_hunk(
        self,
        hunk: Hunk,
        file_path: str = "",
        show_line_numbers: bool = True,
    ) -> Panel:
        """Render a single hunk as a Rich Panel."""
        lines = []

        # Header
        header_text = Text()
        header_text.append(hunk.format_header(), style="bold cyan")
        lines.append(header_text)
        lines.append(Text())

        # Diff lines
        old_num = hunk.old_start
        new_num = hunk.new_start

        for diff_line in hunk.lines:
            line = Text()

            # Line numbers
            if show_line_numbers:
                if diff_line.type == "-":
                    line.append(f"{old_num:4d}      ", style="dim")
                    old_num += 1
                elif diff_line.type == "+":
                    line.append(f"     {new_num:4d} ", style="dim")
                    new_num += 1
                elif diff_line.type == " ":
                    line.append(f"{old_num:4d} {new_num:4d} ", style="dim")
                    old_num += 1
                    new_num += 1
                else:
                    line.append("          ", style="dim")

            # Type indicator and content
            if diff_line.type == "-":
                line.append("-", style="bold red")
                line.append(diff_line.content, style="red")
            elif diff_line.type == "+":
                line.append("+", style="bold green")
                line.append(diff_line.content, style="green")
            elif diff_line.type == " ":
                line.append(" ", style="dim")
                line.append(diff_line.content, style="dim")
            else:
                line.append("\\" + diff_line.content, style="yellow italic")

            lines.append(line)

        # Status badge
        status_styles = {
            HunkStatus.PENDING: ("dim", "pending"),
            HunkStatus.APPROVED: ("green", "approved"),
            HunkStatus.REJECTED: ("red", "rejected"),
            HunkStatus.SKIPPED: ("yellow", "skipped"),
        }
        style, label = status_styles[hunk.status]

        title = f"Hunk: {hunk.changes} changes"
        if file_path:
            title = f"{Path(file_path).name}: {title}"

        return Panel(
            Group(*lines),
            title=title,
            subtitle=f"[{style}]{label}[/{style}]",
            border_style=style if hunk.status != HunkStatus.PENDING else "cyan",
        )

    def render_patch(
        self,
        patch: Patch,
        show_line_numbers: bool = True,
    ) -> Panel:
        """Render a complete patch as a Rich Panel."""
        content = []

        # Summary
        summary = Text()
        summary.append(f"{patch.new_file}", style="bold")
        summary.append(f" (+{patch.total_added}/-{patch.total_removed})", style="dim")
        content.append(summary)
        content.append(Text())

        # Hunks
        for i, hunk in enumerate(patch.hunks, 1):
            content.append(Text(f"Hunk {i}/{len(patch.hunks)}", style="bold dim"))
            content.append(self.render_hunk(hunk, patch.new_file, show_line_numbers))

        return Panel(
            Group(*content),
            title=f"[bold]{patch.new_file}[/bold]",
            border_style="blue",
        )


class PatchApprovalSession:
    """
    Interactive session for per-hunk patch approval.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.renderer = DiffRenderer(console)

    def approve_patch(
        self,
        patch: Patch,
        per_hunk: bool = True,
    ) -> bool:
        """
        Run interactive approval for a patch.

        Args:
            patch: The patch to approve
            per_hunk: If True, ask for each hunk. If False, approve/reject entire patch.

        Returns:
            True if any hunks were approved, False if all rejected
        """
        if not per_hunk:
            # Bulk approval
            self.console.print(self.renderer.render_patch(patch))
            if Confirm.ask("Apply this patch?", default=True, console=self.console):
                patch.approve_all()
                return True
            else:
                patch.reject_all()
                return False

        # Per-hunk approval
        self.console.print(f"\n[bold]Reviewing {len(patch.hunks)} hunks in {patch.new_file}[/bold]")
        self.console.print("[dim]y=yes, n=no, a=approve all remaining, q=reject all remaining[/dim]\n")

        for i, hunk in enumerate(patch.hunks, 1):
            if hunk.status != HunkStatus.PENDING:
                continue

            self.console.print(f"\n[bold cyan]Hunk {i}/{len(patch.hunks)}[/bold cyan]")
            self.console.print(self.renderer.render_hunk(hunk, patch.new_file))

            while True:
                try:
                    choice = self.console.input("[y/n/a/q] > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    # Reject remaining on interrupt
                    for h in patch.pending_hunks:
                        h.status = HunkStatus.REJECTED
                    return len(patch.approved_hunks) > 0

                if choice == "y":
                    hunk.status = HunkStatus.APPROVED
                    self.console.print("[green]Approved[/green]")
                    break
                elif choice == "n":
                    hunk.status = HunkStatus.REJECTED
                    self.console.print("[red]Rejected[/red]")
                    break
                elif choice == "a":
                    for h in patch.pending_hunks:
                        h.status = HunkStatus.APPROVED
                    self.console.print("[green]Approved all remaining hunks[/green]")
                    return True
                elif choice == "q":
                    for h in patch.pending_hunks:
                        h.status = HunkStatus.REJECTED
                    self.console.print("[red]Rejected all remaining hunks[/red]")
                    return len(patch.approved_hunks) > 0
                else:
                    self.console.print("[dim]Enter y, n, a, or q[/dim]")

        return len(patch.approved_hunks) > 0


def apply_patch(
    file_path: str,
    patch: Patch,
    approved_only: bool = True,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Apply a patch to a file.

    Args:
        file_path: Path to the file to patch
        patch: The patch to apply
        approved_only: Only apply approved hunks
        dry_run: If True, don't actually modify the file

    Returns:
        (success, message) tuple
    """
    path = Path(file_path)

    # Get hunks to apply
    if approved_only:
        hunks = patch.approved_hunks
    else:
        hunks = [h for h in patch.hunks if h.status != HunkStatus.REJECTED]

    if not hunks:
        return False, "No hunks to apply"

    # Read original content
    if path.exists():
        try:
            original_content = path.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Cannot read file: {e}"
    else:
        original_content = ""

    original_lines = original_content.splitlines(keepends=True)

    # Apply hunks in reverse order (to avoid offset issues)
    sorted_hunks = sorted(hunks, key=lambda h: h.old_start, reverse=True)
    new_lines = list(original_lines)

    for hunk in sorted_hunks:
        # Calculate the position to apply the hunk
        # Unified diff uses 1-based line numbers
        start_idx = hunk.old_start - 1

        # Build the replacement content
        replacement = []
        for line in hunk.lines:
            if line.type in (" ", "+"):
                replacement.append(line.content + "\n")

        # Calculate how many lines to remove
        remove_count = hunk.old_count

        # Apply the hunk
        new_lines[start_idx:start_idx + remove_count] = replacement

    new_content = "".join(new_lines)

    if dry_run:
        lines_changed = len([h for h in hunks])
        return True, f"Would apply {len(hunks)} hunks ({lines_changed} changes)"

    # Write the new content
    try:
        path.write_text(new_content, encoding="utf-8")
        return True, f"Applied {len(hunks)} hunks successfully"
    except Exception as e:
        return False, f"Failed to write file: {e}"


def preview_edit(
    file_path: str,
    old_text: str,
    new_text: str,
    console: Optional[Console] = None,
) -> Patch:
    """
    Generate and display a preview of a text replacement.

    This is a convenience function for previewing fs.edit operations.

    Args:
        file_path: Path to the file
        old_text: Text to search for
        new_text: Replacement text
        console: Optional Rich console

    Returns:
        Patch object for the changes
    """
    console = console or Console()
    path = Path(file_path)

    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return None

    original_content = path.read_text(encoding="utf-8")

    if old_text not in original_content:
        console.print(f"[red]Text not found in file[/red]")
        return None

    new_content = original_content.replace(old_text, new_text, 1)

    diff_text = generate_unified_diff(
        original_content,
        new_content,
        f"a/{path.name}",
        f"b/{path.name}",
    )

    patches = parse_unified_diff(diff_text)

    if patches:
        renderer = DiffRenderer(console)
        console.print(renderer.render_patch(patches[0]))
        return patches[0]

    return None
