"""
Tests for git tools.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from roura_agent.cli import app
from roura_agent.tools.git import (
    GitStatusTool,
    GitDiffTool,
    GitLogTool,
    git_status,
    git_diff,
    git_log,
    get_status,
    get_diff,
    get_log,
    run_git_command,
    get_repo_root,
)
from roura_agent.tools.base import RiskLevel


runner = CliRunner()


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        capture_output=True,
    )

    # Create initial commit
    (tmp_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        capture_output=True,
    )

    return tmp_path


class TestRunGitCommand:
    """Tests for the run_git_command helper."""

    def test_successful_command(self, temp_git_repo):
        """Should return success and output for valid command."""
        success, stdout, stderr = run_git_command(["status"], cwd=str(temp_git_repo))
        assert success is True
        assert stderr == ""

    def test_failed_command(self, tmp_path):
        """Should return failure for invalid repo."""
        success, stdout, stderr = run_git_command(["status"], cwd=str(tmp_path))
        assert success is False

    @patch("subprocess.run")
    def test_timeout_handling(self, mock_run):
        """Should handle timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        success, stdout, stderr = run_git_command(["status"])
        assert success is False
        assert "timed out" in stderr.lower()


class TestGetRepoRoot:
    """Tests for get_repo_root helper."""

    def test_finds_repo_root(self, temp_git_repo):
        """Should find the repository root."""
        root = get_repo_root(cwd=str(temp_git_repo))
        assert root is not None
        assert Path(root).exists()

    def test_returns_none_for_non_repo(self, tmp_path):
        """Should return None for non-repo directory."""
        root = get_repo_root(cwd=str(tmp_path))
        assert root is None


class TestGitStatusTool:
    """Tests for the git.status tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert git_status.name == "git.status"
        assert git_status.risk_level == RiskLevel.SAFE
        assert git_status.requires_approval is False

    def test_status_clean_repo(self, temp_git_repo):
        """Should report clean status for clean repo."""
        result = get_status(str(temp_git_repo))

        assert result.success is True
        assert result.output["clean"] is True
        assert result.output["branch"] == "main" or result.output["branch"] == "master"
        assert len(result.output["staged"]) == 0
        assert len(result.output["modified"]) == 0
        assert len(result.output["untracked"]) == 0

    def test_status_untracked_file(self, temp_git_repo):
        """Should detect untracked files."""
        (temp_git_repo / "new_file.txt").write_text("content")

        result = get_status(str(temp_git_repo))

        assert result.success is True
        assert result.output["clean"] is False
        assert "new_file.txt" in result.output["untracked"]

    def test_status_modified_file(self, temp_git_repo):
        """Should detect modified files."""
        (temp_git_repo / "README.md").write_text("Modified content\n")

        result = get_status(str(temp_git_repo))

        assert result.success is True
        assert result.output["clean"] is False
        assert "README.md" in result.output["modified"]

    def test_status_staged_file(self, temp_git_repo):
        """Should detect staged files."""
        (temp_git_repo / "README.md").write_text("Modified content\n")
        subprocess.run(["git", "add", "README.md"], cwd=temp_git_repo, capture_output=True)

        result = get_status(str(temp_git_repo))

        assert result.success is True
        assert result.output["clean"] is False
        assert len(result.output["staged"]) > 0

    def test_status_not_a_repo(self, tmp_path):
        """Should fail for non-repo directory."""
        result = get_status(str(tmp_path))

        assert result.success is False
        assert "not a git repository" in result.error.lower()


class TestGitDiffTool:
    """Tests for the git.diff tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert git_diff.name == "git.diff"
        assert git_diff.risk_level == RiskLevel.SAFE
        assert git_diff.requires_approval is False

    def test_diff_no_changes(self, temp_git_repo):
        """Should report no changes for clean repo."""
        result = get_diff(str(temp_git_repo))

        assert result.success is True
        assert result.output["has_changes"] is False

    def test_diff_unstaged_changes(self, temp_git_repo):
        """Should show unstaged changes."""
        (temp_git_repo / "README.md").write_text("Modified content\n")

        result = get_diff(str(temp_git_repo))

        assert result.success is True
        assert result.output["has_changes"] is True
        assert "-# Test Repo" in result.output["diff"]
        assert "+Modified content" in result.output["diff"]

    def test_diff_staged_changes(self, temp_git_repo):
        """Should show staged changes with staged=True."""
        (temp_git_repo / "README.md").write_text("Modified content\n")
        subprocess.run(["git", "add", "README.md"], cwd=temp_git_repo, capture_output=True)

        result = get_diff(str(temp_git_repo), staged=True)

        assert result.success is True
        assert result.output["has_changes"] is True
        assert result.output["staged"] is True

    def test_diff_not_a_repo(self, tmp_path):
        """Should fail for non-repo directory."""
        result = get_diff(str(tmp_path))

        assert result.success is False
        assert "not a git repository" in result.error.lower()


