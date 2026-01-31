"""
Roura Agent Doctor - System health diagnostics.

Enhanced for v1.7.0 with:
- OS/architecture detection
- Path diagnostics
- Permissions checks
- Environment summary
- Support bundle export

© Roura.io
"""
from __future__ import annotations

import io
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
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


# ===== SYSTEM CHECKS =====

def check_os_version() -> CheckResult:
    """Check macOS version and architecture."""
    system = platform.system()
    release = platform.release()
    machine = platform.machine()
    version = platform.mac_ver()[0] if system == "Darwin" else platform.version()

    info = f"{system} {version} ({machine})"

    if system == "Darwin":
        # Check macOS version
        try:
            major_version = int(version.split(".")[0])
            if major_version >= 15:
                return CheckResult(
                    name="OS version",
                    status=CheckStatus.PASS,
                    message=info,
                )
            elif major_version >= 12:
                return CheckResult(
                    name="OS version",
                    status=CheckStatus.WARN,
                    message=info,
                    details="macOS 15+ recommended for best experience",
                )
            else:
                return CheckResult(
                    name="OS version",
                    status=CheckStatus.WARN,
                    message=info,
                    details="macOS 12+ recommended",
                )
        except (ValueError, IndexError):
            pass

    return CheckResult(
        name="OS version",
        status=CheckStatus.PASS,
        message=info,
    )


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


def check_install_path() -> CheckResult:
    """Check installation path and method."""
    exe_path = sys.executable
    script_path = Path(__file__).resolve()

    # Detect install method
    install_method = "unknown"
    if ".local/pipx" in str(script_path):
        install_method = "pipx"
    elif "/Applications/" in str(script_path):
        install_method = "app bundle"
    elif "homebrew" in str(script_path).lower() or "/opt/homebrew" in str(script_path):
        install_method = "homebrew"
    elif "site-packages" in str(script_path):
        install_method = "pip"
    elif ".venv" in str(script_path) or "venv" in str(script_path):
        install_method = "development (venv)"

    return CheckResult(
        name="Install path",
        status=CheckStatus.PASS,
        message=f"{install_method}",
        details=str(script_path.parent.parent),
    )


# ===== PATH CHECKS =====

def get_config_path() -> Path:
    """Get configuration directory path."""
    return Path.home() / ".config" / "roura-agent"


def get_cache_path() -> Path:
    """Get cache directory path."""
    return Path.home() / ".cache" / "roura-agent"


def get_data_path() -> Path:
    """Get local data directory path."""
    return Path.home() / ".local" / "share" / "roura-agent"


def check_config_paths() -> CheckResult:
    """Check config/cache/data directories."""
    config_path = get_config_path()
    cache_path = get_cache_path()
    data_path = get_data_path()

    paths_info = []
    all_ok = True

    for name, path in [("config", config_path), ("cache", cache_path), ("data", data_path)]:
        if path.exists():
            paths_info.append(f"{name}: {path}")
        else:
            paths_info.append(f"{name}: {path} (not created)")

    return CheckResult(
        name="Data paths",
        status=CheckStatus.PASS,
        message="Directories located",
        details="; ".join(paths_info),
    )


def check_workspace_permissions() -> CheckResult:
    """Check if current directory is writable."""
    cwd = Path.cwd()

    can_read = os.access(cwd, os.R_OK)
    can_write = os.access(cwd, os.W_OK)

    if can_read and can_write:
        return CheckResult(
            name="Workspace permissions",
            status=CheckStatus.PASS,
            message=f"Read/write OK: {cwd}",
        )
    elif can_read:
        return CheckResult(
            name="Workspace permissions",
            status=CheckStatus.WARN,
            message=f"Read-only: {cwd}",
            details="File modifications will fail in this directory.",
        )
    else:
        return CheckResult(
            name="Workspace permissions",
            status=CheckStatus.FAIL,
            message=f"No access: {cwd}",
            details="Cannot read or write to current directory.",
        )


# ===== GIT CHECKS =====

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


# ===== OLLAMA CHECKS =====

