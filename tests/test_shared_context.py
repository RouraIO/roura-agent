"""
Tests for the shared execution context.

© Roura.io
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from roura_agent.agents.context import (
    SharedExecutionContext,
    FileSnapshot,
    ModificationRecord,
    get_shared_context,
)
from roura_agent.tools.base import ToolResult


class TestFileSnapshot:
    """Tests for FileSnapshot dataclass."""

    def test_create_snapshot(self):
        """Test creating a file snapshot."""
        snapshot = FileSnapshot(
            path="/path/to/file.py",
            content="print('hello')",
            agent="code",
        )
        assert snapshot.path == "/path/to/file.py"
        assert snapshot.content == "print('hello')"
        assert snapshot.agent == "code"
        assert snapshot.timestamp is not None


class TestModificationRecord:
    """Tests for ModificationRecord dataclass."""

    def test_create_record(self):
        """Test creating a modification record."""
        record = ModificationRecord(
            path="/path/to/file.py",
            old_content="old code",
            new_content="new code",
            action="modified",
            agent="code",
            tool_name="fs.write",
        )
        assert record.path == "/path/to/file.py"
        assert record.old_content == "old code"
        assert record.new_content == "new code"
        assert record.action == "modified"
        assert record.agent == "code"


class TestSharedExecutionContext:
    """Tests for SharedExecutionContext."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        SharedExecutionContext.reset()
        yield
        SharedExecutionContext.reset()

    def test_singleton_pattern(self):
        """Test that SharedExecutionContext is a singleton."""
        ctx1 = SharedExecutionContext()
        ctx2 = SharedExecutionContext()
        assert ctx1 is ctx2

    def test_get_instance(self):
        """Test get_instance returns singleton."""
        ctx1 = SharedExecutionContext.get_instance()
        ctx2 = SharedExecutionContext.get_instance()
        assert ctx1 is ctx2

    def test_reset_creates_new_instance(self):
        """Test reset creates new singleton instance."""
        ctx1 = SharedExecutionContext()
        SharedExecutionContext.reset()
        ctx2 = SharedExecutionContext()
        assert ctx1 is not ctx2

    def test_record_read(self):
        """Test recording a file read."""
        ctx = SharedExecutionContext()
        ctx.record_read("/test/file.py", "content here", agent="code")

        assert ctx.has_read("/test/file.py")
        content = ctx.get_file_content("/test/file.py")
        assert content == "content here"

    def test_has_read_false_for_unread(self):
        """Test has_read returns False for unread files."""
        ctx = SharedExecutionContext()
        assert ctx.has_read("/unread/file.py") is False

    def test_record_modification(self):
        """Test recording a modification."""
        ctx = SharedExecutionContext()
        ctx.record_modification(
            path="/test/file.py",
            old_content="old",
            new_content="new",
            action="modified",
            agent="code",
            tool_name="fs.edit",
        )

        mods = ctx.modifications
        assert len(mods) == 1
        assert mods[0].old_content == "old"
        assert mods[0].new_content == "new"
        assert mods[0].agent == "code"

    def test_get_modified_files(self):
        """Test getting list of modified files."""
        ctx = SharedExecutionContext()
        ctx.record_modification("/a.py", None, "a", "created", "code")
        ctx.record_modification("/b.py", None, "b", "created", "code")
        ctx.record_modification("/a.py", "a", "a2", "modified", "code")

        files = ctx.get_modified_files()
        assert len(files) == 2
        assert "/a.py" in files or str(Path("/a.py").resolve()) in files

    def test_get_modifications_by_agent(self):
        """Test filtering modifications by agent."""
        ctx = SharedExecutionContext()
        ctx.record_modification("/a.py", None, "a", "created", "code")
        ctx.record_modification("/b.py", None, "b", "created", "test")

        code_mods = ctx.get_modifications_by_agent("code")
        assert len(code_mods) == 1
        test_mods = ctx.get_modifications_by_agent("test")
        assert len(test_mods) == 1

    def test_record_tool_call(self):
        """Test recording tool calls."""
        ctx = SharedExecutionContext()
        result = ToolResult(success=True, output={"data": "test"})
        ctx.record_tool_call("fs.read", {"path": "/file.py"}, result, "code")

        history = ctx.tool_history
        assert len(history) == 1
        assert history[0]["tool"] == "fs.read"
        assert history[0]["agent"] == "code"
        assert history[0]["success"] is True

    def test_get_tool_history_for_agent(self):
        """Test filtering tool history by agent."""
        ctx = SharedExecutionContext()
        result = ToolResult(success=True, output={})

        ctx.record_tool_call("fs.read", {}, result, "code")
        ctx.record_tool_call("shell.exec", {}, result, "test")

        code_history = ctx.get_tool_history_for_agent("code")
        assert len(code_history) == 1
        assert code_history[0]["tool"] == "fs.read"

    def test_project_root(self):
        """Test project root property."""
        ctx = SharedExecutionContext()
        assert ctx.project_root is None

        ctx.project_root = "/my/project"
        assert ctx.project_root == "/my/project"

    def test_session_id_created(self):
        """Test session ID is created."""
        ctx = SharedExecutionContext()
        assert ctx.session_id is not None
        assert len(ctx.session_id) > 0

    def test_metadata(self):
        """Test metadata storage."""
        ctx = SharedExecutionContext()
        ctx.set_metadata("key1", "value1")
        ctx.set_metadata("key2", {"nested": "data"})

        assert ctx.get_metadata("key1") == "value1"
        assert ctx.get_metadata("key2")["nested"] == "data"
        assert ctx.get_metadata("missing") is None
        assert ctx.get_metadata("missing", "default") == "default"

    def test_clear_read_cache(self):
        """Test clearing read cache."""
        ctx = SharedExecutionContext()
        ctx.record_read("/a.py", "a")
        ctx.record_read("/b.py", "b")

        assert ctx.has_read("/a.py")
        ctx.clear_read_cache("/a.py")
        assert not ctx.has_read("/a.py")
        assert ctx.has_read("/b.py")

    def test_clear_all_read_cache(self):
        """Test clearing all read cache."""
        ctx = SharedExecutionContext()
        ctx.record_read("/a.py", "a")
        ctx.record_read("/b.py", "b")

        ctx.clear_read_cache()
        assert not ctx.has_read("/a.py")
        assert not ctx.has_read("/b.py")

    def test_get_summary(self):
        """Test getting context summary."""
        ctx = SharedExecutionContext()
        ctx.record_read("/file.py", "content")
        ctx.record_modification("/file.py", "old", "new", "modified", "code")

        result = ToolResult(success=True, output={})
        ctx.record_tool_call("fs.edit", {}, result, "code")

        summary = ctx.get_summary()
        assert summary["files_read_count"] == 1
        assert summary["files_modified_count"] == 1
        assert summary["tool_calls_count"] == 1
        assert "code" in summary["agents_used"]


