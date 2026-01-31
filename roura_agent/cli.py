"""
Roura Agent CLI - Local-first AI coding assistant.

© Roura.io
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .branding import (
    Colors,
    Icons,
    format_diff_line,
    get_logo,
    get_risk_color,
)
from .config import (
    CONFIG_FILE,
    CREDENTIALS_FILE,
    apply_config_to_env,
    detect_project,
    get_effective_config,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)
from .constants import VERSION
from .ollama import get_base_url, list_models
from .safety import BlastRadiusLimits, SafetyMode

# Import these to ensure tools are registered
from .tools.base import registry
from .tools.doctor import format_results, has_critical_failures, run_all_checks
from .tools.fs import edit_file, fs_edit, fs_write, list_directory, read_file, write_file
from .tools.git import (
    create_commit,
    get_diff,
    get_log,
    get_status,
    git_add,
    git_commit,
    stage_files,
)
from .tools.shell import run_command, shell_exec


# Version callback for --version flag
def version_callback(value: bool):
    if value:
        console.print(f"[bold cyan]Roura Agent[/bold cyan] version [green]{VERSION}[/green]")
        raise typer.Exit()

app = typer.Typer(
    invoke_without_command=True,
    rich_markup_mode="rich",
    no_args_is_help=False,
)
fs_app = typer.Typer(help="[bold]Filesystem tools[/bold] - read, write, edit files")
git_app = typer.Typer(help="[bold]Git tools[/bold] - status, diff, log, add, commit")
shell_app = typer.Typer(help="[bold]Shell tools[/bold] - execute commands")
mcp_app = typer.Typer(help="[bold]MCP tools[/bold] - Model Context Protocol servers")
image_app = typer.Typer(help="[bold]Image tools[/bold] - read and analyze images")
notebook_app = typer.Typer(help="[bold]Notebook tools[/bold] - Jupyter notebook operations")
memory_app = typer.Typer(help="[bold]Memory tools[/bold] - store and recall notes")

app.add_typer(fs_app, name="fs")
app.add_typer(git_app, name="git")
app.add_typer(shell_app, name="shell")
app.add_typer(mcp_app, name="mcp")
app.add_typer(image_app, name="image")
app.add_typer(notebook_app, name="notebook")
app.add_typer(memory_app, name="memory")

console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        "-p",
        help="LLM provider: [cyan]ollama[/cyan], [green]openai[/green], [magenta]anthropic[/magenta]",
        envvar="ROURA_PROVIDER",
    ),
    safe_mode: bool = typer.Option(
        False,
        "--safe-mode",
        "-s",
        help="Disable dangerous tools (shell.exec, etc.)",
        envvar="ROURA_SAFE_MODE",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Preview all changes without actually writing files",
        envvar="ROURA_DRY_RUN",
    ),
    readonly: bool = typer.Option(
        False,
        "--readonly",
        "-r",
        help="Completely disable all file modifications",
        envvar="ROURA_READONLY",
    ),
    allow: list[str] = typer.Option(
        None,
        "--allow",
        "-a",
        help="Only allow modifications to files matching these globs (can repeat)",
    ),
    block: list[str] = typer.Option(
        None,
        "--block",
        "-b",
        help="Block modifications to files matching these globs (can repeat)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging to console",
    ),
    resume: str = typer.Option(
        None,
        "--resume",
        help="Resume a previous session by ID",
    ),
):
    """
    [bold cyan]Roura Agent[/bold cyan] - Local-first AI coding assistant by [bold]Roura.io[/bold].

    Run without arguments to start the interactive agent.

    [dim]Examples:[/dim]
      roura-agent                    Start interactive agent
      roura-agent --safe-mode        Start with dangerous tools disabled
      roura-agent doctor             Run system health check
      roura-agent tools              List all available tools
      roura-agent fs read file.py    Read a file
      roura-agent git status         Show git status
    """

    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["provider"] = provider
    ctx.obj["safe_mode"] = safe_mode
    ctx.obj["dry_run"] = dry_run
    ctx.obj["readonly"] = readonly
    ctx.obj["allow"] = allow
    ctx.obj["block"] = block
    ctx.obj["debug"] = debug

    # Setup logging if debug
    if debug:
        from .logging import setup_logging
        setup_logging(level="DEBUG", log_to_console=True, console_level="DEBUG")

    # Apply safety modes
    if dry_run:
        SafetyMode.enable_dry_run()
    if readonly:
        SafetyMode.enable_readonly()

    # Apply file pattern limits
    if allow or block:
        limits = BlastRadiusLimits(
            allowlist=allow if allow else None,
            blocklist=block if block else None,
        )
        SafetyMode.set_limits(limits)

    # If no command given, launch interactive agent
    if ctx.invoked_subcommand is None:
        _run_agent(
            provider=provider,
            safe_mode=safe_mode,
            dry_run=dry_run,
            readonly=readonly,
            allow=allow,
            block=block,
            debug=debug,
            resume=resume,
        )


def _run_agent(
    provider: str = None,
    safe_mode: bool = False,
    dry_run: bool = False,
    readonly: bool = False,
    allow: list[str] = None,
    block: list[str] = None,
    debug: bool = False,
    resume: str = None,
):
    """Launch the interactive agent."""
    from .agent.loop import AgentConfig as LoopConfig
    from .agent.loop import AgentLoop
    from .llm import ProviderType, detect_available_providers, get_provider
    from .onboarding import check_and_run_onboarding, clear_screen, get_tier_display

    # Clear the terminal for a clean start
    clear_screen()

    # Check for first-run onboarding
    if not check_and_run_onboarding(console):
        return  # Setup incomplete

    # Load and apply configuration
    config, creds = get_effective_config()
    apply_config_to_env(config, creds)

    # Display logo
    console.print(get_logo())

    # Check for updates (non-blocking, cached)
    from .update import check_for_updates
    update_info = check_for_updates()
    if update_info and update_info.has_update:
        console.print(
            f"[{Colors.SUCCESS}]{Icons.SUCCESS} Update available: v{update_info.latest_version}[/{Colors.SUCCESS}] "
            f"[{Colors.DIM}](current: v{update_info.current_version})[/{Colors.DIM}]"
        )
        console.print(
            f"[{Colors.DIM}]  Use /upgrade inside the CLI (will restart, context may be lost)[/{Colors.DIM}]"
        )
        console.print(
            f"[{Colors.DIM}]  Or exit and run: pipx upgrade roura-agent[/{Colors.DIM}]"
        )
        console.print()

    # Handle safe mode early
    if safe_mode:
        _enable_safe_mode()

    # Determine provider type
    provider_type = None
    if provider:
        provider_map = {
            "ollama": ProviderType.OLLAMA,
            "openai": ProviderType.OPENAI,
            "anthropic": ProviderType.ANTHROPIC,
        }
        provider_type = provider_map.get(provider.lower())
        if not provider_type:
            console.print(f"[red]Error:[/red] Unknown provider '{provider}'")
            console.print("[dim]Available: ollama, openai, anthropic[/dim]")
            raise typer.Exit(1)
    else:
        # Try to use last provider
        from .onboarding import get_last_provider
        last_provider = get_last_provider()
        if last_provider:
            provider_map = {
                "ollama": ProviderType.OLLAMA,
                "openai": ProviderType.OPENAI,
                "anthropic": ProviderType.ANTHROPIC,
            }
            provider_type = provider_map.get(last_provider.lower())

    # Get provider instance
    try:
        llm_provider = get_provider(provider_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("[dim]Run 'roura-agent setup' to configure, or set environment variables:[/dim]")
        console.print("[dim]  OPENAI_API_KEY=xxx or ANTHROPIC_API_KEY=xxx[/dim]")
        console.print("[dim]  Or ensure Ollama is running with OLLAMA_MODEL set[/dim]")
        raise typer.Exit(1)

    # Detect project and get tier
    project = detect_project()
    tier_display = get_tier_display()
    available = detect_available_providers()

    # Build info panel with two sections

    # Left section: Model & Session info
    left_section = (
        f"[{Colors.PRIMARY}]Model[/{Colors.PRIMARY}]     {llm_provider.model_name}\n"
        f"[{Colors.PRIMARY}]Provider[/{Colors.PRIMARY}]  {llm_provider.provider_type.value}\n"
        f"[{Colors.PRIMARY}]Available[/{Colors.PRIMARY}] {', '.join(p.value for p in available)}"
    )

    # Right section: Project & path info
    # Shorten the cwd path for display
    cwd = str(project.root)
    home = str(Path.home())
    if cwd.startswith(home):
        cwd_display = "~" + cwd[len(home):]
    else:
        cwd_display = cwd
    # Truncate if too long
    if len(cwd_display) > 35:
        cwd_display = "..." + cwd_display[-32:]

    branch_display = project.git_branch if project.git_branch else "—"

    right_section = (
        f"[{Colors.PRIMARY}]Path[/{Colors.PRIMARY}]     {cwd_display}\n"
        f"[{Colors.PRIMARY}]Branch[/{Colors.PRIMARY}]   {branch_display}\n"
        f"[{Colors.PRIMARY}]Files[/{Colors.PRIMARY}]    {len(project.files)} ({project.type})"
    )

    # Create two-column layout
    info_table = Table.grid(padding=(0, 4))
    info_table.add_column(justify="left")
    info_table.add_column(justify="left")
    info_table.add_row(left_section, right_section)

    # Commands hint
    commands_hint = f"\n[{Colors.DIM}]/help[/{Colors.DIM}] commands  │  [{Colors.DIM}]/model[/{Colors.DIM}] switch  │  [{Colors.DIM}]ESC[/{Colors.DIM}] interrupt  │  [{Colors.DIM}]exit[/{Colors.DIM}] quit"

    console.print(Panel(
        Group(info_table, Text.from_markup(commands_hint)),
        title=f"[{Colors.PRIMARY_BOLD}]{Icons.ROCKET} Roura Agent v{VERSION}[/{Colors.PRIMARY_BOLD}]",
        subtitle=f"[{Colors.DIM}]{tier_display}[/{Colors.DIM}]",
        border_style=Colors.BORDER_PRIMARY,
    ))

    # Show mode indicators if any
    modes = []
    if safe_mode:
        modes.append(f"[{Colors.WARNING}]{Icons.LOCK} Safe Mode[/{Colors.WARNING}]")
    if dry_run:
        modes.append(f"[{Colors.INFO}]{Icons.INFO} Dry-Run[/{Colors.INFO}]")
    if readonly:
        modes.append(f"[{Colors.ERROR}]{Icons.FORBIDDEN} Read-Only[/{Colors.ERROR}]")
    if allow:
        modes.append(f"[{Colors.DIM}]Allow: {', '.join(allow)}[/{Colors.DIM}]")
    if block:
        modes.append(f"[{Colors.DIM}]Block: {', '.join(block)}[/{Colors.DIM}]")

    if modes:
        console.print(" • ".join(modes))

    console.print()

    # Run agent
    loop_config = LoopConfig(
        max_tool_calls_per_turn=20,
        require_approval_moderate=True,
        require_approval_dangerous=True,
        stream_responses=True,
    )

    agent = AgentLoop(console=console, config=loop_config, project=project)
    if provider_type:
        agent.set_provider(provider_type)
    if resume:
        agent._resume_session(resume)
    agent.run()


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run system health diagnostics."""
    results = run_all_checks()
    output = format_results(results, use_json=json_output)
    console.print(output)

    if has_critical_failures(results):
        raise typer.Exit(code=1)