def check_ollama_reachable() -> CheckResult:
    """Check if Ollama server is reachable."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            model_count = len(data.get("models", []))
            return CheckResult(
                name="Ollama reachable",
                status=CheckStatus.PASS,
                message=f"{base_url} ({model_count} models)",
            )
    except httpx.ConnectError:
        return CheckResult(
            name="Ollama reachable",
            status=CheckStatus.WARN,
            message=f"Cannot connect to {base_url}",
            details="Ollama not running. Start with: ollama serve",
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
            status=CheckStatus.WARN,
            message=f"Error: {e}",
        )


# ===== ENVIRONMENT CHECKS =====

def check_environment_variables() -> CheckResult:
    """Check relevant environment variables (redact secrets)."""
    relevant_vars = [
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "JIRA_API_TOKEN",
        "ROURA_PROVIDER",
        "ROURA_SAFE_MODE",
    ]

    found = []
    secrets = []

    for var in relevant_vars:
        value = os.getenv(var)
        if value:
            if "KEY" in var or "TOKEN" in var or "SECRET" in var:
                # Redact secrets
                found.append(f"{var}=***{value[-4:]}")
                secrets.append(var)
            else:
                found.append(f"{var}={value}")

    if not found:
        return CheckResult(
            name="Environment",
            status=CheckStatus.PASS,
            message="No custom variables set (using defaults)",
        )

    return CheckResult(
        name="Environment",
        status=CheckStatus.PASS,
        message=f"{len(found)} variables configured",
        details="; ".join(found),
    )


# ===== NETWORK CHECKS =====

def check_network_connectivity() -> CheckResult:
    """Check basic network connectivity."""
    test_urls = [
        ("GitHub", "https://api.github.com"),
        ("OpenAI", "https://api.openai.com"),
    ]

    reachable = []
    unreachable = []

    for name, url in test_urls:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                reachable.append(name)
        except Exception:
            unreachable.append(name)

    if not unreachable:
        return CheckResult(
            name="Network",
            status=CheckStatus.PASS,
            message=f"Connected ({', '.join(reachable)})",
        )
    elif reachable:
        return CheckResult(
            name="Network",
            status=CheckStatus.WARN,
            message=f"Partial ({', '.join(reachable)})",
            details=f"Unreachable: {', '.join(unreachable)}",
        )
    else:
        return CheckResult(
            name="Network",
            status=CheckStatus.FAIL,
            message="No connectivity",
            details="Check your internet connection.",
        )


# ===== RUN ALL CHECKS =====

def run_all_checks() -> list[CheckResult]:
    """Run all diagnostic checks."""
    return [
        check_os_version(),
        check_python_version(),
        check_install_path(),
        check_config_paths(),
        check_workspace_permissions(),
        check_git_available(),
        check_git_repo(),
        check_ollama_reachable(),
        check_environment_variables(),
        check_network_connectivity(),
    ]


# ===== FORMATTING =====

def format_results(results: list[CheckResult], use_json: bool = False) -> str:
    """Format check results for display."""
    if use_json:
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

    from ..constants import VERSION

    lines = [f"Roura Agent Doctor v{VERSION}", "=" * 30, ""]

    status_icons = {
        CheckStatus.PASS: "✓",
        CheckStatus.FAIL: "✗",
        CheckStatus.WARN: "!",
    }

    for result in results:
        icon = status_icons[result.status]
        status_color = {
            CheckStatus.PASS: "",
            CheckStatus.FAIL: "",
            CheckStatus.WARN: "",
        }[result.status]
        lines.append(f"  {icon} {result.name}: {result.message}")
        if result.details and result.status != CheckStatus.PASS:
            lines.append(f"      {result.details}")

    passed = sum(1 for r in results if r.status == CheckStatus.PASS)
    failed = sum(1 for r in results if r.status == CheckStatus.FAIL)
    warned = sum(1 for r in results if r.status == CheckStatus.WARN)
    total = len(results)

    lines.append("")
    summary = f"{passed}/{total} checks passed"
    if failed:
        summary += f", {failed} failed"
    if warned:
        summary += f", {warned} warnings"
    lines.append(summary)

    return "\n".join(lines)


def has_critical_failures(results: list[CheckResult]) -> bool:
    """Check if any critical checks failed."""
    critical_checks = {"Python version", "Git available", "Workspace permissions"}
    for result in results:
        if result.name in critical_checks and result.status == CheckStatus.FAIL:
            return True
    return False


# ===== SUPPORT BUNDLE =====

def create_support_bundle(output_path: Optional[Path] = None) -> Path:
    """
    Create a support bundle ZIP containing diagnostic information.

    Returns the path to the created ZIP file.
    """
    from ..constants import VERSION

    # Default output path
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path.cwd() / f"roura-agent-support-{timestamp}.zip"

    # Collect diagnostic data
    results = run_all_checks()

    # Build bundle contents
    bundle_data = {
        "version": VERSION,
        "timestamp": datetime.now().isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "checks": [
            {
                "name": r.name,
                "status": r.status.value,
                "message": r.message,
                "details": r.details,
            }
            for r in results
        ],
        "environment": {
            k: ("***" + v[-4:] if ("KEY" in k or "TOKEN" in k or "SECRET" in k) else v)
            for k, v in os.environ.items()
            if k.startswith(("ROURA_", "OLLAMA_", "OPENAI_", "ANTHROPIC_", "GITHUB_", "JIRA_"))
        },
        "paths": {
            "config": str(get_config_path()),
            "cache": str(get_cache_path()),
            "data": str(get_data_path()),
            "cwd": str(Path.cwd()),
            "executable": sys.executable,
        },
    }

    # Create ZIP
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add diagnostic JSON
        zf.writestr("diagnostics.json", json.dumps(bundle_data, indent=2))

        # Add formatted report
        zf.writestr("report.txt", format_results(results))

        # Add config files (if they exist and aren't sensitive)
        config_path = get_config_path()
        if config_path.exists():
            config_file = config_path / "config.json"
            if config_file.exists():
                try:
                    # Read and redact sensitive fields
                    with open(config_file) as f:
                        config_data = json.load(f)
                    # Redact any keys containing sensitive words
                    def redact_dict(d):
                        if isinstance(d, dict):
                            return {
                                k: ("***REDACTED***" if any(s in k.lower() for s in ["key", "token", "secret", "password"]) else redact_dict(v))
                                for k, v in d.items()
                            }
                        elif isinstance(d, list):
                            return [redact_dict(i) for i in d]
                        return d
                    zf.writestr("config.json", json.dumps(redact_dict(config_data), indent=2))
                except Exception:
                    pass

    return output_path
