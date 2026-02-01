"""
Tests for repo tools module.

© Roura.io
"""
import pytest
from pathlib import Path
from roura_agent.repo_tools import (
    list_files,
    search_symbol,
    read_file,
    read_files,
    get_file_info,
    IGNORE_DIRS,
)


class TestListFiles:
    """Tests for list_files function."""

    def test_list_files_in_current_dir(self, tmp_path):
        """List files in a directory."""
        (tmp_path / "test.py").write_text("# test")
        (tmp_path / "main.py").write_text("# main")

        files = list_files(tmp_path, ["**/*.py"])
        assert len(files) == 2
        assert "test.py" in files
        assert "main.py" in files

    def test_ignores_venv(self, tmp_path):
        """Should ignore .venv directory."""
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "lib.py").write_text("# venv")
        (tmp_path / "main.py").write_text("# main")

        files = list_files(tmp_path, ["**/*.py"])
        assert "main.py" in files
        assert ".venv/lib.py" not in files

    def test_ignores_node_modules(self, tmp_path):
        """Should ignore node_modules directory."""
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.js").write_text("// pkg")
        (tmp_path / "app.js").write_text("// app")

        files = list_files(tmp_path, ["**/*.js"])
        assert "app.js" in files
        assert any("node_modules" in f for f in files) is False

    def test_respects_max_files(self, tmp_path):
        """Should respect max_files limit."""
        for i in range(20):
            (tmp_path / f"file{i}.py").write_text(f"# {i}")

        files = list_files(tmp_path, ["**/*.py"], max_files=5)
        assert len(files) <= 5


class TestSearchSymbol:
    """Tests for search_symbol function."""

    def test_finds_pattern(self, tmp_path):
        """Should find pattern in files."""
        (tmp_path / "test.py").write_text("def my_function():\n    pass")

        results = search_symbol(tmp_path, "my_function", ["**/*.py"])
        assert len(results) > 0
        assert results[0]["line_text"].startswith("def my_function")

    def test_returns_line_numbers(self, tmp_path):
        """Should return correct line numbers."""
        (tmp_path / "test.py").write_text("line1\nline2\ntarget_line\nline4")

        results = search_symbol(tmp_path, "target_line", ["**/*.py"])
        assert len(results) == 1
        assert results[0]["line_no"] == 3


class TestReadFile:
    """Tests for read_file function."""

    def test_reads_file(self, tmp_path):
        """Should read file content."""
        (tmp_path / "test.txt").write_text("hello world")

        content = read_file(tmp_path / "test.txt")
        assert content == "hello world"

    def test_truncates_large_files(self, tmp_path):
        """Should truncate files exceeding max_bytes."""
        large_content = "x" * 1000
        (tmp_path / "large.txt").write_text(large_content)

        content = read_file(tmp_path / "large.txt", max_bytes=100)
        assert len(content) < 1000
        assert "TRUNCATED" in content

    def test_raises_on_missing_file(self, tmp_path):
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            read_file(tmp_path / "missing.txt")


class TestReadFiles:
    """Tests for read_files function."""

    def test_batch_read(self, tmp_path):
        """Should read multiple files."""
        (tmp_path / "a.txt").write_text("content a")
        (tmp_path / "b.txt").write_text("content b")

        results = read_files([tmp_path / "a.txt", tmp_path / "b.txt"])
        assert len(results) == 2
        assert "content a" in results[str(tmp_path / "a.txt")]
        assert "content b" in results[str(tmp_path / "b.txt")]


class TestGetFileInfo:
    """Tests for get_file_info function."""

    def test_file_info(self, tmp_path):
        """Should return file metadata."""
        (tmp_path / "test.py").write_text("line1\nline2\nline3")

        info = get_file_info(tmp_path / "test.py")
        assert info["exists"] is True
        assert info["extension"] == ".py"
        assert info["line_count"] == 3

    def test_missing_file(self, tmp_path):
        """Should handle missing files."""
        info = get_file_info(tmp_path / "missing.txt")
        assert info["exists"] is False