@app.command()
def tools():
    """List all available tools."""
    table = Table(title="Available Tools")
    table.add_column("Tool", style=Colors.PRIMARY)
    table.add_column("Risk", justify="center")
    table.add_column("Description")


    for name, tool in sorted(registry._tools.items()):
        color = get_risk_color(tool.risk_level.value)
        risk_text = f"[{color}]{tool.risk_level.value}[/{color}]"
        table.add_row(name, risk_text, tool.description)

    console.print(table)


@app.command()
def ping():
    """Ping Ollama and list available models."""
    base = get_base_url()
    try:
        models = list_models(base)

        table = Table(title=f"Ollama @ {base}")
        table.add_column("Model")
        for m in models:
            table.add_row(m)

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error connecting to Ollama:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def config():
    """Show current configuration."""
    cfg, creds = get_effective_config()

    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    # Ollama
    ollama_url = cfg.ollama.base_url or "[dim]not set[/dim]"
    ollama_src = "env" if os.getenv("OLLAMA_BASE_URL") else ("file" if cfg.ollama.base_url else "-")
    table.add_row("OLLAMA_BASE_URL", ollama_url, ollama_src)

    ollama_model = cfg.ollama.model or "[dim]not set[/dim]"
    model_src = "env" if os.getenv("OLLAMA_MODEL") else ("file" if cfg.ollama.model else "-")
    table.add_row("OLLAMA_MODEL", ollama_model, model_src)

    # Jira
    jira_url = cfg.jira.url or "[dim]not set[/dim]"
    jira_url_src = "env" if os.getenv("JIRA_URL") else ("file" if cfg.jira.url else "-")
    table.add_row("JIRA_URL", jira_url, jira_url_src)

    jira_email = cfg.jira.email or "[dim]not set[/dim]"
    jira_email_src = "env" if os.getenv("JIRA_EMAIL") else ("file" if cfg.jira.email else "-")
    table.add_row("JIRA_EMAIL", jira_email, jira_email_src)

    jira_token = "[dim]***[/dim]" if creds.jira_token else "[dim]not set[/dim]"
    token_src = "env" if os.getenv("JIRA_TOKEN") else ("file" if creds.jira_token else "-")
    table.add_row("JIRA_TOKEN", jira_token, token_src)

    console.print(table)
    console.print(f"\n[dim]Config file: {CONFIG_FILE}[/dim]")
    console.print("[dim]Run 'roura-agent setup' to configure interactively[/dim]")


