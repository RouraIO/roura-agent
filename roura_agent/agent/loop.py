"""
Roura Agent Loop - Multi-turn agentic loop with native tool calling.

This is the core agentic loop that makes Roura Agent work like Claude Code:
1. User input → LLM (with tools schema)
2. If tool_calls: Execute → Add results → Loop back to LLM
3. If text only: Display → Done

Constraints:
1. Always propose a plan before acting
2. Never execute tools without approval (for MODERATE/DANGEROUS)
3. Show diffs before commits
4. Summarize actions
5. Max tool calls per turn limit
6. Never hallucinate file contents
7. Never modify files not read
8. ESC to interrupt

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.console import Group

from .context import AgentContext
from .summarizer import ContextSummarizer
from ..llm import LLMProvider, LLMResponse, ToolCall, get_provider, ProviderType
from ..tools.base import registry, ToolResult, RiskLevel
from ..tools.schema import registry_to_json_schema
from ..stream import check_for_escape
from ..errors import RouraError, ErrorCode
from ..branding import Colors, Icons, Styles, format_error
from ..session import SessionManager, Session


class AgentState(Enum):
    """Agent state machine states."""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING_TOOLS = "executing_tools"
    AWAITING_APPROVAL = "awaiting_approval"
    SUMMARIZING = "summarizing"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Agent configuration."""
    max_iterations: int = 50
    max_tool_calls_per_turn: int = 10
    require_approval_moderate: bool = True
    require_approval_dangerous: bool = True
    auto_read_on_modify: bool = True
    stream_responses: bool = True
    show_tool_results: bool = True


