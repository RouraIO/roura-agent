"""
Roura Agent Tool Executor - Gives agents the ability to execute tools.

This module provides the ToolExecutorMixin that enables specialized agents
to use the same tools as the main AgentLoop (fs.read, fs.write, shell.exec, etc.)

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from rich.console import Console

from ..tools.base import RiskLevel, Tool, ToolResult
from ..tools.base import registry as tool_registry
from ..tools.schema import tools_to_json_schema

if TYPE_CHECKING:
    pass


@dataclass
class FileContext:
    """Tracks a file that has been read into context."""
    path: str
    content: str
    lines: int
    size: int


@dataclass
class ExecutionContext:
    """
    Shared context for tool execution across agents.

    Tracks:
    - Files that have been read (required before modification)
    - Files that have been modified (for undo)
    - Tool execution history
    """
    files_read: dict[str, FileContext] = field(default_factory=dict)
    files_modified: list[dict] = field(default_factory=list)
    tool_history: list[dict] = field(default_factory=list)
    project_root: Optional[str] = None

    def has_read(self, path: str) -> bool:
        """Check if a file has been read."""
        from pathlib import Path
        resolved = str(Path(path).resolve())
        return resolved in self.files_read

    def record_read(self, path: str, content: str) -> None:
        """Record that a file has been read."""
        from pathlib import Path
        resolved = str(Path(path).resolve())
        self.files_read[resolved] = FileContext(
            path=resolved,
            content=content,
            lines=content.count('\n') + 1,
            size=len(content.encode('utf-8')),
        )

    def record_modification(
        self,
        path: str,
        old_content: Optional[str],
        new_content: str,
        action: str,
    ) -> None:
        """Record a file modification for potential undo."""
        from pathlib import Path
        resolved = str(Path(path).resolve())
        self.files_modified.append({
            'path': resolved,
            'old_content': old_content,
            'new_content': new_content,
            'action': action,
        })

    def record_tool_call(
        self,
        tool_name: str,
        args: dict,
        result: ToolResult,
    ) -> None:
        """Record a tool execution."""
        self.tool_history.append({
            'tool': tool_name,
            'args': args,
            'success': result.success,
            'error': result.error,
        })


class ToolPermissions:
    """
    Defines which tools an agent is allowed to use.

    This enforces security boundaries - e.g., TestAgent shouldn't
    be able to commit code, GitAgent shouldn't write arbitrary files.
    """

    # Pre-defined permission sets for common agent types
    CODE_AGENT_TOOLS = {
        'fs.read', 'fs.list', 'fs.write', 'fs.edit',
        'glob.find', 'grep.search',
    }

    TEST_AGENT_TOOLS = {
        'fs.read', 'fs.list', 'fs.write', 'fs.edit',
        'shell.exec', 'glob.find', 'grep.search',
        'test.run', 'test.failures', 'test.coverage',
    }

    DEBUG_AGENT_TOOLS = {
        'fs.read', 'fs.list', 'fs.edit',
        'shell.exec', 'glob.find', 'grep.search',
    }

    GIT_AGENT_TOOLS = {
        'fs.read', 'fs.list',
        'git.status', 'git.diff', 'git.log',
        'git.add', 'git.commit',
    }

    REVIEW_AGENT_TOOLS = {
        'fs.read', 'fs.list',
        'glob.find', 'grep.search',
    }

    RESEARCH_AGENT_TOOLS = {
        'fs.read', 'fs.list',
        'glob.find', 'grep.search',
        'web.fetch', 'web.search',
    }

    # Full access for special agents
    ALL_TOOLS = set()  # Populated at runtime

    @classmethod
    def get_for_agent(cls, agent_type: str) -> set[str]:
        """Get the tool permissions for an agent type."""
        permissions = {
            'code': cls.CODE_AGENT_TOOLS,
            'test': cls.TEST_AGENT_TOOLS,
            'debug': cls.DEBUG_AGENT_TOOLS,
            'git': cls.GIT_AGENT_TOOLS,
            'review': cls.REVIEW_AGENT_TOOLS,
            'research': cls.RESEARCH_AGENT_TOOLS,
            'orchestrator': cls.ALL_TOOLS,
        }
        return permissions.get(agent_type, cls.CODE_AGENT_TOOLS)


class ToolExecutorMixin:
    """
    Mixin that gives agents the ability to execute tools.

    This mixin provides:
    - Access to the tool registry
    - Tool execution with safety checks
    - File read tracking (must read before write)
    - Approval callbacks for risky operations

    Usage:
        class MyAgent(BaseAgent, ToolExecutorMixin):
            def execute(self, context):
                # Initialize tool execution
                self.init_tool_executor(context)

                # Execute a tool
                result = self.execute_tool('fs.read', path='/some/file.py')

                # Or run a full agentic loop
                return self.run_tool_loop(context)
    """

    # These will be set by init_tool_executor
    _exec_context: Optional[ExecutionContext] = None
    _allowed_tools: set[str] = set()
    _approval_callback: Optional[Callable[[str, dict], bool]] = None
    _max_iterations: int = 10
    _console: Optional[Console] = None

    def init_tool_executor(
        self,
        context: Optional[ExecutionContext] = None,
        allowed_tools: Optional[set[str]] = None,
        approval_callback: Optional[Callable[[str, dict], bool]] = None,
        max_iterations: int = 10,
        console: Optional[Console] = None,
    ) -> None:
        """
        Initialize the tool executor.

        Args:
            context: Shared execution context (created if not provided)
            allowed_tools: Set of tool names this agent can use
            approval_callback: Function to call for approval (tool_name, args) -> bool
            max_iterations: Maximum iterations in agentic loop
            console: Console for output
        """
        self._exec_context = context or ExecutionContext()
        self._allowed_tools = allowed_tools or self._get_default_tools()
        self._approval_callback = approval_callback
        self._max_iterations = max_iterations
        self._console = console or Console()

        # Populate ALL_TOOLS if empty
        if not ToolPermissions.ALL_TOOLS:
            ToolPermissions.ALL_TOOLS = {t.name for t in tool_registry.list_tools()}

    def _get_default_tools(self) -> set[str]:
        """Get default tools based on agent name."""
        # Access agent's name attribute (from BaseAgent)
        agent_name = getattr(self, 'name', 'code')
        return ToolPermissions.get_for_agent(agent_name)

    def get_available_tools(self) -> list[Tool]:
        """Get list of tools this agent can use."""
        return [
            tool for tool in tool_registry.list_tools()
            if tool.name in self._allowed_tools
        ]

    def get_tools_schema(self) -> list[dict]:
        """Get JSON Schema for available tools (for LLM)."""
        tools = self.get_available_tools()
        return tools_to_json_schema(tools)

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if this agent can use a specific tool."""
        return tool_name in self._allowed_tools

    def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a tool with safety checks.

        This method:
        1. Checks if the tool is allowed
        2. Checks if files have been read before modification
        3. Requests approval for risky operations
        4. Executes the tool
        5. Tracks the execution

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments for the tool

        Returns:
            ToolResult from the tool execution
        """
        # Check if tool is allowed
        if not self.can_use_tool(tool_name):
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool '{tool_name}' not allowed for this agent",
            )

        # Get the tool
        tool = tool_registry.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Unknown tool: {tool_name}",
            )

        # Check read-before-write constraint
        if tool_name in ('fs.write', 'fs.edit'):
            path = kwargs.get('path')
            if path and not self._check_read_before_write(path):
                # Auto-read the file first
                read_result = self._auto_read_file(path)
                if not read_result.success:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"Must read file before modifying: {path}. Auto-read failed: {read_result.error}",
                    )

        # Check if approval needed
        if tool.risk_level in (RiskLevel.MODERATE, RiskLevel.DANGEROUS):
            if self._approval_callback:
                approved = self._approval_callback(tool_name, kwargs)
                if not approved:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"Tool execution rejected by user: {tool_name}",
                    )

        # Track old content for modifications
        old_content = None
        if tool_name in ('fs.write', 'fs.edit'):
            path = kwargs.get('path')
            if path:
                from pathlib import Path
                file_path = Path(path).resolve()
                if file_path.exists():
                    try:
                        old_content = file_path.read_text(encoding='utf-8', errors='replace')
                    except Exception:
                        pass

        # Execute the tool
        try:
            result = tool.execute(**kwargs)
        except Exception as e:
            result = ToolResult(
                success=False,
                output=None,
                error=f"Tool execution error: {e}",
            )

        # Track reads
        if tool_name == 'fs.read' and result.success:
            path = kwargs.get('path')
            content = result.output.get('content', '') if result.output else ''
            if path and self._exec_context:
                self._exec_context.record_read(path, content)

        # Track modifications
        if tool_name in ('fs.write', 'fs.edit') and result.success:
            path = kwargs.get('path')
            if path and self._exec_context:
                from pathlib import Path
                file_path = Path(path).resolve()
                try:
                    new_content = file_path.read_text(encoding='utf-8', errors='replace')
                    action = 'modified' if old_content else 'created'
                    self._exec_context.record_modification(
                        path=str(file_path),
                        old_content=old_content,
                        new_content=new_content,
                        action=action,
                    )
                except Exception:
                    pass

        # Record tool call
        if self._exec_context:
            self._exec_context.record_tool_call(tool_name, kwargs, result)

        return result

    def _check_read_before_write(self, path: str) -> bool:
        """Check if a file has been read before attempting to modify it."""
        if not self._exec_context:
            return False
        return self._exec_context.has_read(path)

    def _auto_read_file(self, path: str) -> ToolResult:
        """Automatically read a file into context."""
        from pathlib import Path
        file_path = Path(path).resolve()

        if not file_path.exists():
            # File doesn't exist - that's OK for writes
            return ToolResult(success=True, output={'new_file': True})

        # Read the file
        result = self.execute_tool('fs.read', path=str(file_path))
        return result

    def format_tool_result_for_llm(self, tool_name: str, result: ToolResult) -> str:
        """Format a tool result for inclusion in LLM context."""
        if result.success:
            if result.output:
                if isinstance(result.output, dict):
                    return json.dumps(result.output, indent=2)
                return str(result.output)
            return "Tool executed successfully"
        else:
            return f"Error: {result.error}"

    def display_tool_call(self, tool_name: str, args: dict) -> None:
        """Display a tool call being executed."""
        if not self._console:
            return

        # Format based on tool type
        if tool_name == 'fs.read' and 'path' in args:
            self._console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{args['path']}[/dim]")
        elif tool_name == 'fs.write' and 'path' in args:
            self._console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{args['path']}[/dim]")
        elif tool_name == 'fs.edit' and 'path' in args:
            self._console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{args['path']}[/dim]")
        elif tool_name == 'shell.exec' and 'command' in args:
            cmd = args['command'][:50] + '...' if len(args.get('command', '')) > 50 else args.get('command', '')
            self._console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold] [dim]{cmd}[/dim]")
        else:
            self._console.print(f"[cyan]▶[/cyan] [bold]{tool_name}[/bold]")

    def display_tool_result(self, tool_name: str, result: ToolResult) -> None:
        """Display a tool result."""
        if not self._console:
            return

        if result.success:
            icon = "✓"
            style = "green"
        else:
            icon = "✗"
            style = "red"

        if result.error:
            self._console.print(f"  [{style}]{icon} {result.error}[/{style}]")
        elif result.output:
            # Brief summary based on tool
            if tool_name == 'fs.read':
                lines = result.output.get('total_lines', 0)
                self._console.print(f"  [{style}]{icon}[/{style}] [dim]Read {lines} lines[/dim]")
            elif tool_name == 'fs.list':
                count = result.output.get('count', 0)
                self._console.print(f"  [{style}]{icon}[/{style}] [dim]Listed {count} entries[/dim]")
            elif tool_name in ('fs.write', 'fs.edit'):
                self._console.print(f"  [{style}]{icon}[/{style}] [dim]File modified[/dim]")
            elif tool_name == 'shell.exec':
                exit_code = result.output.get('exit_code', -1)
                self._console.print(f"  [{style}]{icon}[/{style}] [dim]Exit {exit_code}[/dim]")
            else:
                self._console.print(f"  [{style}]{icon}[/{style}]")
        else:
            self._console.print(f"  [{style}]{icon}[/{style}]")
