"""
Tests for CLI commands.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from roura_agent.cli import app


runner = CliRunner()


class TestCLIHelp:
    """Tests for CLI help and basic structure."""

    def test_help_shows_all_commands(self):
        """Should list all available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output
        assert "ping" in result.output
        assert "tools" in result.output
        assert "config" in result.output
        assert "fs" in result.output
        assert "git" in result.output
        assert "shell" in result.output

    def test_no_args_launches_agent(self, monkeypatch):
        """Should launch agent when invoked without arguments."""
        # Set required env vars
        monkeypatch.setenv("OLLAMA_MODEL", "test-model")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        # Mock the agent to avoid actually running it
        with patch("roura_agent.agent.loop.AgentLoop") as mock_agent:
            mock_instance = MagicMock()
            mock_agent.return_value = mock_instance

            result = runner.invoke(app, [], input="exit\n")
            # Should show logo
            assert "ROURA" in result.output or "roura" in result.output.lower()


class TestDoctorCommand:
    """Tests for the doctor command."""

    @patch("roura_agent.cli.run_all_checks")
    @patch("roura_agent.cli.has_critical_failures")
    def test_doctor_runs_checks(self, mock_has_failures, mock_run_checks):
        """Should run all health checks."""
        from roura_agent.tools.doctor import CheckResult, CheckStatus

        mock_run_checks.return_value = [
            CheckResult("Test", CheckStatus.PASS, "OK"),
        ]
        mock_has_failures.return_value = False

        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        mock_run_checks.assert_called_once()

    @patch("roura_agent.cli.run_all_checks")
    @patch("roura_agent.cli.has_critical_failures")
    def test_doctor_exits_1_on_critical_failure(self, mock_has_failures, mock_run_checks):
        """Should exit with code 1 on critical failure."""
        from roura_agent.tools.doctor import CheckResult, CheckStatus

        mock_run_checks.return_value = [
            CheckResult("Git available", CheckStatus.FAIL, "Not found"),
        ]
        mock_has_failures.return_value = True

        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1

    @patch("roura_agent.cli.run_all_checks")
    @patch("roura_agent.cli.has_critical_failures")
    def test_doctor_json_output(self, mock_has_failures, mock_run_checks):
        """Should output JSON when --json flag is used."""
        from roura_agent.tools.doctor import CheckResult, CheckStatus

        mock_run_checks.return_value = [
            CheckResult("Test", CheckStatus.PASS, "OK"),
        ]
        mock_has_failures.return_value = False

        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        assert "[" in result.output  # JSON array start


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_shows_env_vars(self, monkeypatch):
        """Should display environment variable values."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://test:1234")
        monkeypatch.setenv("OLLAMA_MODEL", "test-model")

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "OLLAMA_BASE_URL" in result.output
        assert "OLLAMA_MODEL" in result.output
        assert "test:1234" in result.output
        assert "test-model" in result.output

    def test_config_shows_not_set_when_empty(self, monkeypatch, tmp_path):
        """Should show 'not set' when env vars and config file not set."""
        # Clear env vars
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)

        # Mock config file path to a non-existent location
        from roura_agent import config
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "nonexistent" / "config.json")

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "not set" in result.output.lower() or "Configuration" in result.output


class TestPingCommand:
    """Tests for the ping command."""

    @patch("roura_agent.cli.list_models")
    @patch("roura_agent.cli.get_base_url")
    def test_ping_lists_models(self, mock_get_url, mock_list_models):
        """Should list available Ollama models."""
        mock_get_url.return_value = "http://localhost:11434"
        mock_list_models.return_value = ["model1", "model2"]

        result = runner.invoke(app, ["ping"])
        assert result.exit_code == 0
        assert "model1" in result.output
        assert "model2" in result.output

    @patch("roura_agent.cli.list_models")
    @patch("roura_agent.cli.get_base_url")
    def test_ping_handles_empty_models(self, mock_get_url, mock_list_models):
        """Should handle when no models are available."""
        mock_get_url.return_value = "http://localhost:11434"
        mock_list_models.return_value = []

        result = runner.invoke(app, ["ping"])
        assert result.exit_code == 0


class TestToolsCommand:
    """Tests for the tools command."""

    def test_tools_lists_all_tools(self):
        """Should list all registered tools."""
        result = runner.invoke(app, ["tools"])
        assert result.exit_code == 0
        assert "fs.read" in result.output
        assert "fs.write" in result.output
        assert "git.status" in result.output
        assert "shell.exec" in result.output


class TestLegacyCommands:
    """Tests for deprecated/legacy commands."""

    def test_where_still_works(self, monkeypatch):
        """The where command should still work (redirects to config)."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://test:1234")

        result = runner.invoke(app, ["where"])
        assert result.exit_code == 0
        # Should show config table
        assert "OLLAMA_BASE_URL" in result.output