class AgentLoop:
    """
    Multi-turn agentic loop with native tool calling.

    This implements the core agentic pattern:
    - LLM reasons about the task and decides which tools to call
    - Tools are executed and results fed back to the LLM
    - LLM continues reasoning until task is complete

    Usage:
        agent = AgentLoop()
        agent.run()  # Interactive REPL
        # or
        agent.process("Fix the bug in main.py")  # Single request
    """

    BASE_SYSTEM_PROMPT = """You are Roura Agent, a powerful local-first AI coding assistant created by Roura.io.

You operate in an agentic loop: you can use tools to accomplish tasks, see the results, and continue working until the task is complete. You are not limited to a single response - you can execute multiple tools and reason about results iteratively.

## Your Capabilities
- Read and understand code in any language
- Write, edit, and create files
- Run shell commands
- Git operations (status, diff, commit, etc.)
- GitHub and Jira integrations (when configured)

## How You Work
1. When given a task, think about what information you need
2. Use tools to gather information (read files, list directories, etc.)
3. Analyze the results and decide on next steps
4. Make changes using appropriate tools
5. Verify your changes if needed
6. Report back when done

## Available Tools
You have access to tools via native function calling. The tools will be provided in the API request. Key tools include:
- fs.read: Read file contents
- fs.list: List directory contents
- fs.write: Write/create files
- fs.edit: Edit files with search/replace
- git.status, git.diff, git.log: Git information
- git.add, git.commit: Git modifications
- shell.exec: Run shell commands

## Important Rules
1. ALWAYS read a file before modifying it - never guess at contents
2. When editing, use precise search/replace patterns that match exactly
3. For multi-step tasks, work through them systematically
4. If a tool fails, analyze the error and try a different approach
5. Be concise in your responses but thorough in your work
6. Ask for clarification if the task is ambiguous

## Project Context
You are working in a project directory. Reference files by their path relative to the project root."""

    def __init__(
        self,
        console: Optional[Console] = None,
        config: Optional[AgentConfig] = None,
        project: Optional[Any] = None,
    ):
        self.console = console or Console()
        self.config = config or AgentConfig()
        self.context = AgentContext(
            max_iterations=self.config.max_iterations,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
        )
        self.state = AgentState.IDLE
        self._interrupted = False
        self.project = project
        self._llm: Optional[LLMProvider] = None
        self._provider_type: Optional[ProviderType] = None
        self._summarizer = ContextSummarizer()
        self._session_manager = SessionManager()
        self._current_session: Optional[Session] = None

        # Build system prompt with project context
        system_prompt = self.BASE_SYSTEM_PROMPT

        if project:
            from ..config import get_project_context_prompt
            project_context = get_project_context_prompt(project)
            system_prompt += f"\n\n{project_context}"
            self.context.cwd = str(project.root)
            self.context.project_root = str(project.root)

        # Initialize system message
        self.context.add_message("system", system_prompt)

    def _get_llm(self) -> LLMProvider:
        """Get or create LLM provider (lazy initialization)."""
        if self._llm is None:
            self._llm = get_provider(self._provider_type)
        return self._llm

    def set_provider(self, provider_type: ProviderType) -> None:
        """Set the provider type before first use."""
        self._provider_type = provider_type
        self._llm = None  # Clear cached provider

    def _get_tools_schema(self) -> list[dict]:
        """Get JSON Schema for all registered tools."""
        return registry_to_json_schema(registry)

    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool with constraint checking and undo tracking."""
        tool_name = tool_call.name
        args = tool_call.arguments

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
                        self.console.print(f"[{Colors.DIM}]Auto-reading {path} first...[/{Colors.DIM}]")
                        read_call = ToolCall(id="auto_read", name="fs.read", arguments={"path": path})
                        read_result = self._execute_tool(read_call)
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

        # Track old content for undo (before modification)
        old_content = None
        file_existed = False
        if tool_name in ("fs.write", "fs.edit"):
            path = args.get("path")
            if path:
                from pathlib import Path as PathLib
                file_path = PathLib(path).resolve()
                file_existed = file_path.exists()
                if file_existed:
                    try:
                        old_content = file_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass

        # Execute the tool
        try:
            result = tool.execute(**args)

            # Track reads in context
            if tool_name == "fs.read" and result.success:
                path = args.get("path")
                content = result.output.get("content", "") if result.output else ""
                self.context.add_to_read_set(path, content)

            # Track file modifications for undo
            if tool_name in ("fs.write", "fs.edit") and result.success:
                path = args.get("path")
                if path:
                    from pathlib import Path as PathLib
                    file_path = PathLib(path).resolve()
                    try:
                        new_content = file_path.read_text(encoding="utf-8", errors="replace")
                        action = "created" if not file_existed else "modified"
                        self.context.record_file_change(
                            path=str(file_path),
                            old_content=old_content,
                            new_content=new_content,
                            action=action,
                        )
                    except Exception:
                        pass

            return result

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def _display_tool_call(self, tool_call: ToolCall) -> None:
        """Display a tool call being executed."""
        self.console.print(f"[cyan]▶[/cyan] [bold]{tool_call.name}[/bold]", end="")

        # Show key args inline for common tools
        args = tool_call.arguments
        if tool_call.name == "fs.read" and "path" in args:
            self.console.print(f" [dim]{args['path']}[/dim]")
        elif tool_call.name == "fs.edit" and "path" in args:
            self.console.print(f" [dim]{args['path']}[/dim]")
        elif tool_call.name == "fs.write" and "path" in args:
            self.console.print(f" [dim]{args['path']}[/dim]")
        elif tool_call.name == "fs.list" and "path" in args:
            self.console.print(f" [dim]{args['path']}[/dim]")
        elif tool_call.name == "shell.exec" and "command" in args:
            cmd = args['command'][:50] + "..." if len(args.get('command', '')) > 50 else args.get('command', '')
            self.console.print(f" [dim]{cmd}[/dim]")
        else:
            self.console.print()

    def _display_tool_result(self, tool_call: ToolCall, result: ToolResult) -> None:
        """Display a tool result."""
        if result.success:
            icon = "✓"
            style = "green"
        else:
            icon = "✗"
            style = "red"

        if result.error:
            self.console.print(f"  [{style}]{icon} {result.error}[/{style}]")
        elif result.output and self.config.show_tool_results:
            # Format output based on tool
            if tool_call.name == "fs.read":
                lines = result.output.get("total_lines", 0)
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]Read {lines} lines[/dim]")
            elif tool_call.name == "fs.list":
                count = result.output.get("count", 0)
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]Listed {count} entries[/dim]")
            elif tool_call.name in ("fs.write", "fs.edit"):
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]File modified[/dim]")
            elif tool_call.name == "shell.exec":
                exit_code = result.output.get("exit_code", -1)
                if exit_code == 0:
                    stdout = result.output.get("stdout", "")
                    lines = stdout.count('\n') + 1 if stdout else 0
                    self.console.print(f"  [{style}]{icon}[/{style}] [dim]Exit 0 ({lines} lines)[/dim]")
                else:
                    self.console.print(f"  [{style}]{icon}[/{style}] [yellow]Exit {exit_code}[/yellow]")
            elif tool_call.name.startswith("git."):
                self.console.print(f"  [{style}]{icon}[/{style}] [dim]Done[/dim]")
            else:
                self.console.print(f"  [{style}]{icon}[/{style}]")
        else:
            self.console.print(f"  [{style}]{icon}[/{style}]")

    def _request_approval(self, tool_call: ToolCall) -> bool:
        """Request user approval for a tool execution with visual diff preview."""
        tool = registry.get(tool_call.name)
        if not tool:
            return False

        self.console.print()

        # Show visual diff for file operations
        if tool_call.name in ("fs.write", "fs.edit"):
            self._show_file_operation_preview(tool_call)
        else:
            # Standard approval panel for non-file operations
            args_str = json.dumps(tool_call.arguments, indent=2)
            self.console.print(Panel(
                f"[{Styles.TOOL_NAME}]{tool_call.name}[/{Styles.TOOL_NAME}]\n\n{args_str}",
                title=f"[{Colors.WARNING}]{Icons.WARNING} Approve {tool.risk_level.value} operation?[/{Colors.WARNING}]",
                border_style=Colors.BORDER_WARNING,
            ))

        try:
            response = Prompt.ask(
                f"[{Colors.WARNING}]APPROVE?[/{Colors.WARNING}]",
                choices=["yes", "no", "y", "n", "all"],
                default="no",
            )
            if response.lower() == "all":
                # Disable approval for rest of this turn
                self.config.require_approval_moderate = False
                self.config.require_approval_dangerous = False
                return True
            return response.lower() in ("yes", "y")
        except (EOFError, KeyboardInterrupt):
            self.console.print(f"\n[{Colors.ERROR}]Cancelled[/{Colors.ERROR}]")
            return False

    def _show_file_operation_preview(self, tool_call: ToolCall) -> None:
        """Show visual diff preview for file write/edit operations."""
        from ..branding import format_diff_line

        args = tool_call.arguments

        if tool_call.name == "fs.write":
            path = args.get("path", "")
            content = args.get("content", "")

            # Get preview with diff
            from ..tools.fs import fs_write
            preview = fs_write.preview(path=path, content=content)

            # Header
            if preview["exists"]:
                action = f"[{Colors.WARNING}]OVERWRITE[/{Colors.WARNING}]"
            else:
                action = f"[{Colors.SUCCESS}]CREATE[/{Colors.SUCCESS}]"

            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            bytes_count = len(content.encode("utf-8"))

            self.console.print(f"{action} {preview['path']}")
            self.console.print(f"[{Colors.DIM}]{lines} lines, {bytes_count} bytes[/{Colors.DIM}]")

            # Show diff if file exists, otherwise show content preview
            if preview["diff"]:
                self.console.print(f"\n[{Styles.HEADER}]Changes:[/{Styles.HEADER}]")
                for line in preview["diff"].splitlines()[:50]:
                    self.console.print(format_diff_line(line))
                if len(preview["diff"].splitlines()) > 50:
                    self.console.print(f"[{Colors.DIM}]... diff truncated ({len(preview['diff'].splitlines())} lines total)[/{Colors.DIM}]")
            else:
                # New file - show content preview
                self.console.print(f"\n[{Styles.HEADER}]Content preview:[/{Styles.HEADER}]")
                preview_lines = content.splitlines()[:15]
                for i, line in enumerate(preview_lines, 1):
                    self.console.print(f"[{Colors.SUCCESS}]+{i:4d} | {line}[/{Colors.SUCCESS}]")
                if len(content.splitlines()) > 15:
                    self.console.print(f"[{Colors.DIM}]... and {len(content.splitlines()) - 15} more lines[/{Colors.DIM}]")

        elif tool_call.name == "fs.edit":
            path = args.get("path", "")
            old_text = args.get("old_text", "")
            new_text = args.get("new_text", "")
            replace_all = args.get("replace_all", False)

            # Get preview with diff
            from ..tools.fs import fs_edit
            preview = fs_edit.preview(path=path, old_text=old_text, new_text=new_text, replace_all=replace_all)

            if preview.get("error"):
                self.console.print(f"[{Colors.ERROR}]{Icons.ERROR} {preview['error']}[/{Colors.ERROR}]")
                return

            self.console.print(f"[{Colors.WARNING}]EDIT[/{Colors.WARNING}] {preview['path']}")
            self.console.print(f"[{Colors.DIM}]Replacing {preview.get('would_replace', 1)} occurrence(s)[/{Colors.DIM}]")

            if preview.get("diff"):
                self.console.print(f"\n[{Styles.HEADER}]Changes:[/{Styles.HEADER}]")
                for line in preview["diff"].splitlines()[:50]:
                    self.console.print(format_diff_line(line))
                if len(preview["diff"].splitlines()) > 50:
                    self.console.print(f"[{Colors.DIM}]... diff truncated ({len(preview['diff'].splitlines())} lines total)[/{Colors.DIM}]")

        self.console.print()

    def _needs_approval(self, tool_call: ToolCall) -> bool:
        """Check if a tool call needs user approval."""
        tool = registry.get(tool_call.name)
        if not tool:
            return True  # Unknown tools need approval

        if tool.risk_level == RiskLevel.DANGEROUS:
            return self.config.require_approval_dangerous
        elif tool.risk_level == RiskLevel.MODERATE:
            return self.config.require_approval_moderate
        return False

    def _stream_response(self, tools_schema: list[dict]) -> LLMResponse:
        """Stream LLM response with live display, elapsed time, and retry handling."""
        import time

        llm = self._get_llm()
        messages = self.context.get_messages_for_llm()

        content_buffer = ""
        final_response: Optional[LLMResponse] = None
        start_time = time.time()
        max_retries = 3
        retry_delay = 2.0  # seconds

        def get_thinking_display() -> Text:
            """Get thinking spinner with elapsed time."""
            elapsed = time.time() - start_time
            return Text.from_markup(
                f"[{Colors.PRIMARY}]{Icons.THINKING}[/{Colors.PRIMARY}] Thinking... [{Colors.DIM}]({elapsed:.1f}s)[/{Colors.DIM}]"
            )

        def get_retry_display(attempt: int, error: str) -> Text:
            """Get retry status display."""
            return Text.from_markup(
                f"[{Colors.WARNING}]{Icons.WARNING}[/{Colors.WARNING}] Connection issue. "
                f"Retrying ({attempt}/{max_retries})... [{Colors.DIM}]{error}[/{Colors.DIM}]"
            )

        for attempt in range(1, max_retries + 1):
            with Live(
                get_thinking_display(),
                console=self.console,
                refresh_per_second=10,
                transient=True,
            ) as live:
                try:
                    for response in llm.chat_stream(messages, tools_schema):
                        # Check for ESC interrupt
                        if check_for_escape():
                            self._interrupted = True
                            final_response = LLMResponse(
                                content=content_buffer,
                                tool_calls=[],
                                done=True,
                                interrupted=True,
                            )
                            break

                        if response.content:
                            content_buffer = response.content

                            # Update display with cursor and elapsed time
                            elapsed = time.time() - start_time
                            display = Text()
                            display.append(content_buffer)
                            display.append(Icons.CURSOR_BLOCK, style=Colors.PRIMARY_BOLD)
                            hint = Text.from_markup(
                                f"\n\n[{Colors.DIM}]{elapsed:.1f}s | Press ESC to interrupt[/{Colors.DIM}]"
                            )
                            live.update(Group(display, hint))
                        else:
                            # Still waiting for content - update timer
                            live.update(get_thinking_display())

                        if response.done:
                            final_response = response
                            break

                    # If we got a response (successful or with error), we're done
                    if final_response is not None:
                        break

                except Exception as e:
                    error_msg = str(e)
                    is_connection_error = any(
                        keyword in error_msg.lower()
                        for keyword in ["connection", "timeout", "refused", "network"]
                    )

                    if is_connection_error and attempt < max_retries:
                        # Show retry message and wait
                        live.update(get_retry_display(attempt, error_msg[:50]))
                        time.sleep(retry_delay)
                        retry_delay *= 1.5  # Exponential backoff
                        content_buffer = ""  # Reset buffer for retry
                        continue
                    else:
                        final_response = LLMResponse(
                            content=content_buffer,
                            error=error_msg,
                            done=True,
                        )
                        break

            # If loop completes without break (shouldn't happen), set default
            if final_response is None:
                final_response = LLMResponse(content=content_buffer, done=True)

        if final_response is None:
            final_response = LLMResponse(content=content_buffer, done=True)

        return final_response

    def _process_turn(self) -> bool:
        """
        Process a single turn of the agentic loop.

        Returns True if the loop should continue, False if done.
        """
        self.context.start_iteration()

        # Check limits
        can_continue, reason = self.context.can_continue()
        if not can_continue:
            self.console.print(f"[{Colors.WARNING}]{Icons.WARNING} {reason}[/{Colors.WARNING}]")
            return False

        # Check if context needs summarization
        if self._summarizer.should_summarize(
            self.context.messages,
            self.context.max_context_tokens,
        ):
            self.console.print("[dim]Compressing context...[/dim]")
            self.context.messages = self._summarizer.summarize(self.context.messages)
            # Recalculate token estimate
            self.context.estimated_tokens = sum(
                m.estimate_tokens() for m in self.context.messages
            )

        # Get LLM response
        self.state = AgentState.THINKING
        tools_schema = self._get_tools_schema()
        response = self._stream_response(tools_schema)

        if response.interrupted:
            self.console.print(f"\n[{Colors.WARNING}]{Icons.LIGHTNING} Interrupted[/{Colors.WARNING}]")
            return False

        if response.error:
            self.console.print(f"\n[{Colors.ERROR}]{Icons.ERROR} {response.error}[/{Colors.ERROR}]")
            return False

        # Display text content if any
        if response.has_content:
            self.console.print()
            try:
                self.console.print(Markdown(response.content))
            except Exception:
                self.console.print(response.content)

        # Add assistant message to context
        if response.has_content or response.has_tool_calls:
            # Format tool_calls for context storage
            tool_calls_data = []
            if response.has_tool_calls:
                for tc in response.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    })

            self.context.add_message(
                role="assistant",
                content=response.content,
                tool_calls=tool_calls_data,
            )

        # If no tool calls, we're done
        if not response.has_tool_calls:
            return False

        # Execute tool calls
        self.state = AgentState.EXECUTING_TOOLS
        self.console.print()

        for tool_call in response.tool_calls:
            # Check iteration limit
            self.context.tool_call_count += 1
            if self.context.tool_call_count > self.config.max_tool_calls_per_turn:
                self.console.print(f"[{Colors.WARNING}]{Icons.WARNING} Tool call limit reached ({self.config.max_tool_calls_per_turn})[/{Colors.WARNING}]")
                break

            # Check if approval needed
            if self._needs_approval(tool_call):
                self.state = AgentState.AWAITING_APPROVAL
                approved = self._request_approval(tool_call)
                if not approved:
                    self.console.print(f"[{Colors.WARNING}]{Icons.TOOL_SKIP} Skipped {tool_call.name}[/{Colors.WARNING}]")
                    # Add a "rejected" result so LLM knows
                    self.context.add_tool_result(
                        tool_call.id,
                        {"error": "User rejected this tool execution", "skipped": True}
                    )
                    continue

            # Display and execute
            self._display_tool_call(tool_call)
            result = self._execute_tool(tool_call)
            self._display_tool_result(tool_call, result)

            # Add result to context for next LLM turn
            self.context.add_tool_result(tool_call.id, result.to_dict())

        # Continue the loop - LLM needs to process tool results
        return True

    def process(self, user_input: str) -> str:
        """
        Process a user request through the full agentic loop.

        Returns the final response content.
        """
        self._interrupted = False
        self.context.reset_iteration()

        # Reset approval settings for this turn
        self.config.require_approval_moderate = True
        self.config.require_approval_dangerous = True

        # Add user message
        self.context.add_message("user", user_input)

        # Run the agentic loop
        final_content = ""
        while True:
            should_continue = self._process_turn()

            # Capture any content from the last turn
            if self.context.messages:
                last_msg = self.context.messages[-1]
                if last_msg.role == "assistant" and last_msg.content:
                    final_content = last_msg.content

            if not should_continue or self._interrupted:
                break

        # Show context summary with token usage
        self.state = AgentState.SUMMARIZING
        self._show_turn_summary()

        # Auto-save session after each turn
        self._auto_save_session()

        self.state = AgentState.IDLE
        return final_content

    def _auto_save_session(self) -> None:
        """Auto-save current session (silent, no error on failure)."""
        try:
            self._save_current_session()
        except Exception:
            pass  # Silent fail for auto-save

    def _show_turn_summary(self) -> None:
        """Show summary of the completed turn including token usage."""
        summary_parts = []

        # Token usage
        token_display, token_status = self.context.get_token_display()
        if token_display:
            if token_status == "warning":
                token_str = f"[{Colors.WARNING}]{token_display}[/{Colors.WARNING}]"
            elif token_status == "moderate":
                token_str = f"[{Colors.INFO}]{token_display}[/{Colors.INFO}]"
            else:
                token_str = f"[{Colors.DIM}]{token_display}[/{Colors.DIM}]"
            summary_parts.append(token_str)

        # Iterations if multiple
        if self.context.iteration > 1:
            summary_parts.append(f"[{Colors.DIM}]{self.context.iteration} iterations[/{Colors.DIM}]")

        # Files in context
        if self.context.read_set:
            summary_parts.append(f"[{Colors.DIM}]{len(self.context.read_set)} file(s)[/{Colors.DIM}]")

        if summary_parts:
            self.console.print()
            self.console.print(" | ".join(summary_parts))

    def run(self) -> None:
        """Run the interactive REPL."""
        # Check LLM availability
        try:
            llm = self._get_llm()
            model_info = f"Model: {llm.model_name}"
            tools_info = "Native tools" if llm.supports_tools() else "Text-based tools"
            provider_info = f"Provider: {llm.provider_type.value}"
        except RouraError as e:
            self.console.print(Panel(
                e.format_for_user(),
                title=f"[{Colors.ERROR}]{Icons.ERROR} Configuration Error[/{Colors.ERROR}]",
                border_style=Colors.BORDER_ERROR,
            ))
            return
        except ValueError as e:
            self.console.print(Panel(
                format_error(str(e), "Run 'roura-agent setup' to configure."),
                title=f"[{Colors.ERROR}]{Icons.ERROR} Error[/{Colors.ERROR}]",
                border_style=Colors.BORDER_ERROR,
            ))
            return

        # Initialize session
        if not self._current_session:
            self._current_session = self._session_manager.create_session(
                project_root=self.context.project_root,
                project_name=self.project.name if self.project else None,
                model=llm.model_name,
            )

        session_id = self._current_session.id[:8]

        self.console.print()
        self.console.print(Panel(
            f"[{Styles.HEADER}]Roura Agent[/{Styles.HEADER}] - Local AI Coding Assistant\n\n"
            f"[{Colors.DIM}]{provider_info} | {model_info} | {tools_info}[/{Colors.DIM}]\n\n"
            "I can read, write, and edit files, run commands, and help with git.\n"
            "I work in an agentic loop - I'll use tools and iterate until done.\n\n"
            f"[{Colors.PRIMARY}]/help[/{Colors.PRIMARY}] for commands | [{Colors.PRIMARY}]exit[/{Colors.PRIMARY}] to quit | [{Colors.PRIMARY}]ESC[/{Colors.PRIMARY}] to interrupt\n"
            f"[{Colors.DIM}]Session: {session_id}[/{Colors.DIM}]",
            title=f"[{Colors.PRIMARY_BOLD}]{Icons.ROCKET} Roura.io[/{Colors.PRIMARY_BOLD}]",
            border_style=Colors.BORDER_PRIMARY,
        ))
        self.console.print()

        try:
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
                        # Re-add system message
                        system_prompt = self.BASE_SYSTEM_PROMPT
                        if self.project:
                            from ..config import get_project_context_prompt
                            project_context = get_project_context_prompt(self.project)
                            system_prompt += f"\n\n{project_context}"
                        self.context.add_message("system", system_prompt)
                        self.console.print("[dim]Context cleared[/dim]")
                        continue

                    if user_input.lower() in ("/tools",):
                        self._show_tools()
                        continue

                    if user_input.lower() in ("/keys", "/shortcuts"):
                        self._show_keys()
                        continue

                    if user_input.lower() in ("/undo",):
                        self._do_undo()
                        continue

                    if user_input.lower() in ("/history", "/sessions"):
                        self._show_history()
                        continue

                    if user_input.lower().startswith("/resume"):
                        parts = user_input.split(maxsplit=1)
                        session_id = parts[1] if len(parts) > 1 else None
                        self._resume_session(session_id)
                        continue

                    if user_input.lower().startswith("/export"):
                        parts = user_input.split()
                        format_type = parts[1] if len(parts) > 1 else "markdown"
                        self._export_session(format_type)
                        continue

                    # Process request through agentic loop
                    self.process(user_input)

                except KeyboardInterrupt:
                    self.console.print("\n[dim]Use 'exit' to quit[/dim]")
                except EOFError:
                    self.console.print("\n[dim]Goodbye![/dim]")
                    break
        finally:
            # Save session on exit
            self._auto_save_session()
            self.console.print(f"[{Colors.DIM}]Session saved.[/{Colors.DIM}]")

    def _show_help(self) -> None:
        """Show help information."""
        self.console.print(Panel(
            f"[{Styles.HEADER}]Commands:[/{Styles.HEADER}]\n"
            f"  [{Colors.PRIMARY}]/help[/{Colors.PRIMARY}]     - Show this help\n"
            f"  [{Colors.PRIMARY}]/context[/{Colors.PRIMARY}]  - Show loaded file context\n"
            f"  [{Colors.PRIMARY}]/undo[/{Colors.PRIMARY}]     - Undo last file change\n"
            f"  [{Colors.PRIMARY}]/clear[/{Colors.PRIMARY}]    - Clear conversation and context\n"
            f"  [{Colors.PRIMARY}]/tools[/{Colors.PRIMARY}]    - List available tools\n"
            f"  [{Colors.PRIMARY}]/keys[/{Colors.PRIMARY}]     - Show keyboard shortcuts\n"
            f"  [{Colors.PRIMARY}]exit[/{Colors.PRIMARY}]      - Quit\n\n"
            f"[{Styles.HEADER}]How I Work:[/{Styles.HEADER}]\n"
            "  \u2022 I operate in an agentic loop\n"
            "  \u2022 I can use tools, see results, and iterate\n"
            "  \u2022 Press ESC to interrupt at any time\n"
            "  \u2022 I'll ask for approval before risky operations\n\n"
            f"[{Styles.HEADER}]Tips:[/{Styles.HEADER}]\n"
            "  \u2022 Be specific about what you want\n"
            "  \u2022 I'll read files before editing them\n"
            "  \u2022 Use /undo if I make an unwanted change\n"
            "  \u2022 For complex tasks, I'll work through them step by step",
            title=f"[{Styles.HEADER}]Help[/{Styles.HEADER}]",
            border_style=Colors.BORDER_INFO,
        ))

    def _show_context(self) -> None:
        """Show current context."""
        self.console.print(f"\n{self.context.get_context_summary()}\n")

        if self.context.read_set:
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
        table.add_column("Tool", style=Colors.PRIMARY)
        table.add_column("Risk", justify="center")
        table.add_column("Description")

        risk_colors = {
            RiskLevel.SAFE: Colors.RISK_SAFE,
            RiskLevel.MODERATE: Colors.RISK_MODERATE,
            RiskLevel.DANGEROUS: Colors.RISK_DANGEROUS,
        }

        for name, tool in sorted(registry._tools.items()):
            color = risk_colors.get(tool.risk_level, "white")
            risk_text = f"[{color}]{tool.risk_level.value}[/{color}]"
            table.add_row(name, risk_text, tool.description)

        self.console.print(table)

    def _show_keys(self) -> None:
        """Show keyboard shortcuts."""
        from ..branding import KEYBOARD_SHORTCUTS
        self.console.print(Panel(
            KEYBOARD_SHORTCUTS,
            title=f"[{Styles.HEADER}]Keyboard Shortcuts[/{Styles.HEADER}]",
            border_style=Colors.BORDER_INFO,
        ))

    def _do_undo(self) -> None:
        """Undo the last file change."""
        if not self.context.can_undo():
            self.console.print(f"[{Colors.DIM}]No changes to undo[/{Colors.DIM}]")
            return

        # Show what will be undone
        change = self.context.get_last_change()
        if change:
            from pathlib import Path as PathLib
            filename = PathLib(change.path).name
            self.console.print(f"\n[{Colors.WARNING}]Undo:[/{Colors.WARNING}] {change.action} {filename}")

            # Ask for confirmation
            try:
                response = Prompt.ask(
                    f"[{Colors.WARNING}]Restore previous version?[/{Colors.WARNING}]",
                    choices=["yes", "no", "y", "n"],
                    default="yes",
                )
                if response.lower() not in ("yes", "y"):
                    self.console.print(f"[{Colors.DIM}]Undo cancelled[/{Colors.DIM}]")
                    return
            except (EOFError, KeyboardInterrupt):
                self.console.print(f"\n[{Colors.DIM}]Undo cancelled[/{Colors.DIM}]")
                return

        # Perform undo
        try:
            result = self.context.undo_last_change()
            if result:
                path, _ = result
                from pathlib import Path as PathLib
                filename = PathLib(path).name
                self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Restored {filename}")

                # Show undo history
                history = self.context.get_undo_history(3)
                if history:
                    self.console.print(f"\n[{Colors.DIM}]Recent changes ({len(self.context.undo_stack)} undoable):[/{Colors.DIM}]")
                    for item in history:
                        self.console.print(f"[{Colors.DIM}]  \u2022 {item['action']} {item['path']} ({item['timestamp']})[/{Colors.DIM}]")
            else:
                self.console.print(f"[{Colors.DIM}]No changes to undo[/{Colors.DIM}]")
        except Exception as e:
            self.console.print(f"[{Colors.ERROR}]{Icons.ERROR} Failed to undo: {e}[/{Colors.ERROR}]")

    def _show_history(self) -> None:
        """Show recent session history."""
        sessions = self._session_manager.list_sessions(limit=10)

        if not sessions:
            self.console.print(f"[{Colors.DIM}]No saved sessions[/{Colors.DIM}]")
            return

        table = Table(title="Recent Sessions")
        table.add_column("ID", style=Colors.DIM, width=8)
        table.add_column("Date", style=Colors.DIM, width=10)
        table.add_column("Summary", style=Colors.PRIMARY)
        table.add_column("Messages", justify="right", width=8)

        for s in sessions:
            date = s["created_at"][:10]
            short_id = s["id"][:8]
            table.add_row(short_id, date, s["summary"][:40], str(s["message_count"]))

        self.console.print(table)
        self.console.print(f"\n[{Colors.DIM}]Use /resume <id> to continue a session[/{Colors.DIM}]")

    def _resume_session(self, session_id: Optional[str]) -> None:
        """Resume a previous session."""
        if not session_id:
            # Resume most recent
            session = self._session_manager.get_latest_session()
            if not session:
                self.console.print(f"[{Colors.DIM}]No sessions to resume[/{Colors.DIM}]")
                return
        else:
            # Find session by partial ID
            sessions = self._session_manager.list_sessions(limit=50)
            matching = [s for s in sessions if s["id"].startswith(session_id)]

            if not matching:
                self.console.print(f"[{Colors.ERROR}]Session not found: {session_id}[/{Colors.ERROR}]")
                return

            session = self._session_manager.load_session(matching[0]["id"])
            if not session:
                self.console.print(f"[{Colors.ERROR}]Failed to load session[/{Colors.ERROR}]")
                return

        # Restore messages to context
        for msg in session.messages:
            if msg.role != "system":  # Skip system messages
                self.context.add_message(
                    role=msg.role,
                    content=msg.content,
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                )

        self._current_session = session
        self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Resumed session: {session.get_summary()}")
        self.console.print(f"[{Colors.DIM}]Loaded {len(session.messages)} messages[/{Colors.DIM}]")

    def _export_session(self, format_type: str = "markdown") -> None:
        """Export current session to file."""
        if not self._current_session:
            # Create session from current context
            self._current_session = self._session_manager.create_session(
                project_root=self.context.project_root,
                project_name=self.project.name if self.project else None,
            )
            for msg in self.context.messages:
                if msg.role != "system":
                    self._current_session.add_message(
                        role=msg.role,
                        content=msg.content,
                        tool_calls=msg.tool_calls,
                        tool_call_id=msg.tool_call_id,
                    )

        if format_type.lower() == "json":
            content = self._current_session.to_json()
            ext = "json"
        else:
            content = self._current_session.to_markdown()
            ext = "md"

        # Write to file
        filename = f"session-{self._current_session.id[:8]}.{ext}"
        Path(filename).write_text(content)

        self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Exported to {filename}")

    def _save_current_session(self) -> None:
        """Save the current session."""
        if not self._current_session:
            self._current_session = self._session_manager.create_session(
                project_root=self.context.project_root,
                project_name=self.project.name if self.project else None,
            )

        # Sync messages
        self._current_session.messages.clear()
        for msg in self.context.messages:
            if msg.role != "system":
                self._current_session.add_message(
                    role=msg.role,
                    content=msg.content,
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                )

        self._session_manager.save_session(self._current_session)
