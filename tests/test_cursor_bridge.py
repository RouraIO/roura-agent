"""
Tests for the Cursor bridge.

© Roura.io
"""
import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from roura_agent.agents.cursor_bridge import (
    CursorBridge,
    CursorTask,
    CursorTaskStatus,
    create_cursor_bridge,
)


class TestCursorTaskStatus:
    """Tests for CursorTaskStatus enum."""

    def test_statuses_exist(self):
        """Test all task statuses exist."""
        assert CursorTaskStatus.PENDING.value == "pending"
        assert CursorTaskStatus.IN_PROGRESS.value == "in_progress"
        assert CursorTaskStatus.COMPLETED.value == "completed"
        assert CursorTaskStatus.FAILED.value == "failed"
        assert CursorTaskStatus.EXPIRED.value == "expired"


class TestCursorTask:
    """Tests for CursorTask dataclass."""

    def test_create_task(self):
        """Test creating a cursor task."""
        task = CursorTask(
            id="task_1",
            task="Implement feature X",
        )
        assert task.id == "task_1"
        assert task.task == "Implement feature X"
        assert task.status == CursorTaskStatus.PENDING
        assert task.created_at is not None

    def test_task_with_context(self):
        """Test creating task with context."""
        task = CursorTask(
            id="task_2",
            task="Fix bug",
            context={"severity": "high"},
            files=["src/main.py", "src/utils.py"],
        )
        assert task.context["severity"] == "high"
        assert len(task.files) == 2

    def test_to_dict(self):
        """Test converting task to dict."""
        task = CursorTask(
            id="task_1",
            task="Test task",
            status=CursorTaskStatus.COMPLETED,
        )
        d = task.to_dict()
        assert d["id"] == "task_1"
        assert d["task"] == "Test task"
        assert d["status"] == "completed"

    def test_from_dict(self):
        """Test creating task from dict."""
        data = {
            "id": "task_1",
            "task": "Test task",
            "status": "pending",
            "created_at": "2024-01-01T00:00:00",
            "context": {"key": "value"},
        }
        task = CursorTask.from_dict(data)
        assert task.id == "task_1"
        assert task.status == CursorTaskStatus.PENDING
        assert task.context["key"] == "value"


