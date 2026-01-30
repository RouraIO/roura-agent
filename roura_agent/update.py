"""
Roura Agent Update System - Check for and apply updates.

© Roura.io
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import httpx

from .constants import VERSION, VERSION_TUPLE


# GitHub repo for version checking
GITHUB_REPO = "RouraIO/roura-agent"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_TAGS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/tags"

# Local cache for update check (don't spam GitHub API)
CACHE_DIR = Path.home() / ".config" / "roura-agent" / "cache"
VERSION_CACHE_FILE = CACHE_DIR / "latest_version.json"
CHECK_INTERVAL_HOURS = 6


@dataclass
class UpdateInfo:
    """Information about an available update."""
    current_version: str
    latest_version: str
    has_update: bool
    release_notes: str = ""
    release_url: str = ""
    new_features: list[str] = None

    def __post_init__(self):
        if self.new_features is None:
            self.new_features = []


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string to tuple for comparison."""
    # Remove 'v' prefix if present
    version_str = version_str.lstrip("v")
    parts = version_str.split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def check_for_updates(force: bool = False) -> Optional[UpdateInfo]:
    """
    Check if a newer version is available.

    Uses cached results unless force=True or cache is stale.
    Returns UpdateInfo if check succeeded, None on error.
    """
    # Check cache first
    if not force and VERSION_CACHE_FILE.exists():
        try:
            cache_data = json.loads(VERSION_CACHE_FILE.read_text())
            cache_time = datetime.fromisoformat(cache_data.get("checked_at", ""))
            if datetime.now() - cache_time < timedelta(hours=CHECK_INTERVAL_HOURS):
                # Cache is fresh
                latest = cache_data.get("latest_version", VERSION)
                return UpdateInfo(
                    current_version=VERSION,
                    latest_version=latest,
                    has_update=parse_version(latest) > VERSION_TUPLE,
                    release_notes=cache_data.get("release_notes", ""),
                    release_url=cache_data.get("release_url", ""),
                    new_features=cache_data.get("new_features", []),
                )
        except (json.JSONDecodeError, ValueError, KeyError):
            pass  # Cache invalid, fetch fresh

    # Fetch from GitHub
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github.v3+json"},
            )

            latest_version = None
            release_notes = ""
            release_url = ""

            if response.status_code == 404:
                # No releases yet, try tags instead
                tags_response = client.get(
                    GITHUB_TAGS_URL,
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if tags_response.status_code == 200:
                    tags = tags_response.json()
                    if tags:
                        # Get the first (most recent) tag
                        latest_version = tags[0].get("name", VERSION).lstrip("v")
                        release_url = f"https://github.com/{GITHUB_REPO}/releases/tag/v{latest_version}"

                if not latest_version:
                    return UpdateInfo(
                        current_version=VERSION,
                        latest_version=VERSION,
                        has_update=False,
                    )
            else:
                response.raise_for_status()
                data = response.json()
                latest_version = data.get("tag_name", VERSION).lstrip("v")
                release_notes = data.get("body", "")
                release_url = data.get("html_url", "")

        # Parse new features from release notes (lines starting with "- NEW:" or "NEW:")
        new_features = []
        for line in release_notes.split("\n"):
            line = line.strip()
            if line.lower().startswith("- new:") or line.lower().startswith("new:"):
                feature = line.split(":", 1)[1].strip() if ":" in line else line
                new_features.append(feature)

        # Cache the result
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        VERSION_CACHE_FILE.write_text(json.dumps({
            "latest_version": latest_version,
            "release_notes": release_notes,
            "release_url": release_url,
            "new_features": new_features,
            "checked_at": datetime.now().isoformat(),
        }))

        return UpdateInfo(
            current_version=VERSION,
            latest_version=latest_version,
            has_update=parse_version(latest_version) > VERSION_TUPLE,
            release_notes=release_notes,
            release_url=release_url,
            new_features=new_features,
        )

    except (httpx.HTTPError, json.JSONDecodeError, Exception):
        # Network error or parsing error - return None
        return None


def perform_update(console) -> bool:
    """
    Perform the update using pipx.

    Returns True if update succeeded, False otherwise.
    """
    from rich.panel import Panel
    from .branding import Colors, Icons

    console.print(f"\n[{Colors.PRIMARY}]Checking for updates...[/{Colors.PRIMARY}]")

    # Check current installation method
    # Try pipx first
    try:
        result = subprocess.run(
            ["pipx", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pipx_data = json.loads(result.stdout) if result.returncode == 0 else {}
        is_pipx = "roura-agent" in str(pipx_data)
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        is_pipx = False

    # Check for git repo (development install)
    repo_path = Path(__file__).parent.parent
    is_git_repo = (repo_path / ".git").exists()

    if is_git_repo:
        # Development install - use git pull
        console.print(f"[{Colors.DIM}]Development install detected. Pulling latest changes...[/{Colors.DIM}]")

        try:
            # Git pull
            result = subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                console.print(f"[{Colors.ERROR}]Git pull failed: {result.stderr}[/{Colors.ERROR}]")
                return False

            console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} Git pull complete[/{Colors.SUCCESS}]")

            # Reinstall with pipx
            console.print(f"[{Colors.DIM}]Reinstalling package...[/{Colors.DIM}]")

            result = subprocess.run(
                ["pipx", "install", str(repo_path), "--force"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                console.print(f"[{Colors.ERROR}]Reinstall failed: {result.stderr}[/{Colors.ERROR}]")
                return False

            console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} Update complete![/{Colors.SUCCESS}]")
            return True

        except subprocess.TimeoutExpired:
            console.print(f"[{Colors.ERROR}]Update timed out[/{Colors.ERROR}]")
            return False
        except FileNotFoundError as e:
            console.print(f"[{Colors.ERROR}]Required tool not found: {e}[/{Colors.ERROR}]")
            return False

    elif is_pipx:
        # Get latest version from GitHub
        update_info = check_for_updates(force=True)
        if not update_info or not update_info.has_update:
            console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} Already on latest version![/{Colors.SUCCESS}]")
            return False

        latest_version = update_info.latest_version
        github_url = f"git+https://github.com/{GITHUB_REPO}.git@v{latest_version}"

        console.print(f"[{Colors.DIM}]Installing v{latest_version} from GitHub...[/{Colors.DIM}]")

        try:
            result = subprocess.run(
                ["pipx", "install", github_url, "--force"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} Update complete![/{Colors.SUCCESS}]")
                return True
            else:
                console.print(f"[{Colors.ERROR}]Update failed: {result.stderr}[/{Colors.ERROR}]")
                return False

        except subprocess.TimeoutExpired:
            console.print(f"[{Colors.ERROR}]Update timed out[/{Colors.ERROR}]")
            return False
        except FileNotFoundError:
            console.print(f"[{Colors.ERROR}]pipx not found[/{Colors.ERROR}]")
            return False

    else:
        console.print(f"[{Colors.WARNING}]Cannot auto-update. Please update manually:[/{Colors.WARNING}]")
        console.print(f"  pip install --upgrade roura-agent")
        return False


def check_new_features_setup(console) -> None:
    """
    Check if new features require setup and prompt user.

    Called after update to configure any new features.
    """
    from rich.prompt import Confirm
    from .branding import Colors, Icons
    from .onboarding import GLOBAL_ENV_FILE, load_env_file, save_env_file

    update_info = check_for_updates()
    if not update_info or not update_info.new_features:
        return

    # Check which features need setup
    env_vars = {}
    if GLOBAL_ENV_FILE.exists():
        env_vars = load_env_file(GLOBAL_ENV_FILE)

    needs_setup = []

    # Feature detection - add new features here
    feature_checks = {
        "model switching": lambda: True,  # Always available
        "smart escalation": lambda: True,  # Always available
        "multi-model": lambda: env_vars.get("OPENAI_API_KEY") or env_vars.get("ANTHROPIC_API_KEY"),
    }

    for feature in update_info.new_features:
        feature_lower = feature.lower()
        for key, check in feature_checks.items():
            if key in feature_lower and not check():
                needs_setup.append(feature)
                break

    if needs_setup:
        console.print(f"\n[{Colors.INFO}]{Icons.INFO} New features available:[/{Colors.INFO}]")
        for feature in needs_setup:
            console.print(f"  • {feature}")

        if Confirm.ask(f"\n[{Colors.PRIMARY}]Run setup for new features?[/{Colors.PRIMARY}]", default=True):
            # Run setup wizard
            from .cli import setup
            setup()