class TestGitLogTool:
    """Tests for the git.log tool."""

    def test_tool_properties(self):
        """Tool should have correct properties."""
        assert git_log.name == "git.log"
        assert git_log.risk_level == RiskLevel.SAFE
        assert git_log.requires_approval is False

    def test_log_shows_commits(self, temp_git_repo):
        """Should show commit history."""
        result = get_log(str(temp_git_repo))

        assert result.success is True
        assert result.output["count"] >= 1
        assert len(result.output["commits"]) >= 1
        assert "Initial commit" in result.output["commits"][0]["subject"]

    def test_log_oneline(self, temp_git_repo):
        """Should work with oneline format."""
        result = get_log(str(temp_git_repo), oneline=True)

        assert result.success is True
        assert len(result.output["commits"]) >= 1
        assert "hash" in result.output["commits"][0]
        assert "message" in result.output["commits"][0]

    def test_log_count_limit(self, temp_git_repo):
        """Should respect count limit."""
        # Create additional commits
        for i in range(5):
            (temp_git_repo / f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=temp_git_repo,
                capture_output=True,
            )

        result = get_log(str(temp_git_repo), count=3)

        assert result.success is True
        assert result.output["count"] == 3

    def test_log_not_a_repo(self, tmp_path):
        """Should fail for non-repo directory."""
        result = get_log(str(tmp_path))

        assert result.success is False
        assert "not a git repository" in result.error.lower()


class TestGitStatusCLI:
    """Tests for the git status CLI command."""

    def test_status_command(self, temp_git_repo):
        """Should show status via CLI."""
        result = runner.invoke(app, ["git", "status", str(temp_git_repo)])

        assert result.exit_code == 0
        assert "Repository:" in result.output
        assert "Branch:" in result.output

    def test_status_json_output(self, temp_git_repo):
        """Should output JSON with --json flag."""
        result = runner.invoke(app, ["git", "status", str(temp_git_repo), "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "branch" in parsed
        assert "clean" in parsed

    def test_status_shows_untracked(self, temp_git_repo):
        """Should show untracked files."""
        (temp_git_repo / "new.txt").write_text("content")

        result = runner.invoke(app, ["git", "status", str(temp_git_repo)])

        assert result.exit_code == 0
        assert "Untracked" in result.output
        assert "new.txt" in result.output


class TestGitDiffCLI:
    """Tests for the git diff CLI command."""

    def test_diff_command(self, temp_git_repo):
        """Should show diff via CLI."""
        (temp_git_repo / "README.md").write_text("Modified\n")

        result = runner.invoke(app, ["git", "diff", str(temp_git_repo)])

        assert result.exit_code == 0
        assert "Modified" in result.output or "-# Test Repo" in result.output

    def test_diff_no_changes(self, temp_git_repo):
        """Should report no changes."""
        result = runner.invoke(app, ["git", "diff", str(temp_git_repo)])

        assert result.exit_code == 0
        assert "No" in result.output and "changes" in result.output

    def test_diff_staged_flag(self, temp_git_repo):
        """Should show staged changes with --staged."""
        (temp_git_repo / "README.md").write_text("Modified\n")
        subprocess.run(["git", "add", "README.md"], cwd=temp_git_repo, capture_output=True)

        result = runner.invoke(app, ["git", "diff", str(temp_git_repo), "--staged"])

        assert result.exit_code == 0

    def test_diff_json_output(self, temp_git_repo):
        """Should output JSON with --json flag."""
        result = runner.invoke(app, ["git", "diff", str(temp_git_repo), "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "has_changes" in parsed


class TestGitLogCLI:
    """Tests for the git log CLI command."""

    def test_log_command(self, temp_git_repo):
        """Should show log via CLI."""
        result = runner.invoke(app, ["git", "log", str(temp_git_repo)])

        assert result.exit_code == 0
        assert "Initial commit" in result.output

    def test_log_oneline_flag(self, temp_git_repo):
        """Should show oneline format with --oneline."""
        result = runner.invoke(app, ["git", "log", str(temp_git_repo), "--oneline"])

        assert result.exit_code == 0
        # Should be more compact
        lines = [l for l in result.output.splitlines() if l.strip()]
        assert len(lines) <= 5  # Should be compact

    def test_log_count_flag(self, temp_git_repo):
        """Should respect --count flag."""
        result = runner.invoke(app, ["git", "log", str(temp_git_repo), "--count", "1"])

        assert result.exit_code == 0

    def test_log_json_output(self, temp_git_repo):
        """Should output JSON with --json flag."""
        result = runner.invoke(app, ["git", "log", str(temp_git_repo), "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "commits" in parsed
        assert len(parsed["commits"]) >= 1
