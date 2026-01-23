from __future__ import annotations

import os
import time
import typer
from rich.console import Console
from rich.table import Table

from .ollama import list_models, get_base_url, generate, chat
from .tools.doctor import run_all_checks, format_results, has_critical_failures
from .tools.fs import read_file, list_directory

app = typer.Typer(no_args_is_help=True)
fs_app = typer.Typer(help="Filesystem tools")
app.add_typer(fs_app, name="fs")
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
