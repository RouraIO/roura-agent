"""
Pytest fixtures for Roura Agent tests.
"""
from __future__ import annotations

import os
import pytest
from typer.testing import CliRunner

from roura_agent.cli import app
from roura_agent.safety import reset_session_state, SafetyMode


@pytest.fixture(autouse=True)
def reset_safety_state():
    """Reset safety state before each test to prevent cross-test pollution."""
    reset_session_state()
    SafetyMode.reset()
    yield
    # Also reset after test completes
    reset_session_state()
    SafetyMode.reset()


@pytest.fixture
def cli_runner():
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli_app():
    """The Typer app instance."""
    return app


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")


@pytest.fixture
def clean_env(monkeypatch):
    """Clear Ollama environment variables."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