@app.command()
def update(
    force: bool = typer.Option(False, "--force", "-f", help="Force check, ignore cache"),
):
    """Check for and install updates."""
    from .update import check_for_updates, perform_update

    console.print(f"[{Colors.PRIMARY}]Checking for updates...[/{Colors.PRIMARY}]")

    update_info = check_for_updates(force=force)

    if update_info is None:
        console.print(f"[{Colors.ERROR}]Could not check for updates. Check your internet connection.[/{Colors.ERROR}]")
        raise typer.Exit(1)

    if not update_info.has_update:
        console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} You're on the latest version (v{update_info.current_version})[/{Colors.SUCCESS}]")
        return

    console.print(f"\n[{Colors.SUCCESS}]{Icons.SUCCESS} Update available![/{Colors.SUCCESS}]")
    console.print(f"  Current: v{update_info.current_version}")
    console.print(f"  Latest:  v{update_info.latest_version}")

    if update_info.new_features:
        console.print(f"\n[{Colors.INFO}]New features:[/{Colors.INFO}]")
        for feature in update_info.new_features[:5]:
            console.print(f"  • {feature}")

    if Confirm.ask(f"\n[{Colors.PRIMARY}]Install update?[/{Colors.PRIMARY}]", default=True):
        perform_update(console)


@app.command()
def setup():
    """Interactive configuration wizard."""
    console.print(Panel(
        "[bold]Roura Agent Setup[/bold]\n\n"
        "This wizard will help you configure Roura Agent.\n"
        "Press Enter to keep current values.",
        title="🔧 Setup",
        border_style="cyan",
    ))

    # Load existing config
    cfg = load_config()
    creds = load_credentials()

    console.print("\n[bold cyan]1. Ollama Configuration[/bold cyan]\n")

    # Ollama Base URL
    current_url = cfg.ollama.base_url or "http://localhost:11434"
    new_url = Prompt.ask(
        "Ollama Base URL",
        default=current_url,
    )
    cfg.ollama.base_url = new_url

    # Test connection and list models
    console.print("[dim]Testing connection...[/dim]")
    try:
        models = list_models(new_url)
        if models:
            console.print(f"[green]✓[/green] Connected. Found {len(models)} models.")

            # Let user pick a model
            console.print("\nAvailable models:")
            for i, m in enumerate(models[:10], 1):
                console.print(f"  {i}. {m}")

            current_model = cfg.ollama.model or (models[0] if models else "")
            new_model = Prompt.ask(
                "\nOllama Model",
                default=current_model,
            )
            cfg.ollama.model = new_model
        else:
            console.print("[yellow]⚠[/yellow] No models found. Install one with: ollama pull qwen2.5-coder:32b")
            cfg.ollama.model = Prompt.ask("Ollama Model (manual entry)", default=cfg.ollama.model or "")
    except Exception as e:
        console.print(f"[red]✗[/red] Could not connect: {e}")
        cfg.ollama.model = Prompt.ask("Ollama Model (manual entry)", default=cfg.ollama.model or "")

    # Jira Configuration
    console.print("\n[bold cyan]2. Jira Configuration (optional)[/bold cyan]\n")

    if Confirm.ask("Configure Jira integration?", default=bool(cfg.jira.url)):
        cfg.jira.url = Prompt.ask(
            "Jira URL (e.g., https://company.atlassian.net)",
            default=cfg.jira.url or "",
        )
        cfg.jira.email = Prompt.ask(
            "Jira Email",
            default=cfg.jira.email or "",
        )

        # Token - show masked if exists
        token_display = "***" if creds.jira_token else ""
        console.print("[dim]API Token: Create one at https://id.atlassian.com/manage-profile/security/api-tokens[/dim]")
        new_token = Prompt.ask(
            "Jira API Token",
            default=token_display,
            password=True,
        )
        if new_token and new_token != "***":
            creds.jira_token = new_token

    # GitHub Configuration
    console.print("\n[bold cyan]3. GitHub Configuration[/bold cyan]\n")
    console.print("[dim]GitHub uses the 'gh' CLI. Checking authentication...[/dim]")

    import subprocess
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            console.print("[green]✓[/green] GitHub CLI is authenticated")
        else:
            console.print("[yellow]⚠[/yellow] Not authenticated. Run: gh auth login")
    except FileNotFoundError:
        console.print("[yellow]⚠[/yellow] GitHub CLI not found. Install with: brew install gh")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Could not check: {e}")

    cfg.github.default_base_branch = Prompt.ask(
        "Default base branch for PRs",
        default=cfg.github.default_base_branch or "main",
    )

    # Save
    console.print("\n[bold cyan]Saving configuration...[/bold cyan]")
    save_config(cfg)
    save_credentials(creds)

    console.print(f"[green]✓[/green] Config saved to {CONFIG_FILE}")
    if creds.jira_token:
        console.print(f"[green]✓[/green] Credentials saved to {CREDENTIALS_FILE} (permissions: 600)")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("[dim]Run 'roura-agent' to start.[/dim]")


