"""
Roura Agent CLI - Local-first AI coding assistant.

© Roura.io
"""
from __future__ import annotations

import os
import sys
import json
import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm

from .ollama import list_models, get_base_url, get_model
from .tools.doctor import run_all_checks, format_results, has_critical_failures
from .tools.fs import read_file, list_directory, write_file, edit_file, fs_write, fs_edit
from .tools.git import get_status, get_diff, get_log, stage_files, create_commit, git_add, git_commit
from .tools.shell import run_command, shell_exec
from .tools.base import registry
from .config import (
    load_config, save_config, load_credentials, save_credentials,
    apply_config_to_env, get_effective_config, detect_project,
    Config, Credentials, CONFIG_FILE, CREDENTIALS_FILE,
)

# Import these to ensure tools are registered
from .tools import github, jira

app = typer.Typer(invoke_without_command=True)
fs_app = typer.Typer(help="Filesystem tools")
git_app = typer.Typer(help="Git tools")
shell_app = typer.Typer(help="Shell tools")
app.add_typer(fs_app, name="fs")
app.add_typer(git_app, name="git")
app.add_typer(shell_app, name="shell")
console = Console()

# ASCII Art Logo
LOGO = """
[cyan]
 ██████╗  ██████╗ ██╗   ██╗██████╗  █████╗
 ██╔══██╗██╔═══██╗██║   ██║██╔══██╗██╔══██╗
 ██████╔╝██║   ██║██║   ██║██████╔╝███████║
 ██╔══██╗██║   ██║██║   ██║██╔══██╗██╔══██║
 ██║  ██║╚██████╔╝╚██████╔╝██║  ██║██║  ██║
 ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
[/cyan][dim]  Local AI Coding Assistant • roura.io[/dim]
"""


@app.callback()
def main(ctx: typer.Context):
    """
    Roura Agent - Local-first AI coding assistant by Roura.io.
    """
    # If no command given, launch interactive agent
    if ctx.invoked_subcommand is None:
        _run_agent()


def _run_agent():
    """Launch the interactive agent."""
    from .agent.loop import AgentLoop, AgentConfig as LoopConfig

    # Load and apply configuration
    config, creds = get_effective_config()
    apply_config_to_env(config, creds)

    # Display logo
    console.print(LOGO)

    # Quick health check
    model = get_model()
    if not model:
        console.print("[red]Error:[/red] OLLAMA_MODEL not set")
        console.print("[dim]Run 'roura-agent setup' to configure, or:[/dim]")
        console.print("[dim]  export OLLAMA_MODEL=qwen2.5-coder:32b[/dim]")
        raise typer.Exit(1)

    # Detect project
    project = detect_project()

    # Show config and project info
    console.print(f"[dim]Model: {model}[/dim]")
    console.print(f"[dim]Endpoint: {get_base_url()}[/dim]")
    console.print(f"[bold cyan]Project:[/bold cyan] {project.name} [dim]({project.type})[/dim]")
    if project.git_branch:
        console.print(f"[dim]Branch: {project.git_branch} • {len(project.files)} files[/dim]")
    console.print()

    # Run agent
    loop_config = LoopConfig(
        max_tool_calls=3,
        require_plan_approval=True,
        require_tool_approval=True,
        stream_responses=True,
    )

    agent = AgentLoop(console=console, config=loop_config, project=project)
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
    table.add_column("Tool", style="cyan")
    table.add_column("Risk", justify="center")
    table.add_column("Description")

    from .tools.base import RiskLevel

    risk_colors = {
        RiskLevel.SAFE: "green",
        RiskLevel.MODERATE: "yellow",
        RiskLevel.DANGEROUS: "red",
    }

    for name, tool in sorted(registry._tools.items()):
        color = risk_colors.get(tool.risk_level, "white")
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
    console.print(f"[dim]Run 'roura-agent setup' to configure interactively[/dim]")


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
            console.print(f"[green]✓[/green] Command succeeded")
        else:
            console.print(f"[yellow]Exit code: {output['exit_code']}[/yellow]")

        if output["stdout"]:
            console.print("\n[bold]Output:[/bold]")
            console.print(output["stdout"])

        if output["stderr"]:
            console.print("\n[bold red]Stderr:[/bold red]")
            console.print(output["stderr"])


# --- Helper Functions ---


def _print_diff(diff: str) -> None:
    """Print a colored diff."""
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        elif line.startswith("diff ") or line.startswith("index "):
            console.print(f"[bold]{line}[/bold]")
        else:
            console.print(line)


def _confirm(prompt: str) -> bool:
    """Ask for confirmation."""
    console.print(f"[bold yellow]{prompt}[/bold yellow] (yes/no) ", end="")
    try:
        response = input().strip().lower()
        return response in ("yes", "y")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[red]Aborted[/red]")
        return False


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
