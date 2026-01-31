"""
Tests for the patch/diff system.

© Roura.io
"""
import pytest
from pathlib import Path

from roura_agent.patch import (
    DiffLine,
    DiffRenderer,
    Hunk,
    HunkStatus,
    Patch,
    apply_patch,
    generate_unified_diff,
    parse_unified_diff,
)


class TestDiffLine:
    """Tests for DiffLine dataclass."""

    def test_create_add_line(self):
        """Create an addition line."""
        line = DiffLine(type="+", content="new content")
        assert line.type == "+"
        assert line.content == "new content"

    def test_create_remove_line(self):
        """Create a removal line."""
        line = DiffLine(type="-", content="old content")
        assert line.type == "-"
        assert line.content == "old content"

    def test_create_context_line(self):
        """Create a context line."""
        line = DiffLine(type=" ", content="unchanged content")
        assert line.type == " "
        assert line.content == "unchanged content"


class TestHunk:
    """Tests for Hunk dataclass."""

    def test_empty_hunk(self):
        """Test empty hunk."""
        hunk = Hunk(old_start=1, old_count=0, new_start=1, new_count=0)
        assert hunk.added_lines == 0
        assert hunk.removed_lines == 0
        assert hunk.changes == 0

    def test_hunk_with_additions(self):
        """Test hunk with only additions."""
        hunk = Hunk(
            old_start=1,
            old_count=0,
            new_start=1,
            new_count=2,
            lines=[
                DiffLine(type="+", content="line 1"),
                DiffLine(type="+", content="line 2"),
            ],
        )
        assert hunk.added_lines == 2
        assert hunk.removed_lines == 0
        assert hunk.changes == 2

    def test_hunk_with_removals(self):
        """Test hunk with only removals."""
        hunk = Hunk(
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=0,
            lines=[
                DiffLine(type="-", content="old line 1"),
                DiffLine(type="-", content="old line 2"),
            ],
        )
        assert hunk.added_lines == 0
        assert hunk.removed_lines == 2
        assert hunk.changes == 2

    def test_hunk_with_modifications(self):
        """Test hunk with modifications (add + remove)."""
        hunk = Hunk(
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=[
                DiffLine(type="-", content="old content"),
                DiffLine(type="+", content="new content"),
            ],
        )
        assert hunk.added_lines == 1
        assert hunk.removed_lines == 1
        assert hunk.changes == 2

    def test_format_header(self):
        """Test hunk header formatting."""
        hunk = Hunk(old_start=10, old_count=5, new_start=10, new_count=6)
        assert hunk.format_header() == "@@ -10,5 +10,6 @@"

    def test_format_header_with_context(self):
        """Test hunk header with function context."""
        hunk = Hunk(
            old_start=10,
            old_count=5,
            new_start=10,
            new_count=6,
            context="def my_function():",
        )
        assert "@@ -10,5 +10,6 @@ def my_function():" in hunk.format_header()

    def test_get_old_content(self):
        """Test extracting old content."""
        hunk = Hunk(
            old_start=1,
            old_count=3,
            new_start=1,
            new_count=3,
            lines=[
                DiffLine(type=" ", content="context"),
                DiffLine(type="-", content="old line"),
                DiffLine(type="+", content="new line"),
                DiffLine(type=" ", content="more context"),
            ],
        )
        old = hunk.get_old_content()
        assert "context" in old
        assert "old line" in old
        assert "more context" in old
        assert "new line" not in old

    def test_get_new_content(self):
        """Test extracting new content."""
        hunk = Hunk(
            old_start=1,
            old_count=3,
            new_start=1,
            new_count=3,
            lines=[
                DiffLine(type=" ", content="context"),
                DiffLine(type="-", content="old line"),
                DiffLine(type="+", content="new line"),
                DiffLine(type=" ", content="more context"),
            ],
        )
        new = hunk.get_new_content()
        assert "context" in new
        assert "new line" in new
        assert "more context" in new
        assert "old line" not in new


