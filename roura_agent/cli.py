from __future__ import annotations

import os
import time
import typer
from rich.console import Console
from rich.table import Table

from .ollama import list_models, get_base_url, generate, chat
from .tools.doctor import run_all_checks, format_results, has_critical_failures

app = typer.Typer(no_args_is_help=True)
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
