"""
Tests for the doctor command and health checks.
Updated for v1.7.0 doctor module.
"""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from roura_agent.tools.doctor import (
    CheckStatus,
    CheckResult,
    check_os_version,
    check_python_version,
    check_install_path,
    check_config_paths,
    check_workspace_permissions,
    check_git_available,
    check_git_repo,
    check_ollama_reachable,
    check_environment_variables,
    check_network_connectivity,
    run_all_checks,
    format_results,
    has_critical_failures,
    create_support_bundle,
    get_config_path,
    get_cache_path,
    get_data_path,
)


class TestCheckOsVersion:
    """Tests for OS version check."""

    def test_os_version_returns_result(self):
        """Should return a valid CheckResult."""
        result = check_os_version()
        assert isinstance(result, CheckResult)
        assert result.name == "OS version"
        # Should pass on any supported platform
        assert result.status in (CheckStatus.PASS, CheckStatus.WARN)


class TestCheckPythonVersion:
    """Tests for Python version check."""

    def test_python_version_passes(self):
        """Current Python should pass (we require 3.9+)."""
        result = check_python_version()
        assert result.status == CheckStatus.PASS
        assert "3.9" in result.message or "3.1" in result.message  # 3.9+ or 3.10+


class TestCheckInstallPath:
    """Tests for install path check."""

    def test_install_path_returns_result(self):
        """Should detect installation method."""
        result = check_install_path()
        assert isinstance(result, CheckResult)
        assert result.name == "Install path"
        assert result.status == CheckStatus.PASS


class TestCheckConfigPaths:
    """Tests for config paths check."""

    def test_config_paths_returns_result(self):
        """Should return path information."""
        result = check_config_paths()
        assert isinstance(result, CheckResult)
        assert result.name == "Data paths"
        assert result.status == CheckStatus.PASS
        assert "config:" in result.details


class TestCheckWorkspacePermissions:
    """Tests for workspace permissions check."""

    def test_workspace_permissions_passes(self):
        """Current directory should be readable/writable in tests."""
        result = check_workspace_permissions()
        assert result.status == CheckStatus.PASS
        assert "Read/write OK" in result.message


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
        mock_response.json.return_value = {"models": [{"name": "model1"}, {"name": "model2"}]}
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_ollama_reachable()
        assert result.status == CheckStatus.PASS
        assert "2 models" in result.message

    @patch("httpx.Client")
    def test_ollama_not_reachable(self, mock_client_class, monkeypatch):
        """Should warn when Ollama is not reachable."""
        import httpx
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_ollama_reachable()
        assert result.status == CheckStatus.WARN
        assert "Cannot connect" in result.message


class TestCheckEnvironmentVariables:
    """Tests for environment variable check."""

    def test_env_vars_returns_result(self):
        """Should return environment variable status."""
        result = check_environment_variables()
        assert isinstance(result, CheckResult)
        assert result.name == "Environment"
        assert result.status == CheckStatus.PASS

    def test_env_vars_redacts_secrets(self, monkeypatch):
        """Should redact API keys and tokens."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789")
        result = check_environment_variables()
        if result.details:
            assert "sk-test" not in result.details
            assert "***" in result.details


class TestCheckNetworkConnectivity:
    """Tests for network connectivity check."""

    @patch("httpx.Client")
    def test_network_connected(self, mock_client_class):
        """Should pass when network is available."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_network_connectivity()
        assert result.status == CheckStatus.PASS

    @patch("httpx.Client")
    def test_network_disconnected(self, mock_client_class):
        """Should fail when network is unavailable."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = check_network_connectivity()
        assert result.status == CheckStatus.FAIL


class TestRunAllChecks:
    """Tests for running all checks."""

    def test_run_all_checks_returns_list(self):
        """Should return a list of CheckResult objects."""
        results = run_all_checks()
        assert isinstance(results, list)
        assert len(results) == 10  # Updated count for v1.7.0
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
        assert "✓" in output  # Pass icon
        assert "✗" in output  # Fail icon

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
            CheckResult("Workspace permissions", CheckStatus.PASS, "OK"),
            CheckResult("Other check", CheckStatus.WARN, "Warning"),
        ]
        assert has_critical_failures(results) is False

    def test_has_critical_failure(self):
        """Should return True when a critical check fails."""
        results = [
            CheckResult("Python version", CheckStatus.PASS, "OK"),
            CheckResult("Git available", CheckStatus.FAIL, "Not found"),
            CheckResult("Workspace permissions", CheckStatus.PASS, "OK"),
        ]
        assert has_critical_failures(results) is True

    def test_non_critical_failure_ok(self):
        """Should return False when only non-critical checks fail."""
        results = [
            CheckResult("Python version", CheckStatus.PASS, "OK"),
            CheckResult("Git available", CheckStatus.PASS, "OK"),
            CheckResult("Workspace permissions", CheckStatus.PASS, "OK"),
            CheckResult("Network", CheckStatus.FAIL, "Not connected"),
        ]
        assert has_critical_failures(results) is False


class TestPathHelpers:
    """Tests for path helper functions."""

    def test_get_config_path(self):
        """Should return config path under home directory."""
        path = get_config_path()
        assert ".config" in str(path)
        assert "roura-agent" in str(path)

    def test_get_cache_path(self):
        """Should return cache path under home directory."""
        path = get_cache_path()
        assert ".cache" in str(path)
        assert "roura-agent" in str(path)

    def test_get_data_path(self):
        """Should return data path under home directory."""
        path = get_data_path()
        assert ".local" in str(path)
        assert "roura-agent" in str(path)


class TestCreateSupportBundle:
    """Tests for support bundle creation."""

    def test_create_support_bundle(self, tmp_path):
        """Should create a ZIP file with diagnostics."""
        output_path = tmp_path / "test-bundle.zip"
        result = create_support_bundle(output_path)

        assert result == output_path
        assert output_path.exists()

        # Verify ZIP contents
        import zipfile
        with zipfile.ZipFile(output_path, 'r') as zf:
            names = zf.namelist()
            assert "diagnostics.json" in names
            assert "report.txt" in names

            # Verify diagnostics.json is valid JSON
            with zf.open("diagnostics.json") as f:
                data = json.load(f)
                assert "version" in data
                assert "platform" in data
                assert "checks" in data
