"""
Roura Agent Onboarding - First-run experience and guided setup.

This module provides:
- First-run detection
- Welcome screen with branding
- Ollama detection and configuration
- Model suggestions based on system capabilities
- Quick start guide

"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from .branding import LOGO, Colors, Icons, BRAND_NAME, BRAND_TAGLINE
from .config import CONFIG_FILE, CREDENTIALS_FILE, Config, load_config, save_config


# Marker file to track if onboarding has been completed
ONBOARDING_MARKER = Path.home() / ".config" / "roura-agent" / ".onboarded"


def is_first_run() -> bool:
    """Check if this is the first time running Roura Agent."""
    # Check if config exists and onboarding has been done
    if ONBOARDING_MARKER.exists():
        return False

    # Also check if config exists with valid model (user might have set up manually)
    if CONFIG_FILE.exists():
        try:
            config = load_config()
            if config.ollama.model:
                return False
        except Exception:
            pass

    # Check environment variable override
    if os.getenv("OLLAMA_MODEL"):
        return False

    return True


def mark_onboarding_complete() -> None:
    """Mark that onboarding has been completed."""
    ONBOARDING_MARKER.parent.mkdir(parents=True, exist_ok=True)
    ONBOARDING_MARKER.touch()


def detect_ollama() -> tuple[bool, str, list[str]]:
    """
    Detect Ollama installation and available models.

    Returns:
        (is_available, base_url, models)
    """
    from .ollama import list_models, get_base_url

    base_url = get_base_url()
    try:
        models = list_models(base_url)
        return True, base_url, models
    except Exception:
        # Try localhost if custom URL fails
        if base_url != "http://localhost:11434":
            try:
                models = list_models("http://localhost:11434")
                return True, "http://localhost:11434", models
            except Exception:
                pass
        return False, base_url, []


def get_recommended_models(available_models: list[str]) -> list[tuple[str, str]]:
    """
    Get recommended models from available models.

    Returns list of (model_name, reason) tuples.
    """
    recommendations = []

    # Priority models for coding tasks
    priority_models = [
        ("qwen2.5-coder", "Excellent for coding tasks, fast, good tool calling"),
        ("qwen2.5", "Great general purpose model with tool support"),
        ("llama3.1", "Meta's latest with tool calling support"),
        ("llama3.2", "Efficient and capable"),
        ("mistral", "Fast and reliable"),
        ("codellama", "Specialized for code"),
        ("deepseek-coder", "Strong coding model"),
    ]

    # Match available models to priority list
    for model_prefix, reason in priority_models:
        matching = [m for m in available_models if m.startswith(model_prefix)]
        if matching:
            # Prefer larger variants
            matching.sort(key=lambda x: ("32b" in x, "14b" in x, "7b" in x), reverse=True)
            recommendations.append((matching[0], reason))

    # Add any remaining models not in recommendations
    recommended_names = {r[0] for r in recommendations}
    for model in available_models[:5]:
        if model not in recommended_names:
            recommendations.append((model, "Available on your system"))

    return recommendations[:5]


def run_onboarding(console: Optional[Console] = None) -> bool:
    """
    Run the first-run onboarding experience.

    Returns True if setup completed successfully, False otherwise.
    """
    console = console or Console()

    # Welcome screen
    console.print(LOGO)
    console.print()
    console.print(Panel(
        f"[{Colors.PRIMARY_BOLD}]Welcome to {BRAND_NAME}![/{Colors.PRIMARY_BOLD}]\n\n"
        f"{BRAND_TAGLINE}\n\n"
        f"This quick setup will help you get started.\n"
        f"It takes about 1 minute.",
        title=f"[{Colors.PRIMARY}]{Icons.ROCKET} First-Time Setup[/{Colors.PRIMARY}]",
        border_style=Colors.BORDER_PRIMARY,
    ))
    console.print()

    # Check Ollama
    console.print(f"[{Colors.PRIMARY}]Step 1/3:[/{Colors.PRIMARY}] Checking for Ollama...\n")

    ollama_available, base_url, models = detect_ollama()

    if not ollama_available:
        console.print(Panel(
            f"[{Colors.WARNING}]{Icons.WARNING} Ollama not detected[/{Colors.WARNING}]\n\n"
            "Roura Agent requires Ollama to run local AI models.\n\n"
            f"[{Colors.PRIMARY}]To install:[/{Colors.PRIMARY}]\n"
            "  macOS:   curl -fsSL https://ollama.com/install.sh | sh\n"
            "  Linux:   curl -fsSL https://ollama.com/install.sh | sh\n"
            "  Windows: Download from https://ollama.com/download\n\n"
            "After installing, run: ollama serve\n"
            "Then pull a model: ollama pull qwen2.5-coder:32b",
            border_style=Colors.BORDER_WARNING,
        ))

        if Confirm.ask("Would you like to continue anyway?", default=False):
            console.print(f"\n[{Colors.DIM}]You can run 'roura-agent setup' later to configure.[/{Colors.DIM}]")
            mark_onboarding_complete()
            return False
        else:
            console.print(f"\n[{Colors.DIM}]Run 'roura-agent' again after installing Ollama.[/{Colors.DIM}]")
            return False

    console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Ollama found at {base_url}")
    console.print(f"[{Colors.DIM}]   {len(models)} model(s) available[/{Colors.DIM}]\n")

    # Model selection
    console.print(f"[{Colors.PRIMARY}]Step 2/3:[/{Colors.PRIMARY}] Select a model\n")

    if not models:
        console.print(Panel(
            f"[{Colors.WARNING}]{Icons.WARNING} No models installed[/{Colors.WARNING}]\n\n"
            "You need to pull a model before using Roura Agent.\n\n"
            f"[{Colors.PRIMARY}]Recommended for coding:[/{Colors.PRIMARY}]\n"
            "  ollama pull qwen2.5-coder:32b  (best quality, requires 20GB+ RAM)\n"
            "  ollama pull qwen2.5-coder:14b  (good balance)\n"
            "  ollama pull qwen2.5-coder:7b   (fastest, lower quality)",
            border_style=Colors.BORDER_WARNING,
        ))

        model_name = Prompt.ask(
            "\nEnter model name to use (or 'skip' to configure later)",
            default="qwen2.5-coder:7b",
        )

        if model_name.lower() == "skip":
            console.print(f"\n[{Colors.DIM}]Run 'roura-agent setup' to configure later.[/{Colors.DIM}]")
            mark_onboarding_complete()
            return False
    else:
        recommendations = get_recommended_models(models)

        table = Table(title="Available Models", show_header=True)
        table.add_column("#", style=Colors.DIM, width=3)
        table.add_column("Model", style=Colors.PRIMARY)
        table.add_column("Notes", style=Colors.DIM)

        for i, (model, reason) in enumerate(recommendations, 1):
            if i == 1:
                table.add_row(str(i), f"{model} (Recommended)", reason)
            else:
                table.add_row(str(i), model, reason)

        console.print(table)
        console.print()

        # Get user selection
        while True:
            choice = Prompt.ask(
                "Select model number or enter model name",
                default="1",
            )

            if choice.isdigit() and 1 <= int(choice) <= len(recommendations):
                model_name = recommendations[int(choice) - 1][0]
                break
            elif choice in models:
                model_name = choice
                break
            elif any(m.startswith(choice) for m in models):
                # Partial match
                matches = [m for m in models if m.startswith(choice)]
                model_name = matches[0]
                break
            else:
                console.print(f"[{Colors.WARNING}]Invalid selection. Try again.[/{Colors.WARNING}]")

    console.print(f"\n[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Selected: {model_name}\n")

    # Save configuration
    console.print(f"[{Colors.PRIMARY}]Step 3/3:[/{Colors.PRIMARY}] Saving configuration...\n")

    try:
        config = load_config()
    except Exception:
        config = Config()

    config.ollama.base_url = base_url
    config.ollama.model = model_name
    save_config(config)

    console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Configuration saved to {CONFIG_FILE}\n")

    # Show quick start guide
    console.print(Panel(
        f"[{Colors.PRIMARY_BOLD}]You're all set![/{Colors.PRIMARY_BOLD}]\n\n"
        f"[{Colors.PRIMARY}]Quick start:[/{Colors.PRIMARY}]\n"
        "  \u2022 Just type your request and press Enter\n"
        "  \u2022 I can read, write, and edit files\n"
        "  \u2022 I'll ask for approval before making changes\n"
        "  \u2022 Press ESC to interrupt at any time\n\n"
        f"[{Colors.PRIMARY}]Commands:[/{Colors.PRIMARY}]\n"
        "  /help     - Show help\n"
        "  /tools    - List available tools\n"
        "  /clear    - Clear conversation\n"
        "  exit      - Quit\n\n"
        f"[{Colors.DIM}]Configuration: {CONFIG_FILE}[/{Colors.DIM}]",
        title=f"[{Colors.SUCCESS}]{Icons.SUCCESS} Setup Complete[/{Colors.SUCCESS}]",
        border_style=Colors.BORDER_SUCCESS,
    ))

    mark_onboarding_complete()
    return True


def check_and_run_onboarding(console: Optional[Console] = None) -> bool:
    """
    Check if onboarding is needed and run it if so.

    Returns True if ready to proceed, False if setup incomplete.
    """
    if is_first_run():
        return run_onboarding(console)
    return True