@app.command()
def reset(
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
):
    """Factory reset - clear all settings and restart onboarding."""
    from .onboarding import (
        GLOBAL_ENV_FILE,
        LAST_PROVIDER_FILE,
        ONBOARDING_MARKER,
        WALKTHROUGH_MARKER,
    )

    console.print(Panel(
        "[bold yellow]Factory Reset[/bold yellow]\n\n"
        "This will:\n"
        f"  • Delete onboarding marker ({ONBOARDING_MARKER})\n"
        f"  • Delete walkthrough marker ({WALKTHROUGH_MARKER})\n"
        f"  • Delete last provider setting\n"
        f"  • Delete global .env file ({GLOBAL_ENV_FILE})\n"
        f"  • Delete config file ({CONFIG_FILE})\n"
        f"  • Delete credentials file ({CREDENTIALS_FILE})\n\n"
        "[dim]You'll go through the first-time setup and walkthrough again on next run.[/dim]",
        title="[yellow]⚠ Warning[/yellow]",
        border_style="yellow",
    ))

    if not force:
        if not Confirm.ask("\n[yellow]Are you sure you want to reset?[/yellow]", default=False):
            console.print("[dim]Reset cancelled[/dim]")
            raise typer.Exit(0)

    deleted = []

    # Delete onboarding marker
    if ONBOARDING_MARKER.exists():
        ONBOARDING_MARKER.unlink()
        deleted.append("onboarding marker")

    # Delete walkthrough marker
    if WALKTHROUGH_MARKER.exists():
        WALKTHROUGH_MARKER.unlink()
        deleted.append("walkthrough marker")

    # Delete last provider setting
    if LAST_PROVIDER_FILE.exists():
        LAST_PROVIDER_FILE.unlink()
        deleted.append("last provider")

    # Delete global .env
    if GLOBAL_ENV_FILE.exists():
        GLOBAL_ENV_FILE.unlink()
        deleted.append("global .env")

    # Delete config
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        deleted.append("config")

    # Delete credentials
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        deleted.append("credentials")

    if deleted:
        console.print(f"\n[green]✓[/green] Deleted: {', '.join(deleted)}")
    else:
        console.print("\n[dim]Nothing to delete - already clean[/dim]")

    console.print("\n[bold green]Reset complete![/bold green]")
    console.print("[dim]Run 'roura-agent' to start fresh.[/dim]")


@app.command()
def project():
    """Show information about the current project."""
    proj = detect_project()

    console.print(Panel(
        f"[bold]{proj.name}[/bold]\n"
        f"Type: {proj.type}\n"
        f"Root: {proj.root}\n"
        f"Branch: {proj.git_branch or 'N/A'}\n"
        f"Files: {len(proj.files)}",
        title="📁 Project",
        border_style="cyan",
    ))

    # Show structure
    from .config import format_structure_tree
    tree = format_structure_tree(proj.structure, max_depth=3)
    if tree:
        console.print("\n[bold]Structure:[/bold]")
        console.print(tree)


# --- Filesystem Tools ---


