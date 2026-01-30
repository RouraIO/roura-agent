"""
Roura Agent Cursor Bridge - Advanced Cursor IDE integration.

This module provides a bidirectional communication bridge with Cursor IDE:
- File-based protocol for task handoffs
- Watch for task completion
- Parse changes and results
- Status tracking for pending tasks

© Roura.io
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Dict, List, Callable

from rich.console import Console

# Optional watchdog import for file watching
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object
    FileModifiedEvent = None


class CursorTaskStatus(Enum):
    """Status of a Cursor task."""
    PENDING = "pending"         # Task created, waiting for Cursor
    IN_PROGRESS = "in_progress" # User working on it in Cursor
    COMPLETED = "completed"     # User marked as done
    FAILED = "failed"           # Task failed or cancelled
    EXPIRED = "expired"         # Task timed out


@dataclass
class CursorTask:
    """A task delegated to Cursor."""
    id: str
    task: str
    context: Dict[str, Any] = field(default_factory=dict)
    files: List[str] = field(default_factory=list)  # Relevant file paths
    status: CursorTaskStatus = CursorTaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    changes: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "context": self.context,
            "files": self.files,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CursorTask":
        return cls(
            id=data["id"],
            task=data["task"],
            context=data.get("context", {}),
            files=data.get("files", []),
            status=CursorTaskStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result=data.get("result"),
            metadata=data.get("metadata", {}),
        )


class CursorTaskWatcher(FileSystemEventHandler):
    """Watches for changes to Cursor task files."""

    def __init__(
        self,
        callback: Callable[[str, Dict[str, Any]], None],
        console: Optional[Console] = None,
    ):
        self._callback = callback
        self._console = console or Console()

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            if event.src_path.endswith('.json'):
                try:
                    with open(event.src_path, 'r') as f:
                        data = json.load(f)
                    task_id = Path(event.src_path).stem
                    self._callback(task_id, data)
                except Exception as e:
                    self._console.print(f"[dim]Watch error: {e}[/dim]")


class CursorBridge:
    """
    Bridge for communicating with Cursor IDE.

    Uses a file-based protocol:
    1. Creates .roura/ directory in project root
    2. Writes task files with context and instructions
    3. Opens files in Cursor for user to work on
    4. Watches for changes to detect completion
    5. Parses git diff to extract changes made
    """

    ROURA_DIR = ".roura"
    TASKS_DIR = "tasks"
    STATUS_FILE = "status.json"

    def __init__(
        self,
        project_root: str,
        console: Optional[Console] = None,
    ):
        self._project_root = Path(project_root).resolve()
        self._console = console or Console()
        self._roura_dir = self._project_root / self.ROURA_DIR
        self._tasks_dir = self._roura_dir / self.TASKS_DIR
        self._tasks: Dict[str, CursorTask] = {}
        self._observer: Optional[Observer] = None
        self._watching = False
        self._cursor_path = self._find_cursor()

        # Initialize directories
        self._init_dirs()

    def _init_dirs(self) -> None:
        """Initialize the .roura directory structure."""
        self._roura_dir.mkdir(exist_ok=True)
        self._tasks_dir.mkdir(exist_ok=True)

        # Create .gitignore to ignore roura files
        gitignore = self._roura_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n!.gitignore\n")

        # Create status file
        self._save_status()

    def _find_cursor(self) -> Optional[str]:
        """Find Cursor CLI or app path."""
        # Check for cursor CLI in PATH
        try:
            result = subprocess.run(
                ["which", "cursor"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        # Check common macOS locations
        mac_paths = [
            "/Applications/Cursor.app/Contents/MacOS/Cursor",
            os.path.expanduser("~/Applications/Cursor.app/Contents/MacOS/Cursor"),
        ]
        for path in mac_paths:
            if os.path.exists(path):
                return path

        return None

    def is_available(self) -> bool:
        """Check if Cursor is available."""
        return self._cursor_path is not None

    # ===== Task Management =====

    def create_task(
        self,
        task_id: str,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
        files: Optional[List[str]] = None,
        file_contents: Optional[Dict[str, str]] = None,
    ) -> CursorTask:
        """
        Create a task file for Cursor.

        Args:
            task_id: Unique task identifier
            task_description: Description of what needs to be done
            context: Additional context dict
            files: List of relevant file paths
            file_contents: Dict of file paths to their contents

        Returns:
            The created CursorTask
        """
        cursor_task = CursorTask(
            id=task_id,
            task=task_description,
            context=context or {},
            files=files or [],
        )

        # Create task file
        task_file = self._tasks_dir / f"{task_id}.md"
        task_content = self._format_task_file(cursor_task, file_contents)
        task_file.write_text(task_content)

        # Create JSON metadata
        meta_file = self._tasks_dir / f"{task_id}.json"
        meta_file.write_text(json.dumps(cursor_task.to_dict(), indent=2))

        # Store task
        self._tasks[task_id] = cursor_task
        self._save_status()

        return cursor_task

    def _format_task_file(
        self,
        task: CursorTask,
        file_contents: Optional[Dict[str, str]] = None,
    ) -> str:
        """Format the task as a markdown file."""
        lines = [
            f"# Task: {task.id}",
            "",
            f"**Created:** {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Description",
            "",
            task.task,
            "",
        ]

        # Add context if present
        if task.context:
            lines.extend([
                "## Context",
                "",
                "```json",
                json.dumps(task.context, indent=2),
                "```",
                "",
            ])

        # Add relevant files
        if task.files:
            lines.extend([
                "## Relevant Files",
                "",
            ])
            for f in task.files:
                lines.append(f"- `{f}`")
            lines.append("")

        # Add file contents if provided
        if file_contents:
            lines.extend([
                "## File Contents",
                "",
            ])
            for path, content in file_contents.items():
                ext = Path(path).suffix[1:] if Path(path).suffix else ""
                lines.extend([
                    f"### {path}",
                    "",
                    f"```{ext}",
                    content,
                    "```",
                    "",
                ])

        # Add completion instructions
        lines.extend([
            "---",
            "",
            "## Instructions",
            "",
            "1. Make the requested changes in Cursor",
            "2. When done, update this file with your changes",
            "3. Add a `## Result` section with what you did",
            "",
            "---",
            "",
            "## Result",
            "",
            "_To be filled when complete..._",
            "",
        ])

        return "\n".join(lines)

    def get_task(self, task_id: str) -> Optional[CursorTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[CursorTaskStatus] = None) -> List[CursorTask]:
        """List all tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def mark_complete(
        self,
        task_id: str,
        result: Optional[str] = None,
    ) -> Optional[CursorTask]:
        """Mark a task as complete."""
        task = self._tasks.get(task_id)
        if task:
            task.status = CursorTaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.result = result

            # Try to parse changes from git diff
            task.changes = self._get_git_changes()

            # Update metadata file
            meta_file = self._tasks_dir / f"{task_id}.json"
            meta_file.write_text(json.dumps(task.to_dict(), indent=2))

            self._save_status()

        return task

    def cancel_task(self, task_id: str) -> Optional[CursorTask]:
        """Cancel a pending task."""
        task = self._tasks.get(task_id)
        if task and task.status == CursorTaskStatus.PENDING:
            task.status = CursorTaskStatus.FAILED
            task.result = "Cancelled"
            self._save_status()
        return task

    # ===== Cursor Integration =====

    def open_task_in_cursor(self, task_id: str) -> bool:
        """Open a task file in Cursor."""
        if not self._cursor_path:
            self._console.print("[red]Cursor not found[/red]")
            return False

        task_file = self._tasks_dir / f"{task_id}.md"
        if not task_file.exists():
            return False

        try:
            subprocess.Popen(
                [self._cursor_path, str(task_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            self._console.print(f"[red]Error opening Cursor: {e}[/red]")
            return False

    def open_project_in_cursor(self) -> bool:
        """Open the project root in Cursor."""
        if not self._cursor_path:
            return False

        try:
            subprocess.Popen(
                [self._cursor_path, str(self._project_root)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def send_to_clipboard(self, text: str) -> bool:
        """Copy text to clipboard (for Cursor Composer)."""
        try:
            # macOS
            process = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
            )
            process.communicate(text.encode())
            return process.returncode == 0
        except Exception:
            return False

    # ===== Watching =====

    def start_watching(
        self,
        on_task_update: Optional[Callable[[CursorTask], None]] = None,
    ) -> bool:
        """
        Start watching for task file changes.

        Returns False if watchdog is not available.
        """
        if not WATCHDOG_AVAILABLE:
            self._console.print(
                "[yellow]File watching not available. "
                "Install watchdog: pip install watchdog[/yellow]"
            )
            return False

        if self._watching:
            return True

        def handle_update(task_id: str, data: Dict[str, Any]):
            task = self._tasks.get(task_id)
            if task:
                old_status = task.status
                task.status = CursorTaskStatus(data.get("status", task.status.value))
                task.result = data.get("result", task.result)

                if task.status != old_status:
                    self._save_status()
                    if on_task_update:
                        on_task_update(task)

        event_handler = CursorTaskWatcher(handle_update, self._console)
        self._observer = Observer()
        self._observer.schedule(
            event_handler,
            str(self._tasks_dir),
            recursive=False,
        )
        self._observer.start()
        self._watching = True
        return True

    def stop_watching(self) -> None:
        """Stop watching for changes."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._watching = False

    def wait_for_completion(
        self,
        task_id: str,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
    ) -> Optional[CursorTask]:
        """
        Wait for a task to complete.

        Args:
            task_id: Task to wait for
            timeout: Maximum time to wait (None = forever)
            poll_interval: How often to check

        Returns:
            The completed task, or None if timeout
        """
        task = self._tasks.get(task_id)
        if not task:
            return None

        start_time = time.time()

        while True:
            # Reload task from file
            meta_file = self._tasks_dir / f"{task_id}.json"
            if meta_file.exists():
                try:
                    data = json.loads(meta_file.read_text())
                    task.status = CursorTaskStatus(data.get("status", task.status.value))
                    task.result = data.get("result", task.result)
                except Exception:
                    pass

            if task.status in (CursorTaskStatus.COMPLETED, CursorTaskStatus.FAILED):
                return task

            if timeout and (time.time() - start_time) >= timeout:
                task.status = CursorTaskStatus.EXPIRED
                return task

            time.sleep(poll_interval)

    # ===== Git Integration =====

    def _get_git_changes(self) -> List[Dict[str, Any]]:
        """Get recent git changes."""
        changes = []
        try:
            # Get diff of staged and unstaged changes
            result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=str(self._project_root),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            file_path = parts[0].strip()
                            change_info = parts[1].strip()
                            changes.append({
                                "file": file_path,
                                "changes": change_info,
                            })
        except Exception:
            pass
        return changes

    def get_recent_diff(self) -> str:
        """Get the recent git diff."""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=str(self._project_root),
                capture_output=True,
                text=True,
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception:
            return ""

    # ===== Status =====

    def _save_status(self) -> None:
        """Save status to file."""
        status = {
            "project_root": str(self._project_root),
            "last_updated": datetime.now().isoformat(),
            "tasks": {
                task_id: task.to_dict()
                for task_id, task in self._tasks.items()
            },
        }

        status_file = self._roura_dir / self.STATUS_FILE
        status_file.write_text(json.dumps(status, indent=2))

    def _load_status(self) -> None:
        """Load status from file."""
        status_file = self._roura_dir / self.STATUS_FILE
        if status_file.exists():
            try:
                data = json.loads(status_file.read_text())
                for task_id, task_data in data.get("tasks", {}).items():
                    self._tasks[task_id] = CursorTask.from_dict(task_data)
            except Exception:
                pass

    def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of all tasks."""
        return {
            "total": len(self._tasks),
            "pending": len([t for t in self._tasks.values() if t.status == CursorTaskStatus.PENDING]),
            "completed": len([t for t in self._tasks.values() if t.status == CursorTaskStatus.COMPLETED]),
            "failed": len([t for t in self._tasks.values() if t.status == CursorTaskStatus.FAILED]),
            "cursor_available": self.is_available(),
        }

    # ===== Cleanup =====

    def cleanup_old_tasks(self, max_age_days: int = 7) -> int:
        """Remove old completed/failed tasks."""
        cutoff = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
        removed = 0

        for task_id, task in list(self._tasks.items()):
            if task.status in (CursorTaskStatus.COMPLETED, CursorTaskStatus.FAILED):
                if task.completed_at and task.completed_at.timestamp() < cutoff:
                    # Remove files
                    (self._tasks_dir / f"{task_id}.md").unlink(missing_ok=True)
                    (self._tasks_dir / f"{task_id}.json").unlink(missing_ok=True)
                    del self._tasks[task_id]
                    removed += 1

        self._save_status()
        return removed


# Convenience function
def create_cursor_bridge(
    project_root: Optional[str] = None,
    console: Optional[Console] = None,
) -> CursorBridge:
    """Create a CursorBridge for the given project."""
    if project_root is None:
        project_root = os.getcwd()
    return CursorBridge(project_root, console)
