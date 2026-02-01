"""
Tests for progress UI module.

© Roura.io
"""
import pytest
from io import StringIO
from rich.console import Console

from roura_agent.ui.progress import (
    TaskList,
    TaskStatus,
    ProgressTracker,
    Task,
)


class TestTaskList:
    """Tests for TaskList class."""

    def test_add_task(self):
        """Should add tasks."""
        tasks = TaskList()
        tasks.add_task("Task 1")
        tasks.add_task("Task 2")

        assert len(tasks.tasks) == 2
        assert "Task 1" in tasks.tasks
        assert "Task 2" in tasks.tasks

    def test_set_status(self):
        """Should set task status."""
        tasks = TaskList()
        tasks.add_task("Task 1")

        tasks.set_status("Task 1", TaskStatus.ACTIVE)
        assert tasks.tasks["Task 1"].status == TaskStatus.ACTIVE

        tasks.set_status("Task 1", TaskStatus.DONE)
        assert tasks.tasks["Task 1"].status == TaskStatus.DONE

    def test_get_active_task(self):
        """Should return active task name."""
        tasks = TaskList()
        tasks.add_task("Task 1")
        tasks.add_task("Task 2")

        tasks.set_status("Task 1", TaskStatus.DONE)
        tasks.set_status("Task 2", TaskStatus.ACTIVE)

        assert tasks.get_active_task() == "Task 2"

    def test_get_completed_count(self):
        """Should count completed tasks."""
        tasks = TaskList()
        tasks.add_task("Task 1")
        tasks.add_task("Task 2")
        tasks.add_task("Task 3")

        tasks.set_status("Task 1", TaskStatus.DONE)
        tasks.set_status("Task 2", TaskStatus.SKIPPED)

        assert tasks.get_completed_count() == 2

    def test_render_includes_tasks(self):
        """Rendered output should include task names."""
        tasks = TaskList()
        tasks.add_task("Read files")
        tasks.add_task("Process data")

        output = tasks.render()

        assert "Read files" in output
        assert "Process data" in output

    def test_render_includes_status_icons(self):
        """Rendered output should include status icons."""
        tasks = TaskList()
        tasks.add_task("Done task")
        tasks.add_task("Active task")
        tasks.add_task("Failed task")

        tasks.set_status("Done task", TaskStatus.DONE)
        tasks.set_status("Active task", TaskStatus.ACTIVE)
        tasks.set_status("Failed task", TaskStatus.FAILED)

        output = tasks.render()

        assert "✓" in output  # Done
        assert "●" in output  # Active
        assert "✗" in output  # Failed

    def test_render_includes_progress(self):
        """Rendered output should include progress count."""
        tasks = TaskList()
        tasks.add_task("Task 1")
        tasks.add_task("Task 2")
        tasks.set_status("Task 1", TaskStatus.DONE)

        output = tasks.render()

        assert "1/2" in output

    def test_set_action(self):
        """Should track current action."""
        tasks = TaskList()
        tasks.set_action("Reading file.py")

        output = tasks.render()

        assert "Reading file.py" in output

    def test_increment_retry(self):
        """Should track retry count."""
        tasks = TaskList()
        tasks.increment_retry()
        tasks.increment_retry()

        output = tasks.render()

        assert "Retries: 2" in output


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_add_step(self):
        """Should add steps."""
        console = Console(file=StringIO())

        with ProgressTracker(console, "Test", live=False) as tracker:
            tracker.add_step("Step 1")
            tracker.add_step("Step 2")

            assert len(tracker.tasks.tasks) == 2

    def test_step_context_manager(self):
        """Step context manager should update status."""
        console = Console(file=StringIO())

        with ProgressTracker(console, "Test", live=False) as tracker:
            tracker.add_step("Step 1")

            with tracker.step("Step 1"):
                assert tracker.tasks.tasks["Step 1"].status == TaskStatus.ACTIVE

            assert tracker.tasks.tasks["Step 1"].status == TaskStatus.DONE

    def test_step_handles_error(self):
        """Step should handle errors gracefully."""
        console = Console(file=StringIO())

        with ProgressTracker(console, "Test", live=False) as tracker:
            tracker.add_step("Step 1")

            try:
                with tracker.step("Step 1"):
                    raise ValueError("test error")
            except ValueError:
                pass

            assert tracker.tasks.tasks["Step 1"].status == TaskStatus.FAILED

    def test_retry_increments_counter(self):
        """Retry should increment counter."""
        console = Console(file=StringIO())

        with ProgressTracker(console, "Test", live=False) as tracker:
            tracker.retry("Approach 1 failed")

            assert tracker.tasks.retry_count == 1


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_defined(self):
        """All expected statuses should be defined."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.ACTIVE.value == "active"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"
