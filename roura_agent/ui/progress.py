"""
Roura Agent Progress UI - Task tracking and progress display.

Provides consistent progress UI for grind-mode operations:
- Deep review
- Code write
- Diagnose
- Execution loop

© Roura.io
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.table import Table
from rich.text import Text


class TaskStatus(Enum):
    """Status of a task in the task list."""
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """A single task in the task list."""
    name: str
    status: TaskStatus = TaskStatus.PENDING
    detail: str = ""
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None


class TaskList:
    """
    Track and display a list of tasks with progress.

    Usage:
        tasks = TaskList(console)
        tasks.add_task("Read files")
        tasks.add_task("Analyze code")
        tasks.add_task("Generate report")

        tasks.set_status("Read files", TaskStatus.ACTIVE)
        # ... do work ...
        tasks.set_status("Read files", TaskStatus.DONE)

        tasks.render()
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.tasks: dict[str, Task] = {}
        self.order: list[str] = []
        self.current_action: str = ""
        self.retry_count: int = 0
        self.start_time: float = time.time()

    def add_task(self, name: str, detail: str = "") -> None:
        """Add a new task to the list."""
        if name not in self.tasks:
            self.tasks[name] = Task(name=name, detail=detail)
            self.order.append(name)

    def set_status(
        self,
        name: str,
        status: TaskStatus,
        detail: str = "",
        error: str = "",
    ) -> None:
        """Set the status of a task."""
        if name not in self.tasks:
            self.add_task(name)

        task = self.tasks[name]
        task.status = status

        if detail:
            task.detail = detail
        if error:
            task.error = error

        if status == TaskStatus.ACTIVE and task.started_at is None:
            task.started_at = time.time()
        elif status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SKIPPED):
            task.completed_at = time.time()

    def set_action(self, action: str) -> None:
        """Set the current action being performed."""
        self.current_action = action

    def increment_retry(self) -> None:
        """Increment retry count (for failed approach switching)."""
        self.retry_count += 1

    def get_active_task(self) -> Optional[str]:
        """Get the currently active task name."""
        for name in self.order:
            if self.tasks[name].status == TaskStatus.ACTIVE:
                return name
        return None

    def get_completed_count(self) -> int:
        """Get count of completed tasks."""
        return sum(
            1 for t in self.tasks.values()
            if t.status in (TaskStatus.DONE, TaskStatus.SKIPPED)
        )

    def get_failed_count(self) -> int:
        """Get count of failed tasks."""
        return sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)

    def render(self) -> str:
        """Render the task list as a string."""
        lines = []

        # Header
        elapsed = time.time() - self.start_time
        completed = self.get_completed_count()
        total = len(self.tasks)

        lines.append(f"Progress: {completed}/{total} tasks ({elapsed:.1f}s)")
        if self.retry_count > 0:
            lines.append(f"  ⚠️ Retries: {self.retry_count}")
        lines.append("")

        # Tasks
        for name in self.order:
            task = self.tasks[name]

            # Status icon
            icons = {
                TaskStatus.PENDING: "○",
                TaskStatus.ACTIVE: "●",
                TaskStatus.DONE: "✓",
                TaskStatus.FAILED: "✗",
                TaskStatus.SKIPPED: "–",
            }
            icon = icons.get(task.status, "?")

            # Status color
            colors = {
                TaskStatus.PENDING: "dim",
                TaskStatus.ACTIVE: "cyan",
                TaskStatus.DONE: "green",
                TaskStatus.FAILED: "red",
                TaskStatus.SKIPPED: "yellow",
            }
            color = colors.get(task.status, "white")

            line = f"  [{color}]{icon}[/{color}] {name}"

            # Add detail or error
            if task.status == TaskStatus.ACTIVE and task.detail:
                line += f" [{color}]({task.detail})[/{color}]"
            elif task.status == TaskStatus.FAILED and task.error:
                line += f" [red]({task.error})[/red]"
            elif task.status == TaskStatus.DONE and task.completed_at and task.started_at:
                duration = task.completed_at - task.started_at
                line += f" [dim]({duration:.1f}s)[/dim]"

            lines.append(line)

        # Current action
        if self.current_action:
            lines.append("")
            lines.append(f"  → {self.current_action}")

        return "\n".join(lines)

    def render_rich(self) -> Panel:
        """Render as a Rich Panel for live display."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=3)
        table.add_column("Task")
        table.add_column("Detail", style="dim")

        for name in self.order:
            task = self.tasks[name]

            icons = {
                TaskStatus.PENDING: ("○", "dim"),
                TaskStatus.ACTIVE: ("●", "cyan bold"),
                TaskStatus.DONE: ("✓", "green"),
                TaskStatus.FAILED: ("✗", "red"),
                TaskStatus.SKIPPED: ("–", "yellow"),
            }
            icon, style = icons.get(task.status, ("?", "white"))

            detail = ""
            if task.status == TaskStatus.ACTIVE and task.detail:
                detail = task.detail
            elif task.status == TaskStatus.FAILED and task.error:
                detail = task.error
            elif task.status == TaskStatus.DONE and task.completed_at and task.started_at:
                duration = task.completed_at - task.started_at
                detail = f"{duration:.1f}s"

            table.add_row(
                Text(icon, style=style),
                Text(name, style=style if task.status == TaskStatus.ACTIVE else ""),
                detail,
            )

        elapsed = time.time() - self.start_time
        completed = self.get_completed_count()
        total = len(self.tasks)

        title = f"Progress: {completed}/{total} ({elapsed:.1f}s)"
        if self.retry_count > 0:
            title += f" | Retries: {self.retry_count}"

        return Panel(table, title=title, border_style="cyan")

    def print(self) -> None:
        """Print the task list to console."""
        self.console.print(self.render_rich())


class ProgressTracker:
    """
    Context manager for tracking progress of a multi-step operation.

    Usage:
        with ProgressTracker(console, "Deep Review") as tracker:
            tracker.add_step("Build index")
            tracker.add_step("Analyze files")
            tracker.add_step("Generate report")

            with tracker.step("Build index"):
                # ... do work ...
                pass
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        title: str = "Progress",
        live: bool = True,
    ):
        self.console = console or Console()
        self.title = title
        self.tasks = TaskList(console)
        self.live = live
        self._live_context: Optional[Live] = None

    def __enter__(self) -> "ProgressTracker":
        if self.live:
            self._live_context = Live(
                self.tasks.render_rich(),
                console=self.console,
                refresh_per_second=4,
                transient=True,
            )
            self._live_context.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._live_context:
            self._live_context.__exit__(exc_type, exc_val, exc_tb)
        # Print final state
        self.tasks.print()

    def add_step(self, name: str, detail: str = "") -> None:
        """Add a step to track."""
        self.tasks.add_task(name, detail)
        self._update()

    def step(self, name: str) -> "StepContext":
        """Context manager for a single step."""
        return StepContext(self, name)

    def set_action(self, action: str) -> None:
        """Set current action being performed."""
        self.tasks.set_action(action)
        self._update()

    def retry(self, reason: str = "") -> None:
        """Mark that an approach failed and switching."""
        self.tasks.increment_retry()
        if reason:
            self.set_action(f"Approach failed: {reason}, switching...")
        else:
            self.set_action("Approach failed, switching...")
        self._update()

    def _update(self) -> None:
        """Update live display."""
        if self._live_context:
            self._live_context.update(self.tasks.render_rich())


class StepContext:
    """Context manager for a single step in progress tracking."""

    def __init__(self, tracker: ProgressTracker, name: str):
        self.tracker = tracker
        self.name = name

    def __enter__(self) -> "StepContext":
        self.tracker.tasks.set_status(self.name, TaskStatus.ACTIVE)
        self.tracker._update()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.tracker.tasks.set_status(
                self.name,
                TaskStatus.FAILED,
                error=str(exc_val)[:50] if exc_val else "Error",
            )
        else:
            self.tracker.tasks.set_status(self.name, TaskStatus.DONE)
        self.tracker._update()

    def update(self, detail: str) -> None:
        """Update step detail."""
        self.tracker.tasks.set_status(self.name, TaskStatus.ACTIVE, detail=detail)
        self.tracker._update()