class TestUndoFunctionality:
    """Tests for undo functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        SharedExecutionContext.reset()
        yield
        SharedExecutionContext.reset()

    def test_can_undo_returns_false_initially(self):
        """Test can_undo returns False when no modifications."""
        ctx = SharedExecutionContext()
        assert ctx.can_undo() is False

    def test_can_undo_returns_true_after_modification(self):
        """Test can_undo returns True after modification."""
        ctx = SharedExecutionContext()
        ctx.record_modification("/file.py", "old", "new", "modified", "code")
        assert ctx.can_undo() is True

    def test_undo_last_returns_record(self):
        """Test undo_last returns the modification record."""
        ctx = SharedExecutionContext()
        ctx.record_modification("/file.py", "old", "new", "modified", "code")

        # Need a real file for undo to work
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("new content")
            temp_path = f.name

        try:
            ctx.record_modification(temp_path, "old content", "new content", "modified", "code")
            record = ctx.undo_last()

            assert record is not None
            assert record.action == "modified"
            # File should be restored
            content = Path(temp_path).read_text()
            assert content == "old content"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_undo_last_returns_none_when_empty(self):
        """Test undo_last returns None when no modifications."""
        ctx = SharedExecutionContext()
        record = ctx.undo_last()
        assert record is None


class TestGetSharedContext:
    """Tests for get_shared_context helper."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        SharedExecutionContext.reset()
        yield
        SharedExecutionContext.reset()

    def test_get_shared_context_returns_singleton(self):
        """Test that get_shared_context returns the singleton."""
        ctx1 = get_shared_context()
        ctx2 = get_shared_context()
        assert ctx1 is ctx2

    def test_get_shared_context_same_as_direct(self):
        """Test get_shared_context returns same as direct call."""
        ctx1 = get_shared_context()
        ctx2 = SharedExecutionContext()
        assert ctx1 is ctx2
