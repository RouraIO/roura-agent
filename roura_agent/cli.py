from __future__ import annotations

import os
import time
import typer
from rich.console import Console
from rich.table import Table

from .ollama import list_models, get_base_url, generate, chat
from .tools.doctor import run_all_checks, format_results, has_critical_failures
from .tools.fs import read_file, list_directory, write_file, edit_file, fs_write, fs_edit
from .tools.git import get_status, get_diff, get_log

app = typer.Typer(no_args_is_help=True)
fs_app = typer.Typer(help="Filesystem tools")
git_app = typer.Typer(help="Git tools")
app.add_typer(fs_app, name="fs")
app.add_typer(git_app, name="git")
console = Console()


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Run system health diagnostics.
    """
    results = run_all_checks()
    output = format_results(results, use_json=json_output)
    console.print(output)

    if has_critical_failures(results):
        raise typer.Exit(code=1)


# --- Filesystem Tools ---


@fs_app.command("read")
def fs_read(
    path: str = typer.Argument(..., help="Path to the file to read"),
    offset: int = typer.Option(1, "--offset", "-o", help="Line number to start from (1-indexed)"),
    lines: int = typer.Option(0, "--lines", "-n", help="Number of lines to read (0 = all)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Read the contents of a file.
    """
    result = read_file(path=path, offset=offset, lines=lines)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
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
    """
    List contents of a directory.
    """
    result = list_directory(path=path, show_all=show_all)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
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
    """
    Write content to a file (requires approval).
    """
    # Get content from either --content or --from-file
    if content is None and content_file is None:
        console.print("[bold red]Error:[/bold red] Must provide --content or --from-file")
        raise typer.Exit(code=1)

    if content is not None and content_file is not None:
        console.print("[bold red]Error:[/bold red] Cannot use both --content and --from-file")
        raise typer.Exit(code=1)

    if content_file is not None:
        try:
            from pathlib import Path
            content = Path(content_file).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] Cannot read {content_file}: {e}")
            raise typer.Exit(code=1)

    # Generate preview
    preview = fs_write.preview(path=path, content=content)

    # Show what will happen
    if preview["exists"]:
        action_str = "[yellow]OVERWRITE[/yellow]"
    else:
        action_str = "[green]CREATE[/green]"

    lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    bytes_count = len(content.encode("utf-8"))

    console.print(f"\n{action_str} {preview['path']}")
    console.print(f"[dim]{lines} lines, {bytes_count} bytes[/dim]")

    # Show diff for existing files
    if preview["diff"]:
        console.print("\n[bold]Diff:[/bold]")
        for line in preview["diff"].splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/cyan]")
            else:
                console.print(line)
    elif not preview["exists"]:
        # Show content preview for new files
        console.print("\n[bold]Content preview:[/bold]")
        preview_lines = content.splitlines()[:10]
        for i, line in enumerate(preview_lines, 1):
            console.print(f"[green]+{i:4d} | {line}[/green]")
        if len(content.splitlines()) > 10:
            console.print(f"[dim]... and {len(content.splitlines()) - 10} more lines[/dim]")

    console.print()

    # Dry run stops here
    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    # Approval gate
    if not force:
        console.print("[bold yellow]APPROVE_WRITE?[/bold yellow] (yes/no) ", end="")
        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[red]Aborted[/red]")
            raise typer.Exit(code=1)

        if response not in ("yes", "y"):
            console.print("[red]Write cancelled[/red]")
            raise typer.Exit(code=0)

    # Execute write
    result = write_file(path=path, content=content, create_dirs=create_dirs)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[green]✓[/green] {output['action'].capitalize()} {output['path']}")
        console.print(f"[dim]{output['lines']} lines, {output['bytes']} bytes[/dim]")


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
    """
    Edit a file by replacing text (requires approval).
    """
    # Generate preview
    preview = fs_edit.preview(path=path, old_text=old_text, new_text=new_text, replace_all=replace_all)

    # Check for errors
    if preview["error"]:
        if "not found" in preview["error"].lower() or "ambiguous" in preview["error"].lower():
            console.print(f"[bold red]Error:[/bold red] {preview['error']}")
            if preview["occurrences"] > 1:
                console.print(f"[dim]Found {preview['occurrences']} occurrences. Use --replace-all or provide more context.[/dim]")
            raise typer.Exit(code=1)

    # Show what will happen
    console.print(f"\n[yellow]EDIT[/yellow] {preview['path']}")
    console.print(f"[dim]Replacing {preview['would_replace']} occurrence(s)[/dim]")

    # Show diff
    if preview["diff"]:
        console.print("\n[bold]Diff:[/bold]")
        for line in preview["diff"].splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/cyan]")
            else:
                console.print(line)

    console.print()

    # Dry run stops here
    if dry_run:
        console.print("[dim]Dry run - no changes made[/dim]")
        return

    # Approval gate
    if not force:
        console.print("[bold yellow]APPROVE_EDIT?[/bold yellow] (yes/no) ", end="")
        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[red]Aborted[/red]")
            raise typer.Exit(code=1)

        if response not in ("yes", "y"):
            console.print("[red]Edit cancelled[/red]")
            raise typer.Exit(code=0)

    # Execute edit
    result = edit_file(path=path, old_text=old_text, new_text=new_text, replace_all=replace_all)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
        print(json.dumps(result.output, indent=2))
    else:
        output = result.output
        console.print(f"[green]✓[/green] Edited {output['path']}")
        console.print(f"[dim]{output['replacements']} replacement(s) made[/dim]")