class TestPatch:
    """Tests for Patch dataclass."""

    def test_empty_patch(self):
        """Test empty patch."""
        patch = Patch(old_file="a.txt", new_file="a.txt")
        assert patch.total_added == 0
        assert patch.total_removed == 0
        assert len(patch.hunks) == 0

    def test_patch_with_hunks(self):
        """Test patch with multiple hunks."""
        patch = Patch(
            old_file="a.txt",
            new_file="a.txt",
            hunks=[
                Hunk(
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=2,
                    lines=[
                        DiffLine(type="-", content="old"),
                        DiffLine(type="+", content="new1"),
                        DiffLine(type="+", content="new2"),
                    ],
                ),
                Hunk(
                    old_start=10,
                    old_count=2,
                    new_start=11,
                    new_count=1,
                    lines=[
                        DiffLine(type="-", content="remove1"),
                        DiffLine(type="-", content="remove2"),
                        DiffLine(type="+", content="keep"),
                    ],
                ),
            ],
        )
        assert patch.total_added == 3  # new1, new2, keep
        assert patch.total_removed == 3  # old, remove1, remove2

    def test_approve_all(self):
        """Test approving all hunks."""
        patch = Patch(
            old_file="a.txt",
            new_file="a.txt",
            hunks=[
                Hunk(old_start=1, old_count=1, new_start=1, new_count=1),
                Hunk(old_start=5, old_count=1, new_start=5, new_count=1),
            ],
        )
        patch.approve_all()
        assert all(h.status == HunkStatus.APPROVED for h in patch.hunks)

    def test_reject_all(self):
        """Test rejecting all hunks."""
        patch = Patch(
            old_file="a.txt",
            new_file="a.txt",
            hunks=[
                Hunk(old_start=1, old_count=1, new_start=1, new_count=1),
                Hunk(old_start=5, old_count=1, new_start=5, new_count=1),
            ],
        )
        patch.reject_all()
        assert all(h.status == HunkStatus.REJECTED for h in patch.hunks)

    def test_approved_hunks(self):
        """Test getting approved hunks."""
        patch = Patch(
            old_file="a.txt",
            new_file="a.txt",
            hunks=[
                Hunk(old_start=1, old_count=1, new_start=1, new_count=1, status=HunkStatus.APPROVED),
                Hunk(old_start=5, old_count=1, new_start=5, new_count=1, status=HunkStatus.REJECTED),
                Hunk(old_start=10, old_count=1, new_start=10, new_count=1, status=HunkStatus.APPROVED),
            ],
        )
        approved = patch.approved_hunks
        assert len(approved) == 2
        assert approved[0].old_start == 1
        assert approved[1].old_start == 10


class TestGenerateUnifiedDiff:
    """Tests for generate_unified_diff function."""

    def test_simple_modification(self):
        """Test generating diff for simple modification."""
        old = "line 1\nline 2\nline 3\n"
        new = "line 1\nmodified line 2\nline 3\n"

        diff = generate_unified_diff(old, new, "a/file.txt", "b/file.txt")

        assert "--- a/file.txt" in diff
        assert "+++ b/file.txt" in diff
        assert "-line 2" in diff
        assert "+modified line 2" in diff

    def test_addition(self):
        """Test generating diff for addition."""
        old = "line 1\nline 2\n"
        new = "line 1\nline 2\nline 3\n"

        diff = generate_unified_diff(old, new)

        assert "+line 3" in diff

    def test_deletion(self):
        """Test generating diff for deletion."""
        old = "line 1\nline 2\nline 3\n"
        new = "line 1\nline 3\n"

        diff = generate_unified_diff(old, new)

        assert "-line 2" in diff

    def test_no_changes(self):
        """Test generating diff when no changes."""
        content = "line 1\nline 2\n"
        diff = generate_unified_diff(content, content)
        # Empty diff when no changes
        assert diff == ""


class TestParseUnifiedDiff:
    """Tests for parse_unified_diff function."""

    def test_simple_diff(self):
        """Test parsing simple diff."""
        diff = """--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line 1
-old line
+new line
 line 3
"""
        patches = parse_unified_diff(diff)

        assert len(patches) == 1
        assert patches[0].old_file == "file.txt"
        assert patches[0].new_file == "file.txt"
        assert len(patches[0].hunks) == 1

        hunk = patches[0].hunks[0]
        assert hunk.old_start == 1
        assert hunk.old_count == 3
        assert hunk.new_start == 1
        assert hunk.new_count == 3

    def test_multiple_hunks(self):
        """Test parsing diff with multiple hunks."""
        diff = """--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,3 @@
 line 1
+inserted
 line 2
@@ -10,2 +11,2 @@
 line 10
-removed
+replaced
"""
        patches = parse_unified_diff(diff)

        assert len(patches) == 1
        assert len(patches[0].hunks) == 2

    def test_hunk_with_context(self):
        """Test parsing hunk with function context."""
        diff = """--- a/file.py
+++ b/file.py
@@ -10,5 +10,6 @@ def my_function():
     context
-    old
+    new
     more context
"""
        patches = parse_unified_diff(diff)

        assert len(patches) == 1
        hunk = patches[0].hunks[0]
        assert "my_function" in hunk.context


