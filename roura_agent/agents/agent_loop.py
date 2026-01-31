"""
Roura Agent Agent Loop - Agentic loop for specialized agents.

This provides each agent with its own tool-using loop, similar to the main
AgentLoop but scoped to the agent's allowed tools and capabilities.

© Roura.io
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from ..tools.base import registry as tool_registry
from ..tools.schema import tools_to_json_schema
from .base import AgentContext, AgentResult
from .executor import ExecutionContext, ToolPermissions

if TYPE_CHECKING:
    from ..llm import LLMProvider, LLMResponse


@dataclass
class AgentLoopConfig:
    """Configuration for an agent's agentic loop."""
    max_iterations: int = 10
    max_tool_calls_per_turn: int = 5
    stream_responses: bool = True
    show_tool_calls: bool = True
    show_tool_results: bool = True
    auto_approve_safe: bool = True  # Auto-approve SAFE tools
    require_approval_moderate: bool = True
    require_approval_dangerous: bool = True


class AgentLoop:
    """
    Agentic loop for specialized agents.

    This is a self-contained loop that:
    1. Sends messages to the LLM with tools schema
    2. Parses tool calls from LLM response
    3. Executes tools and collects results
    4. Feeds results back to LLM
    5. Repeats until LLM responds without tool calls or max iterations

    Each agent gets its own instance with configured permissions.
    """

    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        llm: LLMProvider,
        console: Optional[Console] = None,
        config: Optional[AgentLoopConfig] = None,
        allowed_tools: Optional[set[str]] = None,
        execution_context: Optional[ExecutionContext] = None,
        approval_callback: Optional[Callable[[str, dict], bool]] = None,
    ):
        """
        Initialize the agent loop.

        Args:
            agent_name: Name of the agent (for display and permissions)
            system_prompt: System prompt for this agent
            llm: LLM provider to use
            console: Console for output
            config: Loop configuration
            allowed_tools: Set of allowed tool names (defaults based on agent_name)
            execution_context: Shared execution context
            approval_callback: Callback for tool approval
        """
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.llm = llm
        self.console = console or Console()
        self.config = config or AgentLoopConfig()

        # Tool permissions
        self.allowed_tools = allowed_tools or ToolPermissions.get_for_agent(agent_name)

        # Shared context
        self.execution_context = execution_context or ExecutionContext()

        # Approval
        self.approval_callback = approval_callback

        # State
        self._messages: list[dict] = []
        self._interrupted = False
        self._iteration = 0
        self._tool_calls_this_turn = 0

    def get_available_tools(self) -> list:
        """Get list of tools this agent can use."""
        return [
            tool for tool in tool_registry.list_tools()
            if tool.name in self.allowed_tools
        ]

    def get_tools_schema(self) -> list[dict]:
        """Get JSON Schema for available tools."""
        tools = self.get_available_tools()
        return tools_to_json_schema(tools)

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        """
        Execute a tool with safety checks.

        Returns a dict with 'success', 'output', and 'error' keys.
        """
        from ..tools.base import RiskLevel

        # Check if tool is allowed
        if tool_name not in self.allowed_tools:
            return {
                'success': False,
                'output': None,
                'error': f"Tool '{tool_name}' not allowed for {self.agent_name}",
            }

        # Get the tool
        tool = tool_registry.get(tool_name)
        if not tool:
            return {
                'success': False,
                'output': None,
                'error': f"Unknown tool: {tool_name}",
            }

        # Check read-before-write
        if tool_name in ('fs.write', 'fs.edit'):
            path = args.get('path')
            if path and not self.execution_context.has_read(path):
                # Auto-read first
                read_tool = tool_registry.get('fs.read')
                if read_tool:
                    self.console.print(f"[dim]Auto-reading {path} first...[/dim]")
                    read_result = read_tool.execute(path=path)
                    if read_result.success:
                        content = read_result.output.get('content', '') if read_result.output else ''
                        self.execution_context.record_read(path, content)
                    else:
                        return {
                            'success': False,
                            'output': None,
                            'error': f"Must read file before modifying. Auto-read failed: {read_result.error}",
                        }

        # Check approval
        needs_approval = False
        if tool.risk_level == RiskLevel.DANGEROUS and self.config.require_approval_dangerous:
            needs_approval = True
        elif tool.risk_level == RiskLevel.MODERATE and self.config.require_approval_moderate:
            needs_approval = True

        if needs_approval and self.approval_callback:
            approved = self.approval_callback(tool_name, args)
            if not approved:
                return {
                    'success': False,
                    'output': None,
                    'error': f"Tool execution rejected: {tool_name}",
                }

        # Track old content for undo
        old_content = None
        if tool_name in ('fs.write', 'fs.edit'):
            path = args.get('path')
            if path:
                from pathlib import Path
                file_path = Path(path).resolve()
                if file_path.exists():
                    try:
                        old_content = file_path.read_text(encoding='utf-8', errors='replace')
                    except Exception:
                        pass

        # Execute
        try:
            result = tool.execute(**args)
        except Exception as e:
            return {
                'success': False,
                'output': None,
                'error': f"Tool error: {e}",
            }

        # Track reads
        if tool_name == 'fs.read' and result.success:
            path = args.get('path')
            content = result.output.get('content', '') if result.output else ''
            if path:
                self.execution_context.record_read(path, content)

        # Track modifications
        if tool_name in ('fs.write', 'fs.edit') and result.success:
            path = args.get('path')
            if path:
                from pathlib import Path
                file_path = Path(path).resolve()
                try:
                    new_content = file_path.read_text(encoding='utf-8', errors='replace')
                    self.execution_context.record_modification(
                        path=str(file_path),
                        old_content=old_content,
                        new_content=new_content,
                        action='modified' if old_content else 'created',
                    )
                except Exception:
                    pass

        # Record tool call
        self.execution_context.record_tool_call(tool_name, args, result)

        return result.to_dict()

    def _display_tool_call(self, tool_name: str, args: dict) -> None:
        """Display a tool call being executed."""
        if not self.config.show_tool_calls:
            return

        if tool_name == 'fs.read' and 'path' in args:
            self.console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{args['path']}[/dim]")
        elif tool_name == 'fs.write' and 'path' in args:
            self.console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{args['path']}[/dim]")
        elif tool_name == 'fs.edit' and 'path' in args:
            self.console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{args['path']}[/dim]")
        elif tool_name == 'shell.exec' and 'command' in args:
            cmd = args['command'][:50] + '...' if len(args.get('command', '')) > 50 else args.get('command', '')
            self.console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{cmd}[/dim]")
        else:
            self.console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold]")

    def _display_tool_result(self, tool_name: str, result: dict) -> None:
        """Display a tool result."""
        if not self.config.show_tool_results:
            return

        success = result.get('success', False)
        error = result.get('error')
        output = result.get('output')

        if success:
            icon = "✓"
            style = "green"
        else:
            icon = "✗"
            style = "red"

        if error:
            self.console.print(f"  [{style}]{icon} {error}[/{style}]")
        elif output:
            if tool_name == 'fs.read':
                lines = output.get('total_lines', 0) if isinstance(output, dict) else 0
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]Read {lines} lines[/dim]")
            elif tool_name == 'fs.list':
                count = output.get('count', 0) if isinstance(output, dict) else 0
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]Listed {count} entries[/dim]")
            elif tool_name in ('fs.write', 'fs.edit'):
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]File modified[/dim]")
            elif tool_name == 'shell.exec':
                exit_code = output.get('exit_code', -1) if isinstance(output, dict) else -1
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]Exit {exit_code}[/dim]")
            else:
                self.console.print(f"  [{style}]{icon}[/{style}]")
        else:
            self.console.print(f"  [{style}]{icon}[/{style}]")

    def _stream_response(self) -> LLMResponse:
        """Stream LLM response with live display."""
        tools_schema = self.get_tools_schema()
        content_buffer = ""
        final_response = None
        start_time = time.time()

        def get_thinking_display() -> Text:
            elapsed = time.time() - start_time
            return Text.from_markup(
                f"[cyan]⟳[/cyan] [{self.agent_name}] thinking... [dim]({elapsed:.1f}s)[/dim]"
            )

        with Live(
            get_thinking_display(),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            try:
                for response in self.llm.chat_stream(self._messages, tools_schema):
                    if response.content:
                        content_buffer = response.content
                        time.time() - start_time
                        display = Text()
                        display.append(content_buffer)
                        display.append("█", style="cyan bold")
                        live.update(display)
                    else:
                        live.update(get_thinking_display())

                    if response.done:
                        final_response = response
                        break
            except Exception as e:
                from ..llm import LLMResponse
                final_response = LLMResponse(
                    content=content_buffer,
                    error=str(e),
                    done=True,
                )

        if final_response is None:
            from ..llm import LLMResponse
            final_response = LLMResponse(content=content_buffer, done=True)

        return final_response

    def _process_turn(self) -> bool:
        """
        Process a single turn of the loop.

        Returns True if loop should continue, False if done.
        """
        self._iteration += 1
        self._tool_calls_this_turn = 0

        # Check iteration limit
        if self._iteration > self.config.max_iterations:
            self.console.print(f"[yellow]⚠ Max iterations ({self.config.max_iterations}) reached[/yellow]")
            return False

        # Get LLM response
        if self.config.stream_responses:
            response = self._stream_response()
        else:
            tools_schema = self.get_tools_schema()
            response = self.llm.chat(self._messages, tools_schema)

        if response.error:
            self.console.print(f"[red]✗ LLM Error: {response.error}[/red]")
            return False

        # Display content if any
        if response.content:
            self.console.print()
            try:
                self.console.print(Markdown(response.content))
            except Exception:
                self.console.print(response.content)

        # Add assistant message to context
        if response.content or response.tool_calls:
            tool_calls_data = []
            if response.tool_calls:
                for tc in response.tool_calls:
                    tool_calls_data.append({
                        'id': tc.id,
                        'type': 'function',
                        'function': {
                            'name': tc.name,
                            'arguments': json.dumps(tc.arguments),
                        }
                    })

            self._messages.append({
                'role': 'assistant',
                'content': response.content or '',
                'tool_calls': tool_calls_data if tool_calls_data else None,
            })

        # If no tool calls, we're done
        if not response.tool_calls:
            return False

        # Execute tool calls
        self.console.print()
        for tool_call in response.tool_calls:
            self._tool_calls_this_turn += 1

            if self._tool_calls_this_turn > self.config.max_tool_calls_per_turn:
                self.console.print(f"[yellow]⚠ Tool call limit reached ({self.config.max_tool_calls_per_turn})[/yellow]")
                break

            # Display and execute
            self._display_tool_call(tool_call.name, tool_call.arguments)
            result = self._execute_tool(tool_call.name, tool_call.arguments)
            self._display_tool_result(tool_call.name, result)

            # Add tool result to messages
            self._messages.append({
                'role': 'tool',
                'tool_call_id': tool_call.id,
                'content': json.dumps(result),
            })

        # Continue - LLM needs to process tool results
        return True

    def run(self, task: str, context: Optional[AgentContext] = None) -> AgentResult:
        """
        Run the agentic loop for a task.

        Args:
            task: The task description
            context: Optional context with additional info

        Returns:
            AgentResult with the final output
        """
        # Initialize messages
        self._messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': task},
        ]

        # Add context if provided
        if context:
            if context.project_root:
                self.execution_context.project_root = context.project_root
            if context.files_in_context:
                context_info = f"\n\nRelevant files in context: {', '.join(context.files_in_context)}"
                self._messages[0]['content'] += context_info

        # Reset state
        self._iteration = 0
        self._interrupted = False

        # Run the loop
        final_content = ""
        while True:
            should_continue = self._process_turn()

            # Capture last content
            for msg in reversed(self._messages):
                if msg.get('role') == 'assistant' and msg.get('content'):
                    final_content = msg['content']
                    break

            if not should_continue or self._interrupted:
                break

        # Build result
        return AgentResult(
            success=True,
            output=final_content,
            artifacts={
                'iterations': self._iteration,
                'files_read': list(self.execution_context.files_read.keys()),
                'files_modified': [m['path'] for m in self.execution_context.files_modified],
                'tool_calls': len(self.execution_context.tool_history),
            },
        )

    def interrupt(self) -> None:
        """Interrupt the current loop."""
        self._interrupted = True