# --- Git Tools ---


@git_app.command("status")
def git_status_cmd(
    path: str = typer.Argument(".", help="Path to repository"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show the working tree status.
    """
    result = get_status(path=path)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
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
    """
    Show changes between commits, commit and working tree, etc.
    """
    result = get_diff(path=path, staged=staged, commit=commit)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
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
            # Color the diff output
            for line in output["diff"].splitlines():
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


@git_app.command("log")
def git_log_cmd(
    path: str = typer.Argument(".", help="Path to repository"),
    count: int = typer.Option(10, "--count", "-n", help="Number of commits to show"),
    oneline: bool = typer.Option(False, "--oneline", help="Show one line per commit"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show commit logs.
    """
    result = get_log(path=path, count=count, oneline=oneline)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(code=1)

    if json_output:
        import json
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


@app.command()
def ping():
    """
    Ping Ollama and list available models.
    """
    base = get_base_url()
    models = list_models(base)

    table = Table(title=f"Ollama @ {base}")
    table.add_column("Model")
    for m in models:
        table.add_row(m)

    console.print(table)


@app.command()
def where():
    """
    Show current configuration.
    """
    console.print(f"OLLAMA_BASE_URL={os.getenv('OLLAMA_BASE_URL', '')}")
    console.print(f"OLLAMA_MODEL={os.getenv('OLLAMA_MODEL', '')}")


@app.command()
def chat_once(prompt: str):
    """
    One-shot chat with the local model.
    """
    start = time.perf_counter()
    with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="dots"):
        response = generate(prompt)
    dur = time.perf_counter() - start

    console.print("\n[bold green]Model:[/bold green]")
    console.print(response)
    console.print(f"[dim]({dur:.2f}s)[/dim]")


@app.command()
def repl():
    """
    Interactive chat loop with memory.
    Type 'exit' or 'quit' to leave.
    """
    console.print("[bold cyan]roura-agent REPL[/bold cyan] (type 'exit' to quit)\n")

    messages = [
        {
            "role": "system",
            "content": "You are roura-agent, a local coding assistant similar to Claude Code. Be concise, precise, and helpful.",
        }
    ]

    while True:
        try:
            prompt = input("> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting.")
            break

        if prompt.strip().lower() in {"exit", "quit"}:
            console.print("Goodbye.")
            break

        if not prompt.strip():
            continue

        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()
        try:
            with console.status("[bold cyan]Thinking...[/bold cyan]", spinner="dots"):
                response = chat(messages)
            dur = time.perf_counter() - start

            messages.append({"role": "assistant", "content": response})
            console.print(f"\n[bold green]Model:[/bold green]\n{response}")
            console.print(f"[dim]({dur:.2f}s)[/dim]\n")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