@fs_app.command("read")
def fs_read(
    path: str = typer.Argument(..., help="Path to the file to read"),
    offset: int = typer.Option(1, "--offset", "-o", help="Line number to start from (1-indexed)"),
    lines: int = typer.Option(0, "--lines", "-n", help="Number of lines to read (0 = all)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read the contents of a file."""
    result = read_file(path=path, offset=offset, lines=lines)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[dim]{output['path']} ({output['total_lines']} lines, showing {output['showing']})[/dim]")
        console.print(output["content"])


@fs_app.command("list")
def fs_list_cmd(
    path: str = typer.Argument(".", help="Path to the directory to list"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Include hidden files"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List contents of a directory."""
    result = list_directory(path=path, show_all=show_all)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[dim]{output['path']} ({output['count']} entries)[/dim]")

        table = Table()
        table.add_column("Type", width=4)
        table.add_column("Size", justify="right", width=10)
        table.add_column("Name")

        for entry in output["entries"]:
            type_icon = "dir" if entry["type"] == "dir" else "file"
            size_str = str(entry["size"]) if entry["type"] == "file" else "-"
            table.add_row(type_icon, size_str, entry["name"])

        console.print(table)


@fs_app.command("write")
def fs_write_cmd(
    path: str = typer.Argument(..., help="Path to the file to write"),
    content: str = typer.Option(None, "--content", "-c", help="Content to write"),
    content_file: str = typer.Option(None, "--from-file", "-f", help="Read content from this file"),
    create_dirs: bool = typer.Option(False, "--create-dirs", "-p", help="Create parent directories if needed"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be written without writing"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip approval prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Write content to a file (requires approval)."""
    if content is None and content_file is None:
        console.print("[red]Error:[/red] Must provide --content or --from-file")
        raise typer.Exit(code=1)

    if content is not None and content_file is not None:
        console.print("[red]Error:[/red] Cannot use both --content and --from-file")
        raise typer.Exit(code=1)

    if content_file is not None:
        try:
            content = Path(content_file).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[red]Error:[/red] Cannot read {content_file}: {e}")
            raise typer.Exit(code=1)

    preview = fs_write.preview(path=path, content=content)

    if preview["exists"]:
        action_str = "[yellow]OVERWRITE[/yellow]"
    else:
        action_str = "[green]CREATE[/green]"

    lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    bytes_count = len(content.encode("utf-8"))

    console.print(f"\n{action_str} {preview['path']}")
    console.print(f"[dim]{lines} lines, {bytes_count} bytes[/dim]")

    if preview["diff"]:
        console.print("\n[bold]Diff:[/bold]")
        _print_diff(preview["diff"])
    elif not preview["exists"]:
        console.print("\n[bold]Content preview:[/bold]")
        preview_lines = content.splitlines()[:10]
        for i, line in enumerate(preview_lines, 1):
            console.print(f"[green]+{i:4d} | {line}[/green]")
        if len(content.splitlines()) > 10:
            console.print(f"[dim]... and {len(content.splitlines()) - 10} more lines[/dim]")

    console.print()

    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    if not force:
        if not _confirm("APPROVE_WRITE?"):
            console.print("[red]Write cancelled[/red]")
            raise typer.Exit(code=0)

    result = write_file(path=path, content=content, create_dirs=create_dirs)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[green]✓[/green] {output['action'].capitalize()} {output['path']}")


@fs_app.command("edit")
def fs_edit_cmd(
    path: str = typer.Argument(..., help="Path to the file to edit"),
    old_text: str = typer.Option(..., "--old", "-o", help="Text to search for"),
    new_text: str = typer.Option(..., "--new", "-n", help="Text to replace with"),
    replace_all: bool = typer.Option(False, "--replace-all", "-a", help="Replace all occurrences"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be changed without changing"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip approval prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Edit a file by replacing text (requires approval)."""
    preview = fs_edit.preview(path=path, old_text=old_text, new_text=new_text, replace_all=replace_all)

    if preview["error"]:
        console.print(f"[red]Error:[/red] {preview['error']}")
        if preview["occurrences"] > 1:
            console.print(f"[dim]Found {preview['occurrences']} occurrences. Use --replace-all or provide more context.[/dim]")
        raise typer.Exit(code=1)

    console.print(f"\n[yellow]EDIT[/yellow] {preview['path']}")
    console.print(f"[dim]Replacing {preview['would_replace']} occurrence(s)[/dim]")

    if preview["diff"]:
        console.print("\n[bold]Diff:[/bold]")
        _print_diff(preview["diff"])

    console.print()

    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    if not force:
        if not _confirm("APPROVE_EDIT?"):
            console.print("[red]Edit cancelled[/red]")
            raise typer.Exit(code=0)

    result = edit_file(path=path, old_text=old_text, new_text=new_text, replace_all=replace_all)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[green]✓[/green] Edited {output['path']}")


# --- Git Tools ---


@git_app.command("status")
def git_status_cmd(
    path: str = typer.Argument(".", help="Path to repository"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show the working tree status."""
    result = get_status(path=path)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[bold]Repository:[/bold] {output['repo_root']}")
        console.print(f"[bold]Branch:[/bold] {output['branch']}")

        if output["clean"]:
            console.print("\n[green]Working tree clean[/green]")
        else:
            if output["staged"]:
                console.print("\n[bold green]Staged changes:[/bold green]")
                for item in output["staged"]:
                    console.print(f"  [green]{item['status']}[/green] {item['file']}")

            if output["modified"]:
                console.print("\n[bold yellow]Modified:[/bold yellow]")
                for f in output["modified"]:
                    console.print(f"  [yellow]M[/yellow] {f}")

            if output["untracked"]:
                console.print("\n[bold red]Untracked:[/bold red]")
                for f in output["untracked"]:
                    console.print(f"  [red]?[/red] {f}")


@git_app.command("diff")
def git_diff_cmd(
    path: str = typer.Argument(".", help="Path to repository or file"),
    staged: bool = typer.Option(False, "--staged", "-s", help="Show staged changes"),
    commit: str = typer.Option(None, "--commit", "-c", help="Compare against specific commit"),
    stat_only: bool = typer.Option(False, "--stat", help="Show only diffstat"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show changes between commits, commit and working tree, etc."""
    result = get_diff(path=path, staged=staged, commit=commit)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output

        if not output["has_changes"]:
            diff_type = "staged" if staged else "unstaged"
            console.print(f"[dim]No {diff_type} changes[/dim]")
            return

        if stat_only:
            console.print(output["stat"])
        else:
            _print_diff(output["diff"])


@git_app.command("log")
def git_log_cmd(
    path: str = typer.Argument(".", help="Path to repository"),
    count: int = typer.Option(10, "--count", "-n", help="Number of commits to show"),
    oneline: bool = typer.Option(False, "--oneline", help="Show one line per commit"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show commit logs."""
    result = get_log(path=path, count=count, oneline=oneline)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output

        if not output["commits"]:
            console.print("[dim]No commits found[/dim]")
            return

        for commit in output["commits"]:
            if oneline:
                console.print(f"[yellow]{commit['hash'][:7]}[/yellow] {commit['message']}")
            else:
                console.print(f"[yellow]commit {commit['hash']}[/yellow]")
                console.print(f"Author: {commit['author']} <{commit['email']}>")
                console.print(f"Date:   {commit['date']}")
                console.print()
                console.print(f"    {commit['subject']}")
                if commit.get("body"):
                    for line in commit["body"].splitlines():
                        console.print(f"    {line}")
                console.print()


@git_app.command("add")
def git_add_cmd(
    files: list[str] = typer.Argument(..., help="Files to stage"),
    path: str = typer.Option(".", "--path", "-C", help="Path to repository"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be staged without staging"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip approval prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Stage files for commit (requires approval)."""
    preview = git_add.preview(files=files, path=path)

    if preview["errors"]:
        for error in preview["errors"]:
            console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1)

    console.print(f"\n[yellow]STAGE[/yellow] {len(preview['would_stage'])} file(s)")
    for f in preview["would_stage"][:20]:
        console.print(f"  [green]+[/green] {f}")
    if len(preview["would_stage"]) > 20:
        console.print(f"  [dim]... and {len(preview['would_stage']) - 20} more files[/dim]")

    console.print()

    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    if not force:
        if not _confirm("APPROVE_ADD?"):
            console.print("[red]Add cancelled[/red]")
            raise typer.Exit(code=0)

    result = stage_files(files=files, path=path)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[green]✓[/green] Staged {output['staged_count']} file(s)")


@git_app.command("commit")
def git_commit_cmd(
    message: str = typer.Option(..., "--message", "-m", help="Commit message"),
    path: str = typer.Option(".", "--path", "-C", help="Path to repository"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be committed without committing"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip approval prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create a commit with staged changes (requires approval)."""
    preview = git_commit.preview(message=message, path=path)

    if preview["error"]:
        console.print(f"[red]Error:[/red] {preview['error']}")
        raise typer.Exit(code=1)

    console.print(f"\n[yellow]COMMIT[/yellow] {len(preview['staged_files'])} file(s)")
    console.print(f"[bold]Message:[/bold] {message}")
    console.print()

    console.print("[bold]Staged files:[/bold]")
    for item in preview["staged_files"][:20]:
        status_color = {"M": "yellow", "A": "green", "D": "red", "R": "cyan"}.get(item["status"], "white")
        console.print(f"  [{status_color}]{item['status']}[/{status_color}] {item['file']}")
    if len(preview["staged_files"]) > 20:
        console.print(f"  [dim]... and {len(preview['staged_files']) - 20} more files[/dim]")

    if preview["staged_diff"]:
        console.print("\n[bold]Diff preview:[/bold]")
        diff_lines = preview["staged_diff"].splitlines()[:30]
        _print_diff("\n".join(diff_lines))
        if len(preview["staged_diff"].splitlines()) > 30:
            console.print(f"[dim]... diff truncated ({len(preview['staged_diff'].splitlines())} total lines)[/dim]")

    console.print()

    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    if not force:
        if not _confirm("APPROVE_COMMIT?"):
            console.print("[red]Commit cancelled[/red]")
            raise typer.Exit(code=0)

    result = create_commit(message=message, path=path)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[green]✓[/green] Created commit [yellow]{output['short_hash']}[/yellow]")


# --- Shell Tools ---


@shell_app.command("exec")
def shell_exec_cmd(
    command: str = typer.Argument(..., help="Command to execute"),
    cwd: str = typer.Option(None, "--cwd", "-C", help="Working directory"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed"),
    force: bool = typer.Option(False, "--force", "-y", help="Skip approval prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Execute a shell command (requires approval)."""
    preview = shell_exec.preview(command=command, cwd=cwd, timeout=timeout)

    if preview["blocked"]:
        console.print(f"[red]Blocked:[/red] {preview['block_reason']}")
        raise typer.Exit(code=1)

    danger_str = " [red]⚠ DANGEROUS[/red]" if preview["dangerous"] else ""
    console.print(f"\n[yellow]EXECUTE[/yellow]{danger_str}")
    console.print(f"[bold]Command:[/bold] {preview['command']}")
    console.print(f"[dim]Working directory: {preview['cwd']}[/dim]")

    if preview["dangerous_patterns"]:
        console.print(f"[red]Dangerous patterns: {', '.join(preview['dangerous_patterns'])}[/red]")

    console.print()

    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    if not force:
        if not _confirm("APPROVE_EXEC?"):
            console.print("[red]Execution cancelled[/red]")
            raise typer.Exit(code=0)

    result = run_command(command=command, cwd=cwd, timeout=timeout)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        if output["exit_code"] == 0:
            console.print("[green]✓[/green] Command succeeded")
        else:
            console.print(f"[yellow]Exit code: {output['exit_code']}[/yellow]")

        if output["stdout"]:
            console.print("\n[bold]Output:[/bold]")
            console.print(output["stdout"])

        if output["stderr"]:
            console.print("\n[bold red]Stderr:[/bold red]")
            console.print(output["stderr"])


# --- MCP Tools ---


@mcp_app.command("servers")
def mcp_servers_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all configured MCP servers."""
    from .tools.mcp import get_mcp_manager

    manager = get_mcp_manager()
    status = manager.get_status()

    if json_output:
        print(json.dumps(status, indent=2))
    else:
        if not status["servers"]:
            console.print("[dim]No MCP servers configured[/dim]")
            console.print("\n[dim]Add servers via config file or mcp.connect tool[/dim]")
            return

        table = Table(title="MCP Servers")
        table.add_column("Name", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Tools", justify="right")
        table.add_column("Resources", justify="right")

        for name, info in status["servers"].items():
            status_color = {
                "connected": "green",
                "connecting": "yellow",
                "disconnected": "dim",
                "error": "red",
            }.get(info["status"], "white")
            status_text = f"[{status_color}]{info['status']}[/{status_color}]"
            table.add_row(name, status_text, str(info["tools"]), str(info["resources"]))

        console.print(table)
        console.print(f"\n[dim]Total tools: {status['total_tools']}[/dim]")


@mcp_app.command("tools")
def mcp_tools_cmd(
    server: str = typer.Option(None, "--server", "-s", help="Filter by server name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all available MCP tools."""
    from .tools.mcp import get_mcp_manager

    manager = get_mcp_manager()
    tools = manager.get_all_tools()

    if server:
        tools = [t for t in tools if t.server_name == server]

    if json_output:
        output = [{"name": t.name, "description": t.description, "server": t.server_name} for t in tools]
        print(json.dumps(output, indent=2))
    else:
        if not tools:
            console.print("[dim]No MCP tools available[/dim]")
            return

        table = Table(title="MCP Tools")
        table.add_column("Tool", style="cyan")
        table.add_column("Server", style="dim")
        table.add_column("Description")

        for tool in tools:
            table.add_row(tool.name, tool.server_name, tool.description or "")

        console.print(table)


@mcp_app.command("connect")
def mcp_connect_cmd(
    name: str = typer.Argument(..., help="Name of the server to connect"),
):
    """Connect to an MCP server."""
    from .tools.mcp import MCPServerStatus, get_mcp_manager

    manager = get_mcp_manager()
    server = manager.get_server(name)

    if not server:
        console.print(f"[red]Error:[/red] Server '{name}' not found")
        raise typer.Exit(code=1)

    with console.status(f"[bold cyan]Connecting to {name}...[/bold cyan]", spinner="dots"):
        success = server.connect()

    if success and server.status == MCPServerStatus.CONNECTED:
        console.print(f"[green]✓[/green] Connected to {name}")
        console.print(f"[dim]Available: {len(server.tools)} tools, {len(server.resources)} resources[/dim]")
    else:
        console.print(f"[red]✗[/red] Failed to connect to {name}")
        if server.error:
            console.print(f"[red]Error:[/red] {server.error}")
        raise typer.Exit(code=1)


@mcp_app.command("disconnect")
def mcp_disconnect_cmd(
    name: str = typer.Argument(..., help="Name of the server to disconnect"),
):
    """Disconnect from an MCP server."""
    from .tools.mcp import get_mcp_manager

    manager = get_mcp_manager()
    server = manager.get_server(name)

    if not server:
        console.print(f"[red]Error:[/red] Server '{name}' not found")
        raise typer.Exit(code=1)

    server.disconnect()
    console.print(f"[green]✓[/green] Disconnected from {name}")


# --- Image Tools ---


@image_app.command("read")
def image_read_cmd(
    path: str = typer.Argument(..., help="Path to the image file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read and display information about an image."""
    from .tools.image import read_image

    with console.status("[bold cyan]Reading image...[/bold cyan]", spinner="dots"):
        result = read_image(path=path)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        info = result.output
        console.print(Panel(
            f"[bold]Path:[/bold] {info['path']}\n"
            f"[bold]Format:[/bold] {info['format']}\n"
            f"[bold]Size:[/bold] {info['width']}x{info['height']} pixels\n"
            f"[bold]File size:[/bold] {info['file_size']} bytes",
            title="Image Info",
            border_style="cyan",
        ))


@image_app.command("analyze")
def image_analyze_cmd(
    path: str = typer.Argument(..., help="Path to the image file"),
    prompt: str = typer.Option("Describe this image in detail", "--prompt", "-p", help="Analysis prompt"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Analyze an image using vision AI."""
    from .tools.image import analyze_image

    with console.status("[bold cyan]Analyzing image...[/bold cyan]", spinner="dots"):
        result = analyze_image(path=path, prompt=prompt)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        console.print(Panel(
            result.output.get("analysis", "No analysis available"),
            title="Image Analysis",
            border_style="cyan",
        ))


@image_app.command("compare")
def image_compare_cmd(
    path1: str = typer.Argument(..., help="Path to first image"),
    path2: str = typer.Argument(..., help="Path to second image"),
    prompt: str = typer.Option("Compare these images and describe the differences", "--prompt", "-p"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Compare two images using vision AI."""
    from .tools.image import compare_images

    with console.status("[bold cyan]Comparing images...[/bold cyan]", spinner="dots"):
        result = compare_images(path1=path1, path2=path2, prompt=prompt)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        console.print(Panel(
            result.output.get("comparison", "No comparison available"),
            title="Image Comparison",
            border_style="cyan",
        ))


# --- Notebook Tools ---


@notebook_app.command("read")
def notebook_read_cmd(
    path: str = typer.Argument(..., help="Path to the Jupyter notebook"),
    cell: int = typer.Option(None, "--cell", "-c", help="Show only a specific cell (1-indexed)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read a Jupyter notebook."""
    from .tools.notebook import read_notebook

    result = read_notebook(path=path)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        nb = result.output
        console.print(f"[bold]{nb['path']}[/bold]")
        console.print(f"[dim]{nb['cell_count']} cells, {nb['code_cells']} code, {nb['markdown_cells']} markdown[/dim]")
        console.print()

        cells = nb["cells"]
        if cell is not None:
            if 1 <= cell <= len(cells):
                cells = [cells[cell - 1]]
            else:
                console.print(f"[red]Error:[/red] Cell {cell} not found (notebook has {len(cells)} cells)")
                raise typer.Exit(code=1)

        for i, c in enumerate(cells, 1 if cell is None else cell):
            cell_type_color = "green" if c["cell_type"] == "code" else "blue"
            console.print(f"[{cell_type_color}]In [{i}]:[/{cell_type_color}] ({c['cell_type']})")
            console.print(c["source"])
            if c.get("outputs"):
                console.print(f"[dim]Out [{i}]:[/dim]")
                for out in c["outputs"][:3]:
                    console.print(f"  {out.get('text', str(out)[:100])}")
            console.print()


@notebook_app.command("create")
def notebook_create_cmd(
    path: str = typer.Argument(..., help="Path for the new notebook"),
    kernel: str = typer.Option("python3", "--kernel", "-k", help="Kernel name"),
    force: bool = typer.Option(False, "--force", "-y", help="Overwrite if exists"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create a new Jupyter notebook."""
    from .tools.notebook import create_notebook

    if Path(path).exists() and not force:
        console.print(f"[red]Error:[/red] File already exists: {path}")
        console.print("[dim]Use --force to overwrite[/dim]")
        raise typer.Exit(code=1)

    result = create_notebook(path=path, kernel_name=kernel)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        console.print(f"[green]✓[/green] Created notebook: {result.output['path']}")


@notebook_app.command("execute")
def notebook_execute_cmd(
    path: str = typer.Argument(..., help="Path to the Jupyter notebook"),
    cell: int = typer.Option(None, "--cell", "-c", help="Execute only a specific cell (1-indexed)"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Execution timeout per cell in seconds"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Execute a Jupyter notebook."""
    from .tools.notebook import execute_notebook

    with console.status("[bold cyan]Executing notebook...[/bold cyan]", spinner="dots"):
        if cell is not None:
            result = execute_notebook(path=path, cell_index=cell - 1, timeout=timeout)
        else:
            result = execute_notebook(path=path, timeout=timeout)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        executed = output.get("executed_cells", output.get("executed", 1))
        console.print(f"[green]✓[/green] Executed {executed} cell(s)")
        if output.get("outputs"):
            console.print("\n[bold]Outputs:[/bold]")
            for out in output["outputs"][:5]:
                console.print(f"  {out}")


# --- Memory Tools ---


@memory_app.command("store")
def memory_store_cmd(
    content: str = typer.Argument(..., help="Content to store"),
    tags: list[str] = typer.Option(None, "--tag", "-t", help="Tags for the note (can repeat)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Store a note in memory."""
    from .tools.memory import store_note

    result = store_note(content=content, tags=tags or [])

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        console.print(f"[green]✓[/green] Stored note: {result.output['id']}")
        if tags:
            console.print(f"[dim]Tags: {', '.join(tags)}[/dim]")


@memory_app.command("recall")
def memory_recall_cmd(
    query: str = typer.Argument(None, help="Search query (optional)"),
    tags: list[str] = typer.Option(None, "--tag", "-t", help="Filter by tags (can repeat)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum notes to return"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Recall notes from memory."""
    from .tools.memory import recall_notes

    result = recall_notes(query=query, tags=tags or [], limit=limit)

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result.output, indent=2))
    else:
        notes = result.output.get("notes", [])
        if not notes:
            console.print("[dim]No notes found[/dim]")
            return

        console.print(f"[bold]Found {len(notes)} note(s):[/bold]\n")
        for note in notes:
            console.print(f"[cyan]{note['id']}[/cyan] [dim]({note.get('timestamp', 'unknown')})[/dim]")
            if note.get("tags"):
                console.print(f"  Tags: {', '.join(note['tags'])}")
            console.print(f"  {note['content'][:200]}{'...' if len(note.get('content', '')) > 200 else ''}")
            console.print()


@memory_app.command("clear")
def memory_clear_cmd(
    force: bool = typer.Option(False, "--force", "-y", help="Skip confirmation"),
):
    """Clear all notes from memory."""
    from .tools.memory import clear_memory

    if not force:
        if not _confirm("Clear all memory?"):
            console.print("[red]Cancelled[/red]")
            raise typer.Exit(code=0)

    result = clear_memory()

    if not result.success:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    console.print(f"[green]✓[/green] Memory cleared ({result.output.get('deleted', 0)} notes removed)")


# --- Additional Commands ---


@app.command()
def status():
    """Show system status overview."""
    from .tools.base import registry

    # Provider status
    console.print("[bold cyan]System Status[/bold cyan]\n")

    # Check providers
    console.print("[bold]Providers:[/bold]")
    from .llm import ProviderType, detect_available_providers
    available = detect_available_providers()
    for pt in ProviderType:
        status = "[green]✓[/green]" if pt in available else "[dim]✗[/dim]"
        console.print(f"  {status} {pt.value}")

    # Tool counts
    console.print(f"\n[bold]Tools:[/bold] {len(registry._tools)} registered")
    risk_counts = {}
    for tool in registry._tools.values():
        risk_counts[tool.risk_level] = risk_counts.get(tool.risk_level, 0) + 1
    for risk, count in sorted(risk_counts.items(), key=lambda x: x[0].value):
        color = get_risk_color(risk.value)
        console.print(f"  [{color}]{risk.value}[/{color}]: {count}")

    # MCP servers
    from .tools.mcp import get_mcp_manager
    manager = get_mcp_manager()
    servers = manager.list_servers()
    console.print(f"\n[bold]MCP Servers:[/bold] {len(servers)}")
    for srv in servers:
        status_color = "green" if srv.status.value == "connected" else "dim"
        console.print(f"  [{status_color}]{srv.name}[/{status_color}]: {srv.status.value}")

    # Project info
    project = detect_project()
    console.print(f"\n[bold]Project:[/bold] {project.name}")
    console.print(f"  Type: {project.type}")
    console.print(f"  Files: {len(project.files)}")
    if project.git_branch:
        console.print(f"  Branch: {project.git_branch}")


@app.command()
def completion(
    shell: str = typer.Argument(..., help="Shell type: bash, zsh, fish, powershell"),
):
    """Generate shell completion script."""

    shell_map = {
        "bash": "bash",
        "zsh": "zsh",
        "fish": "fish",
        "powershell": "powershell",
        "ps": "powershell",
    }

    shell_type = shell_map.get(shell.lower())
    if not shell_type:
        console.print(f"[red]Error:[/red] Unknown shell type: {shell}")
        console.print("[dim]Supported: bash, zsh, fish, powershell[/dim]")
        raise typer.Exit(code=1)

    # Typer's built-in completion
    console.print(f"[dim]# Add this to your ~/.{shell_type}rc or equivalent:[/dim]")
    console.print()

    if shell_type == "bash":
        console.print('eval "$(roura-agent --show-completion bash)"')
    elif shell_type == "zsh":
        console.print('eval "$(roura-agent --show-completion zsh)"')
    elif shell_type == "fish":
        console.print("roura-agent --show-completion fish | source")
    elif shell_type == "powershell":
        console.print("roura-agent --show-completion powershell | Out-String | Invoke-Expression")


# --- Helper Functions ---


def _print_diff(diff: str) -> None:
    """Print a colored diff using branding colors."""
    for line in diff.splitlines():
        console.print(format_diff_line(line))


def _confirm(prompt: str) -> bool:
    """Ask for confirmation."""
    console.print(f"[bold yellow]{prompt}[/bold yellow] (yes/no) ", end="")
    try:
        response = input().strip().lower()
        return response in ("yes", "y")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[red]Aborted[/red]")
        return False


def _error_panel(title: str, message: str, suggestion: str = None) -> None:
    """Display an error in a styled panel."""
    content = f"[red]{message}[/red]"
    if suggestion:
        content += f"\n\n[dim]Suggestion: {suggestion}[/dim]"
    console.print(Panel(
        content,
        title=f"[red]Error: {title}[/red]",
        border_style="red",
    ))


def _success_panel(title: str, message: str) -> None:
    """Display a success message in a styled panel."""
    console.print(Panel(
        f"[green]{message}[/green]",
        title=f"[green]{title}[/green]",
        border_style="green",
    ))


def _warning_panel(title: str, message: str) -> None:
    """Display a warning in a styled panel."""
    console.print(Panel(
        f"[yellow]{message}[/yellow]",
        title=f"[yellow]Warning: {title}[/yellow]",
        border_style="yellow",
    ))


def _info_panel(title: str, content: str) -> None:
    """Display information in a styled panel."""
    console.print(Panel(
        content,
        title=f"[cyan]{title}[/cyan]",
        border_style="cyan",
    ))


def _run_with_spinner(func, message: str, *args, **kwargs):
    """Run a function with a spinner, returning the result."""
    with console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots"):
        return func(*args, **kwargs)


def _enable_safe_mode() -> None:
    """
    Enable safe mode by disabling dangerous tools.

    This removes all tools with RiskLevel.DANGEROUS from the registry,
    preventing them from being called during the session.
    """
    from .tools.base import RiskLevel, registry

    # Get list of dangerous tools to remove
    dangerous_tools = [
        name for name, tool in registry._tools.items()
        if tool.risk_level == RiskLevel.DANGEROUS
    ]

    # Remove dangerous tools from registry
    for name in dangerous_tools:
        del registry._tools[name]


# Legacy commands for backward compatibility


@app.command(hidden=True)
def where():
    """Show current configuration (deprecated: use 'config')."""
    config()


@app.command(hidden=True)
def chat_once(prompt: str):
    """One-shot chat with the local model (deprecated)."""
    import time

    from .ollama import generate

    start = time.perf_counter()
    with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="dots"):
        response = generate(prompt)
    dur = time.perf_counter() - start

    console.print("\n[bold green]Response:[/bold green]")
    console.print(response)
    console.print(f"[dim]({dur:.2f}s)[/dim]")


@app.command(hidden=True)
def repl():
    """Interactive chat loop (deprecated: just run 'roura-agent')."""
    _run_agent()
