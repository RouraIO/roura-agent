"""
Roura Agent Loop - Core agent with safety constraints.

Constraints:
1. Always propose a plan before acting
2. Never execute tools without approval
3. Show diffs before commits
4. Summarize actions
5. Max 3 tool calls without re-checking
6. Never hallucinate file contents
7. Never modify files not read
8. ESC to interrupt
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.table import Table

from .context import AgentContext
from .planner import Planner, Plan, PlanStep, StepType
from ..stream import stream_chat_live, StreamResult
from ..tools.base import registry, ToolResult, RiskLevel


class AgentState(Enum):
    """Agent state machine states."""
    IDLE = "idle"
    UNDERSTANDING = "understanding"
    GATHERING = "gathering"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Agent configuration."""
    max_tool_calls: int = 3
    require_plan_approval: bool = True
    require_tool_approval: bool = True
    stream_responses: bool = True
    show_thinking: bool = False
    auto_read_on_modify: bool = True  # Automatically read files before allowing edits


@dataclass
class ExecutionResult:
    """Result of executing a plan step."""
    step: PlanStep
    success: bool
    output: Any = None
    error: Optional[str] = None


class AgentLoop:
    """
    Main agent loop with safety constraints.

    Usage:
        agent = AgentLoop()
        agent.run()  # Interactive REPL
        # or
        agent.process("Fix the bug in main.py")  # Single request
    """

    BASE_SYSTEM_PROMPT = """You are Roura Agent, a local-first AI coding assistant created by Roura.io.

You help developers with:
- Reading and understanding code
- Writing and editing files
- Running shell commands
- Git operations
- GitHub and Jira integrations

IMPORTANT RULES:
1. Always explain what you plan to do BEFORE doing it
2. When asked to modify a file, READ it first to understand context
3. Show diffs and previews before making changes
4. Be concise but thorough
5. Ask for clarification when the request is ambiguous

You have access to these tools:
- fs.read: Read file contents
- fs.list: List directory contents
- fs.write: Write/create files (requires approval)
- fs.edit: Edit files with search/replace (requires approval)
- git.status: Show git status
- git.diff: Show git diff
- git.log: Show commit history
- git.add: Stage files (requires approval)
- git.commit: Create commits (requires approval)
- shell.exec: Run shell commands (requires approval)

When you need to use a tool, respond with a JSON block:
```tool
{"tool": "tool.name", "args": {"arg1": "value1"}}
```

For multiple tools, use multiple blocks.

The user is working in a specific project directory. You can reference files by their relative path from the project root. When they ask to "review X" or "look at X", find the matching file in the project.

Always think step by step and explain your reasoning."""

    def __init__(
        self,
        console: Optional[Console] = None,
        config: Optional[AgentConfig] = None,
        project: Optional[Any] = None,
    ):
        self.console = console or Console()
        self.config = config or AgentConfig()
        self.context = AgentContext(max_tool_calls=self.config.max_tool_calls)
        self.planner = Planner(self.console)
        self.state = AgentState.IDLE
        self._interrupted = False
        self.project = project

        # Build system prompt with project context
        system_prompt = self.BASE_SYSTEM_PROMPT

        if project:
            from ..config import get_project_context_prompt
            project_context = get_project_context_prompt(project)
            system_prompt += f"\n\n{project_context}"

            # Set context cwd
            self.context.cwd = str(project.root)
            self.context.project_root = str(project.root)

        # Initialize system message
        self.context.add_message("system", system_prompt)

    def _extract_tool_calls(self, text: str) -> list[dict]:
        """Extract tool calls from response text."""
        tool_calls = []

        # Match ```tool ... ``` blocks
        pattern = r"```tool\s*\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match.strip())
                if "tool" in data:
                    tool_calls.append(data)
            except json.JSONDecodeError:
                continue

        return tool_calls

    def _execute_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Execute a single tool with constraint checking."""
        # Get tool from registry
        tool = registry.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Unknown tool: {tool_name}",
            )

        # Constraint #7: Check if we can modify this file
        if tool_name in ("fs.write", "fs.edit"):
            path = args.get("path")
            if path:
                can_modify, reason = self.context.can_modify(path)
                if not can_modify:
                    # Auto-read if configured
                    if self.config.auto_read_on_modify:
                        self.console.print(f"[dim]Auto-reading {path} first...[/dim]")
                        read_result = self._execute_tool("fs.read", {"path": path})
                        if not read_result.success:
                            return ToolResult(
                                success=False,
                                output=None,
                                error=f"Cannot modify: {reason}. Auto-read failed: {read_result.error}",
                            )
                    else:
                        return ToolResult(
                            success=False,
                            output=None,
                            error=reason,
                        )

        # Constraint #5: Check tool call limit
        if not self.context.increment_tool_calls():
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool call limit reached ({self.config.max_tool_calls}). Please confirm to continue.",
            )

        # Execute the tool
        try:
            result = tool.execute(**args)

            # Track reads in context
            if tool_name == "fs.read" and result.success:
                path = args.get("path")
                content = result.output.get("content", "") if result.output else ""
                self.context.add_to_read_set(path, content)

            return result

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def _display_tool_result(self, tool_name: str, result: ToolResult) -> None:
        """Display a tool result nicely."""
        if result.success:
            icon = "✓"
            style = "green"
        else:
            icon = "✗"
            style = "red"

        self.console.print(f"[{style}]{icon}[/{style}] [bold]{tool_name}[/bold]")

        if result.error:
            self.console.print(f"  [red]{result.error}[/red]")
        elif result.output:
            # Format output based on tool
            if tool_name == "fs.read":
                lines = result.output.get("total_lines", 0)
                path = result.output.get("path", "")
                self.console.print(f"  [dim]Read {lines} lines from {Path(path).name}[/dim]")
            elif tool_name == "fs.list":
                count = result.output.get("count", 0)
                self.console.print(f"  [dim]Listed {count} entries[/dim]")
            elif tool_name in ("fs.write", "fs.edit"):
                path = result.output.get("path", "")
                self.console.print(f"  [dim]Modified {Path(path).name}[/dim]")
            elif tool_name == "shell.exec":
                exit_code = result.output.get("exit_code", -1)
                if exit_code == 0:
                    self.console.print(f"  [dim]Command succeeded[/dim]")
                    if result.output.get("stdout"):
                        # Show first few lines
                        lines = result.output["stdout"].splitlines()[:5]
                        for line in lines:
                            self.console.print(f"  [dim]{line}[/dim]")
                        if len(result.output["stdout"].splitlines()) > 5:
                            self.console.print(f"  [dim]... ({len(result.output['stdout'].splitlines())} lines)[/dim]")
                else:
                    self.console.print(f"  [yellow]Exit code: {exit_code}[/yellow]")
                    if result.output.get("stderr"):
                        self.console.print(f"  [red]{result.output['stderr'][:200]}[/red]")
            else:
                # Generic output
                if isinstance(result.output, dict):
                    for key, value in list(result.output.items())[:3]:
                        if not isinstance(value, (dict, list)) or len(str(value)) < 50:
                            self.console.print(f"  [dim]{key}: {value}[/dim]")

    def _request_approval(self, action: str, details: str = "") -> bool:
        """Request user approval for an action."""
        self.console.print()
        self.console.print(Panel(
            f"{details}" if details else action,
            title=f"[bold yellow]⚠ {action}[/bold yellow]",
            border_style="yellow",
        ))

        try:
            response = Prompt.ask(
                "[bold yellow]APPROVE?[/bold yellow]",
                choices=["yes", "no", "y", "n"],
                default="no",
            )
            return response.lower() in ("yes", "y")
        except (EOFError, KeyboardInterrupt):
            self.console.print("\n[red]Cancelled[/red]")
            return False

    def _stream_response(self, user_input: str) -> StreamResult:
        """Get streaming response from LLM with live token display."""
        self.context.add_message("user", user_input)
        messages = self.context.get_messages_for_llm()

        self.console.print()

        # Use live streaming - handles display internally
        result = stream_chat_live(messages, console=self.console)

        # Add to context if we got content
        if result.content:
            self.context.add_message("assistant", result.content)

        return result

    def process(self, user_input: str) -> str:
        """
        Process a single user request through the full loop.

        Returns the final response/summary.
        """
        self._interrupted = False
        self.context.reset_tool_calls()

        # 1. UNDERSTAND & RESPOND
        self.state = AgentState.UNDERSTANDING
        result = self._stream_response(user_input)

        if result.interrupted or result.error:
            return result.content or ""

        # 2. EXTRACT & EXECUTE TOOL CALLS
        tool_calls = self._extract_tool_calls(result.content)

        if tool_calls:
            self.state = AgentState.EXECUTING
            self.console.print()
            self.console.print("[bold]Tool Calls:[/bold]")

            for call in tool_calls:
                tool_name = call.get("tool")
                args = call.get("args", {})

                # Get tool to check risk level
                tool = registry.get(tool_name)
                needs_approval = tool and tool.risk_level != RiskLevel.SAFE

                # Constraint #2: Request approval for risky tools
                if needs_approval and self.config.require_tool_approval:
                    approved = self._request_approval(
                        f"Execute {tool_name}",
                        f"Args: {json.dumps(args, indent=2)}",
                    )
                    if not approved:
                        self.console.print(f"[yellow]Skipped {tool_name}[/yellow]")
                        continue

                # Execute
                tool_result = self._execute_tool(tool_name, args)
                self._display_tool_result(tool_name, tool_result)

                # Check if we hit the limit
                if self.context.needs_user_check():
                    self.console.print()
                    self.console.print("[yellow]Tool call limit reached. Continue?[/yellow]")
                    if not Confirm.ask("Continue"):
                        break
                    self.context.reset_tool_calls()

        # 3. SUMMARIZE
        self.state = AgentState.SUMMARIZING
        if self.context.read_set or tool_calls:
            self.console.print()
            self.console.print(f"[dim]{self.context.get_context_summary()}[/dim]")

        self.state = AgentState.IDLE
        return result.content or ""

    def run(self) -> None:
        """Run the interactive REPL."""
        self.console.print()
        self.console.print(Panel(
            "[bold]Roura Agent[/bold] - Local AI Coding Assistant\n\n"
            "Type your request, or:\n"
            "  [cyan]/help[/cyan]    - Show commands\n"
            "  [cyan]/context[/cyan] - Show loaded files\n"
            "  [cyan]/clear[/cyan]   - Clear context\n"
            "  [cyan]exit[/cyan]     - Quit",
            title="[bold cyan]🚀 Roura.io[/bold cyan]",
            border_style="cyan",
        ))
        self.console.print()

        while True:
            try:
                # Prompt
                prompt_text = "[bold cyan]>[/bold cyan] "
                user_input = self.console.input(prompt_text).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                    self.console.print("[dim]Goodbye![/dim]")
                    break

                if user_input.lower() in ("/help", "/h", "help"):
                    self._show_help()
                    continue

                if user_input.lower() in ("/context", "/ctx"):
                    self._show_context()
                    continue

                if user_input.lower() in ("/clear", "/reset"):
                    self.context.clear()
                    self.console.print("[dim]Context cleared[/dim]")
                    continue

                if user_input.lower() in ("/tools",):
                    self._show_tools()
                    continue

                # Process request
                self.process(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Use 'exit' to quit[/dim]")
            except EOFError:
                self.console.print("\n[dim]Goodbye![/dim]")
                break

    def _show_help(self) -> None:
        """Show help information."""
        self.console.print(Panel(
            "[bold]Commands:[/bold]\n"
            "  /help     - Show this help\n"
            "  /context  - Show loaded file context\n"
            "  /clear    - Clear conversation and context\n"
            "  /tools    - List available tools\n"
            "  exit      - Quit\n\n"
            "[bold]Tips:[/bold]\n"
            "  • Press ESC to interrupt generation\n"
            "  • Ask to read files before editing\n"
            "  • Request a plan for complex tasks\n"
            "  • Use natural language - be specific!",
            title="[bold]Help[/bold]",
            border_style="blue",
        ))

    def _show_context(self) -> None:
        """Show current context."""
        if not self.context.read_set:
            self.console.print("[dim]No files loaded[/dim]")
            return

        table = Table(title="Files in Context")
        table.add_column("File", style="cyan")
        table.add_column("Lines", justify="right")
        table.add_column("Size", justify="right")

        for path, ctx in self.context.read_set.items():
            name = Path(path).name
            table.add_row(name, str(ctx.lines), f"{ctx.size:,} B")

        self.console.print(table)

    def _show_tools(self) -> None:
        """Show available tools."""
        table = Table(title="Available Tools")
        table.add_column("Tool", style="cyan")
        table.add_column("Risk", justify="center")
        table.add_column("Description")

        risk_colors = {
            RiskLevel.SAFE: "green",
            RiskLevel.MODERATE: "yellow",
            RiskLevel.DANGEROUS: "red",
        }

        for name, tool in sorted(registry._tools.items()):
            color = risk_colors.get(tool.risk_level, "white")
            risk_text = f"[{color}]{tool.risk_level.value}[/{color}]"
            table.add_row(name, risk_text, tool.description)

        self.console.print(table)