class TestApplyPatch:
    """Tests for apply_patch function."""

    def test_apply_simple_patch(self, tmp_path):
        """Test applying a simple patch."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nold line\nline 3\n")

        # Create patch
        patch = Patch(
            old_file="test.txt",
            new_file="test.txt",
            hunks=[
                Hunk(
                    old_start=1,
                    old_count=3,
                    new_start=1,
                    new_count=3,
                    lines=[
                        DiffLine(type=" ", content="line 1"),
                        DiffLine(type="-", content="old line"),
                        DiffLine(type="+", content="new line"),
                        DiffLine(type=" ", content="line 3"),
                    ],
                    status=HunkStatus.APPROVED,
                ),
            ],
        )

        success, message = apply_patch(str(test_file), patch)

        assert success
        content = test_file.read_text()
        assert "new line" in content
        assert "old line" not in content

    def test_apply_only_approved_hunks(self, tmp_path):
        """Test that only approved hunks are applied."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\n")

        patch = Patch(
            old_file="test.txt",
            new_file="test.txt",
            hunks=[
                Hunk(
                    old_start=2,
                    old_count=1,
                    new_start=2,
                    new_count=1,
                    lines=[
                        DiffLine(type="-", content="line 2"),
                        DiffLine(type="+", content="APPROVED"),
                    ],
                    status=HunkStatus.APPROVED,
                ),
                Hunk(
                    old_start=3,
                    old_count=1,
                    new_start=3,
                    new_count=1,
                    lines=[
                        DiffLine(type="-", content="line 3"),
                        DiffLine(type="+", content="REJECTED"),
                    ],
                    status=HunkStatus.REJECTED,
                ),
            ],
        )

        success, _ = apply_patch(str(test_file), patch, approved_only=True)

        assert success
        content = test_file.read_text()
        assert "APPROVED" in content
        assert "REJECTED" not in content
        assert "line 3" in content  # Original preserved

    def test_dry_run(self, tmp_path):
        """Test dry run mode."""
        test_file = tmp_path / "test.txt"
        original_content = "line 1\nold line\nline 3\n"
        test_file.write_text(original_content)

        patch = Patch(
            old_file="test.txt",
            new_file="test.txt",
            hunks=[
                Hunk(
                    old_start=2,
                    old_count=1,
                    new_start=2,
                    new_count=1,
                    lines=[
                        DiffLine(type="-", content="old line"),
                        DiffLine(type="+", content="new line"),
                    ],
                    status=HunkStatus.APPROVED,
                ),
            ],
        )

        success, message = apply_patch(str(test_file), patch, dry_run=True)

        assert success
        assert "Would apply" in message
        # File should be unchanged
        assert test_file.read_text() == original_content

    def test_no_hunks_to_apply(self, tmp_path):
        """Test when no hunks are approved."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n")

        patch = Patch(
            old_file="test.txt",
            new_file="test.txt",
            hunks=[
                Hunk(
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=[DiffLine(type="-", content="content")],
                    status=HunkStatus.REJECTED,
                ),
            ],
        )

        success, message = apply_patch(str(test_file), patch)

        assert not success
        assert "No hunks to apply" in message


class TestDiffRenderer:
    """Tests for DiffRenderer class."""

    def test_render_hunk(self):
        """Test rendering a hunk."""
        renderer = DiffRenderer()
        hunk = Hunk(
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=2,
            lines=[
                DiffLine(type="-", content="old"),
                DiffLine(type="+", content="new"),
            ],
        )

        panel = renderer.render_hunk(hunk, "test.py")

        # Panel should be created without error
        assert panel is not None
        assert panel.title is not None

    def test_render_patch(self):
        """Test rendering a patch."""
        renderer = DiffRenderer()
        patch = Patch(
            old_file="test.py",
            new_file="test.py",
            hunks=[
                Hunk(
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=[DiffLine(type="+", content="new line")],
                ),
            ],
        )

        panel = renderer.render_patch(patch)

        assert panel is not None
        assert "test.py" in panel.title