class TestCursorBridge:
    """Tests for CursorBridge."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def bridge(self, temp_project):
        """Create a CursorBridge for testing."""
        return CursorBridge(temp_project, console=Mock())

    def test_init_creates_directories(self, bridge, temp_project):
        """Test initialization creates .roura directory."""
        roura_dir = Path(temp_project) / ".roura"
        assert roura_dir.exists()
        assert (roura_dir / "tasks").exists()
        assert (roura_dir / ".gitignore").exists()
        assert (roura_dir / "status.json").exists()

    def test_create_task(self, bridge, temp_project):
        """Test creating a task."""
        task = bridge.create_task(
            task_id="test_1",
            task_description="Test task description",
            context={"key": "value"},
            files=["file1.py"],
        )

        assert task.id == "test_1"
        assert task.task == "Test task description"
        assert task.status == CursorTaskStatus.PENDING

        # Check files were created
        tasks_dir = Path(temp_project) / ".roura" / "tasks"
        assert (tasks_dir / "test_1.md").exists()
        assert (tasks_dir / "test_1.json").exists()

    def test_create_task_with_file_contents(self, bridge, temp_project):
        """Test creating task with file contents."""
        task = bridge.create_task(
            task_id="test_2",
            task_description="Fix this code",
            file_contents={
                "main.py": "print('hello')",
                "utils.py": "def helper(): pass",
            },
        )

        # Check markdown file contains file contents
        md_file = Path(temp_project) / ".roura" / "tasks" / "test_2.md"
        content = md_file.read_text()
        assert "print('hello')" in content
        assert "def helper()" in content

    def test_get_task(self, bridge):
        """Test getting a task by ID."""
        bridge.create_task("task_1", "Task 1")
        bridge.create_task("task_2", "Task 2")

        task = bridge.get_task("task_1")
        assert task is not None
        assert task.task == "Task 1"

        assert bridge.get_task("nonexistent") is None

    def test_list_tasks(self, bridge):
        """Test listing all tasks."""
        bridge.create_task("task_1", "Task 1")
        bridge.create_task("task_2", "Task 2")

        tasks = bridge.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_by_status(self, bridge):
        """Test filtering tasks by status."""
        bridge.create_task("task_1", "Task 1")
        bridge.create_task("task_2", "Task 2")
        bridge.mark_complete("task_1", "Done")

        pending = bridge.list_tasks(CursorTaskStatus.PENDING)
        completed = bridge.list_tasks(CursorTaskStatus.COMPLETED)

        assert len(pending) == 1
        assert len(completed) == 1

    def test_mark_complete(self, bridge):
        """Test marking a task as complete."""
        bridge.create_task("task_1", "Task 1")
        task = bridge.mark_complete("task_1", "Successfully completed")

        assert task is not None
        assert task.status == CursorTaskStatus.COMPLETED
        assert task.result == "Successfully completed"
        assert task.completed_at is not None

    def test_cancel_task(self, bridge):
        """Test cancelling a task."""
        bridge.create_task("task_1", "Task 1")
        task = bridge.cancel_task("task_1")

        assert task is not None
        assert task.status == CursorTaskStatus.FAILED
        assert task.result == "Cancelled"

    def test_get_status_summary(self, bridge):
        """Test getting status summary."""
        bridge.create_task("task_1", "Task 1")
        bridge.create_task("task_2", "Task 2")
        bridge.mark_complete("task_1")

        summary = bridge.get_status_summary()
        assert summary["total"] == 2
        assert summary["pending"] == 1
        assert summary["completed"] == 1
        assert summary["failed"] == 0


class TestCursorBridgeIntegration:
    """Integration tests for CursorBridge."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def bridge(self, temp_project):
        """Create a CursorBridge for testing."""
        return CursorBridge(temp_project, console=Mock())

    def test_status_persists_to_file(self, bridge, temp_project):
        """Test that status is saved to file."""
        bridge.create_task("task_1", "Task 1")

        # Read status file directly
        status_file = Path(temp_project) / ".roura" / "status.json"
        data = json.loads(status_file.read_text())

        assert "tasks" in data
        assert "task_1" in data["tasks"]

    def test_task_json_created(self, bridge, temp_project):
        """Test that task JSON metadata is created."""
        bridge.create_task(
            "task_1",
            "Task 1",
            context={"priority": "high"},
        )

        json_file = Path(temp_project) / ".roura" / "tasks" / "task_1.json"
        data = json.loads(json_file.read_text())

        assert data["id"] == "task_1"
        assert data["context"]["priority"] == "high"

    def test_task_markdown_format(self, bridge, temp_project):
        """Test task markdown file format."""
        bridge.create_task(
            "feature_1",
            "Implement user authentication",
            context={"framework": "FastAPI"},
            files=["auth.py", "models.py"],
        )

        md_file = Path(temp_project) / ".roura" / "tasks" / "feature_1.md"
        content = md_file.read_text()

        assert "# Task: feature_1" in content
        assert "Implement user authentication" in content
        assert "auth.py" in content
        assert "models.py" in content
        assert "## Instructions" in content
        assert "## Result" in content

    def test_cleanup_old_tasks(self, bridge, temp_project):
        """Test cleaning up old tasks."""
        # Create a task and mark it complete with old date
        task = bridge.create_task("old_task", "Old task")
        bridge.mark_complete("old_task")

        # Manually set completed_at to old date
        from datetime import timedelta
        task.completed_at = datetime.now() - timedelta(days=10)
        bridge._tasks["old_task"] = task

        # Cleanup tasks older than 7 days
        removed = bridge.cleanup_old_tasks(max_age_days=7)
        assert removed == 1
        assert bridge.get_task("old_task") is None

    @patch("roura_agent.agents.cursor_bridge.subprocess.Popen")
    def test_open_in_cursor_success(self, mock_popen, bridge):
        """Test opening task in Cursor."""
        bridge._cursor_path = "/usr/bin/cursor"
        bridge.create_task("task_1", "Task 1")

        result = bridge.open_task_in_cursor("task_1")

        assert result is True
        mock_popen.assert_called_once()

    def test_open_in_cursor_no_cursor(self, bridge):
        """Test opening task when Cursor not available."""
        bridge._cursor_path = None
        bridge.create_task("task_1", "Task 1")

        result = bridge.open_task_in_cursor("task_1")
        assert result is False

    @patch("roura_agent.agents.cursor_bridge.subprocess.Popen")
    def test_send_to_clipboard(self, mock_popen, bridge):
        """Test sending text to clipboard."""
        mock_process = Mock()
        mock_process.communicate.return_value = (None, None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = bridge.send_to_clipboard("Test text")
        assert result is True


class TestCreateCursorBridge:
    """Tests for create_cursor_bridge helper."""

    def test_creates_bridge(self):
        """Test helper creates a bridge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = create_cursor_bridge(tmpdir)
            assert isinstance(bridge, CursorBridge)

    def test_uses_cwd_by_default(self):
        """Test helper uses current directory by default."""
        import os
        original_cwd = os.getcwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                bridge = create_cursor_bridge()
                # Bridge should be created in tmpdir
                # Use resolve() to handle macOS symlinks (/var -> /private/var)
                expected = (Path(tmpdir) / ".roura").resolve()
                actual = bridge._roura_dir.resolve()
                assert expected == actual
            finally:
                os.chdir(original_cwd)
