"""
Tests for repo index module.

© Roura.io
"""
import pytest
import time
from pathlib import Path
from roura_agent.repo_index import (
    RepoIndex,
    build_repo_index,
    load_index,
    save_index,
    get_or_build_index,
    get_largest_by_language,
    get_index_summary,
)


class TestBuildRepoIndex:
    """Tests for build_repo_index function."""

    def test_builds_index(self, tmp_path):
        """Should build index from directory."""
        (tmp_path / "main.py").write_text("# line1\n# line2\n# line3")
        (tmp_path / "test.py").write_text("# test")
        (tmp_path / "config.json").write_text("{}")

        index = build_repo_index(tmp_path)

        assert index.root == str(tmp_path)
        assert index.total_files >= 3
        assert ".py" in index.file_count_by_ext

    def test_counts_extensions(self, tmp_path):
        """Should count files by extension."""
        (tmp_path / "a.py").write_text("#")
        (tmp_path / "b.py").write_text("#")
        (tmp_path / "c.js").write_text("//")

        index = build_repo_index(tmp_path)

        assert index.file_count_by_ext.get(".py", 0) == 2
        assert index.file_count_by_ext.get(".js", 0) == 1

    def test_finds_largest_files(self, tmp_path):
        """Should identify largest files."""
        (tmp_path / "small.py").write_text("# small")
        (tmp_path / "large.py").write_text("# " + "line\n" * 100)

        index = build_repo_index(tmp_path)

        assert len(index.largest_files) > 0
        # Large file should be first
        assert index.largest_files[0][0] == "large.py"

    def test_detects_test_files(self, tmp_path):
        """Should detect test files."""
        (tmp_path / "test_main.py").write_text("#")
        (tmp_path / "main.py").write_text("#")

        index = build_repo_index(tmp_path)

        assert "test_main.py" in index.test_files


class TestSaveLoadIndex:
    """Tests for save/load index functions."""

    def test_save_and_load(self, tmp_path):
        """Should save and load index correctly."""
        (tmp_path / "main.py").write_text("# code")

        original = build_repo_index(tmp_path)
        save_index(original, tmp_path)

        loaded = load_index(tmp_path)

        assert loaded is not None
        assert loaded.root == original.root
        assert loaded.total_files == original.total_files

    def test_load_missing_returns_none(self, tmp_path):
        """Should return None for missing index."""
        result = load_index(tmp_path)
        assert result is None


class TestGetOrBuildIndex:
    """Tests for get_or_build_index function."""

    def test_builds_when_missing(self, tmp_path):
        """Should build when no cache exists."""
        (tmp_path / "main.py").write_text("#")

        index = get_or_build_index(tmp_path)

        assert index is not None
        assert index.total_files >= 1

    def test_uses_cache_when_fresh(self, tmp_path):
        """Should use cache when fresh."""
        (tmp_path / "main.py").write_text("#")

        # Build and save
        index1 = get_or_build_index(tmp_path)
        time1 = index1.generated_at

        # Should return cached
        index2 = get_or_build_index(tmp_path)

        assert index2.generated_at == time1


class TestGetIndexSummary:
    """Tests for get_index_summary function."""

    def test_summary_format(self, tmp_path):
        """Should generate readable summary."""
        (tmp_path / "main.py").write_text("# code\n" * 50)

        index = build_repo_index(tmp_path)
        summary = get_index_summary(index)

        assert "Repository:" in summary
        assert "Total files:" in summary
        assert ".py" in summary
