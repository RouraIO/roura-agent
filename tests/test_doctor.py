"""
Tests for the doctor command and health checks.
"""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from roura_agent.tools.doctor import (
    CheckStatus,
    CheckResult,
    check_python_version,
    check_git_available,
    check_git_repo,
    check_ollama_reachable,
    check_ollama_model,
    check_config_directory,
    run_all_checks,
    format_results,
    has_critical_failures,
)


class TestCheckPythonVersion:
    """Tests for Python version check."""

    def test_python_version_passes(self):
        """Current Python should pass (we require 3.9+)."""
        result = check_python_version()
        assert result.status == CheckStatus.PASS
        assert "3.9" in result.message or "3.1" in result.message  # 3.9+ or 3.10+


class TestCheckGitAvailable:
    """Tests for git availability check."""

    def test_git_available_when_installed(self):
        """Git should be available in test environment."""
        result = check_git_available()
        assert result.status == CheckStatus.PASS
        assert "git version" in result.message

    @patch("shutil.which")
    def test_git_not_available(self, mock_which):
        """Should fail when git is not in PATH."""
        mock_which.return_value = None
        result = check_git_available()
        assert result.status == CheckStatus.FAIL
        assert "not found" in result.message


class TestCheckGitRepo:
    """Tests for git repository check."""

    def test_git_repo_detected(self):
        """Should detect we're in a git repo (test runs from repo root)."""
        result = check_git_repo()
        # Could be PASS or WARN depending on where tests run
        assert result.status in (CheckStatus.PASS, CheckStatus.WARN)

    @patch("subprocess.run")
    def test_git_repo_not_found(self, mock_run):
        """Should warn when not in a git repo."""
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="")
        result = check_git_repo()
        assert result.status == CheckStatus.WARN


class TestCheckOllamaReachable:
    """Tests for Ollama connectivity check."""

    @patch("httpx.Client")
    def test_ollama_reachable(self, mock_client_class, monkeypatch):
        """Should pass when Ollama responds."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_ollama_reachable()
        assert result.status == CheckStatus.PASS

    @patch("httpx.Client")
    def test_ollama_not_reachable(self, mock_client_class, monkeypatch):
        """Should fail when Ollama is not reachable."""
        import httpx
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_ollama_reachable()
        assert result.status == CheckStatus.FAIL


class TestCheckOllamaModel:
    """Tests for Ollama model check."""

    def test_model_not_set(self, monkeypatch):
        """Should warn when OLLAMA_MODEL is not set."""
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        result = check_ollama_model()
        assert result.status == CheckStatus.WARN
        assert "not set" in result.message

    @patch("httpx.Client")
    def test_model_found(self, mock_client_class, monkeypatch):
        """Should pass when model exists."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "test-model")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"models": [{"name": "test-model"}]}
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_ollama_model()
        assert result.status == CheckStatus.PASS

    @patch("httpx.Client")
    def test_model_not_found(self, mock_client_class, monkeypatch):
        """Should fail when model doesn't exist."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "nonexistent-model")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"models": [{"name": "other-model"}]}
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_ollama_model()
        assert result.status == CheckStatus.FAIL


class TestCheckConfigDirectory:
    """Tests for config directory check."""

    def test_config_directory_not_found(self):
        """Should warn when .roura/ doesn't exist (expected in fresh repo)."""
        result = check_config_directory()
        # Will be WARN in test environment (no .roura/ yet)
        assert result.status in (CheckStatus.PASS, CheckStatus.WARN)


class TestRunAllChecks:
    """Tests for running all checks."""

    def test_run_all_checks_returns_list(self):
        """Should return a list of CheckResult objects."""
        results = run_all_checks()
        assert isinstance(results, list)
        assert len(results) == 6
        assert all(isinstance(r, CheckResult) for r in results)


class TestFormatResults:
    """Tests for result formatting."""

    def test_format_results_text(self):
        """Should format results as human-readable text."""
        results = [
            CheckResult("Test 1", CheckStatus.PASS, "OK"),
            CheckResult("Test 2", CheckStatus.FAIL, "Failed", "Details here"),
        ]
        output = format_results(results, use_json=False)
        assert "Roura Agent Doctor" in output
        assert "Test 1" in output
        assert "Test 2" in output
        assert "[ok]" in output
        assert "[FAIL]" in output

    def test_format_results_json(self):
        """Should format results as valid JSON."""
        results = [
            CheckResult("Test 1", CheckStatus.PASS, "OK"),
            CheckResult("Test 2", CheckStatus.WARN, "Warning", "Details"),
        ]
        output = format_results(results, use_json=True)
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["status"] == "pass"
        assert parsed[1]["status"] == "warn"


class TestHasCriticalFailures:
    """Tests for critical failure detection."""

    def test_no_critical_failures(self):
        """Should return False when no critical checks fail."""
        results = [
            CheckResult("Python version", CheckStatus.PASS, "OK"),
            CheckResult("Git available", CheckStatus.PASS, "OK"),
            CheckResult("Ollama reachable", CheckStatus.PASS, "OK"),
            CheckResult("Config directory", CheckStatus.WARN, "Not found"),
        ]
        assert has_critical_failures(results) is False

    def test_has_critical_failure(self):
        """Should return True when a critical check fails."""
        results = [
            CheckResult("Python version", CheckStatus.PASS, "OK"),
            CheckResult("Git available", CheckStatus.FAIL, "Not found"),
            CheckResult("Ollama reachable", CheckStatus.PASS, "OK"),
        ]
        assert has_critical_failures(results) is True

    def test_non_critical_failure_ok(self):
        """Should return False when only non-critical checks fail."""
        results = [
            CheckResult("Python version", CheckStatus.PASS, "OK"),
            CheckResult("Git available", CheckStatus.PASS, "OK"),
            CheckResult("Ollama reachable", CheckStatus.PASS, "OK"),
            CheckResult("Config directory", CheckStatus.FAIL, "Not found"),
        ]
        assert has_critical_failures(results) is False
