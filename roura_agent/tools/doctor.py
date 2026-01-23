"""
Roura Agent Doctor - System health diagnostics.
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx


class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None


def check_python_version() -> CheckResult:
    """Check Python version >= 3.9."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version >= (3, 9):
        return CheckResult(
            name="Python version",
            status=CheckStatus.PASS,
            message=f"{version_str} (>= 3.9 required)",
        )
    else:
        return CheckResult(
            name="Python version",
            status=CheckStatus.FAIL,
            message=f"{version_str} (>= 3.9 required)",
            details="Please upgrade Python to 3.9 or later.",
        )


def check_git_available() -> CheckResult:
    """Check if git CLI is installed."""
    git_path = shutil.which("git")

    if not git_path:
        return CheckResult(
            name="Git available",
            status=CheckStatus.FAIL,
            message="git not found in PATH",
            details="Install git: https://git-scm.com/downloads",
        )

    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip()
        return CheckResult(
            name="Git available",
            status=CheckStatus.PASS,
            message=version,
        )
    except Exception as e:
        return CheckResult(
            name="Git available",
            status=CheckStatus.FAIL,
            message=f"git check failed: {e}",
        )


def check_git_repo() -> CheckResult:
    """Check if current directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            repo_root = result.stdout.strip()
            return CheckResult(
                name="Git repository",
                status=CheckStatus.PASS,
                message=repo_root,
            )
        else:
            return CheckResult(
                name="Git repository",
                status=CheckStatus.WARN,
                message="Not inside a git repository",
                details="Some features require a git repository.",
            )
    except Exception as e:
        return CheckResult(
            name="Git repository",
            status=CheckStatus.FAIL,
            message=f"git check failed: {e}",
        )


def check_ollama_reachable() -> CheckResult:
    """Check if Ollama server is reachable."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            return CheckResult(
                name="Ollama reachable",
                status=CheckStatus.PASS,
                message=base_url,
            )
    except httpx.ConnectError:
        return CheckResult(
            name="Ollama reachable",
            status=CheckStatus.FAIL,
            message=f"Cannot connect to {base_url}",
            details="Ensure Ollama is running and OLLAMA_BASE_URL is correct.",
        )
    except httpx.HTTPStatusError as e:
        return CheckResult(
            name="Ollama reachable",
            status=CheckStatus.FAIL,
            message=f"HTTP error: {e.response.status_code}",
            details=str(e),
        )
    except Exception as e:
        return CheckResult(
            name="Ollama reachable",
            status=CheckStatus.FAIL,
            message=f"Error: {e}",
        )


def check_ollama_model() -> CheckResult:
    """Check if configured Ollama model exists."""
    model = os.getenv("OLLAMA_MODEL", "").strip()

    if not model:
        return CheckResult(
            name="Ollama model",
            status=CheckStatus.WARN,
            message="OLLAMA_MODEL not set",
            details="Set OLLAMA_MODEL environment variable.",
        )

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]

            if model in models:
                return CheckResult(
                    name="Ollama model",
                    status=CheckStatus.PASS,
                    message=model,
                )
            else:
                return CheckResult(
                    name="Ollama model",
                    status=CheckStatus.FAIL,
                    message=f"Model '{model}' not found",
                    details=f"Available models: {', '.join(models) or 'none'}",
                )
    except Exception as e:
        return CheckResult(
            name="Ollama model",
            status=CheckStatus.FAIL,
            message=f"Cannot check model: {e}",
        )


def check_config_directory() -> CheckResult:
    """Check if .roura/ config directory exists."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            repo_root = Path(result.stdout.strip())
            config_dir = repo_root / ".roura"
        else:
            config_dir = Path.cwd() / ".roura"
    except Exception:
        config_dir = Path.cwd() / ".roura"

    if config_dir.exists():
        return CheckResult(
            name="Config directory",
            status=CheckStatus.PASS,
            message=str(config_dir),
        )
    else:
        return CheckResult(
            name="Config directory",
            status=CheckStatus.WARN,
            message=f"{config_dir} not found",
            details="Run 'roura-agent init' to create configuration.",
        )


def run_all_checks() -> list[CheckResult]:
    """Run all diagnostic checks."""
    return [
        check_python_version(),
        check_git_available(),
        check_git_repo(),
        check_ollama_reachable(),
        check_ollama_model(),
        check_config_directory(),
    ]


def format_results(results: list[CheckResult], use_json: bool = False) -> str:
    """Format check results for display."""
    if use_json:
        import json
        return json.dumps(
            [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                }
                for r in results
            ],
            indent=2,
        )

    lines = ["Roura Agent Doctor", "=" * 18, ""]

    status_icons = {
        CheckStatus.PASS: "[ok]",
        CheckStatus.FAIL: "[FAIL]",
        CheckStatus.WARN: "[warn]",
    }

    for result in results:
        icon = status_icons[result.status]
        lines.append(f"{icon} {result.name}: {result.message}")
        if result.details and result.status != CheckStatus.PASS:
            lines.append(f"      {result.details}")

    passed = sum(1 for r in results if r.status == CheckStatus.PASS)
    failed = sum(1 for r in results if r.status == CheckStatus.FAIL)
    warned = sum(1 for r in results if r.status == CheckStatus.WARN)
    total = len(results)

    lines.append("")
    lines.append(f"{passed}/{total} checks passed", )
    if failed:
        lines.append(f"{failed} failed")
    if warned:
        lines.append(f"{warned} warnings")

    return "\n".join(lines)


def has_critical_failures(results: list[CheckResult]) -> bool:
    """Check if any critical checks failed."""
    critical_checks = {"Python version", "Git available", "Ollama reachable"}
    for result in results:
        if result.name in critical_checks and result.status == CheckStatus.FAIL:
            return True
    return False
