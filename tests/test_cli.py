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
        assert "where" in result.output
        assert "chat-once" in result.output
        assert "repl" in result.output

    def test_no_args_shows_help(self):
        """Should show help when invoked without arguments."""
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Usage:" in result.output


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


class TestWhereCommand:
    """Tests for the where command."""

    def test_where_shows_env_vars(self, monkeypatch):
        """Should display environment variable values."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://test:1234")
        monkeypatch.setenv("OLLAMA_MODEL", "test-model")

        result = runner.invoke(app, ["where"])
        assert result.exit_code == 0
        assert "OLLAMA_BASE_URL" in result.output
        assert "OLLAMA_MODEL" in result.output

    def test_where_shows_empty_when_not_set(self, monkeypatch):
        """Should show empty values when env vars not set."""
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)

        result = runner.invoke(app, ["where"])
        assert result.exit_code == 0
        assert "OLLAMA_BASE_URL=" in result.output


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


class TestChatOnceCommand:
    """Tests for the chat-once command."""

    @patch("roura_agent.cli.generate")
    def test_chat_once_sends_prompt(self, mock_generate):
        """Should send prompt to LLM and display response."""
        mock_generate.return_value = "Hello, world!"

        result = runner.invoke(app, ["chat-once", "Say hello"])
        assert result.exit_code == 0
        assert "Hello, world!" in result.output
        mock_generate.assert_called_once_with("Say hello")

    def test_chat_once_requires_prompt(self):
        """Should require a prompt argument."""
        result = runner.invoke(app, ["chat-once"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output
