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
from ..agents import Orchestrator, get_registry, initialize_agents


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
    max_tool_calls_per_turn: int = 20
    require_approval_moderate: bool = True
    require_approval_dangerous: bool = True
    auto_read_on_modify: bool = True
    stream_responses: bool = True
    show_tool_results: bool = True
    multi_agent_mode: bool = True  # Enable orchestrator delegation (on by default)
    # Smart escalation: use more powerful models when local model struggles
    # Smart escalation: very conservative - local models should do 99% of work
    escalation_enabled: bool = True
    escalation_min_failures: int = 3  # Only escalate after 3 consecutive failures
    escalation_prompt_user: bool = True  # Always ask before escalating
    escalation_auto: bool = False  # Never auto-escalate without user consent


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

    BASE_SYSTEM_PROMPT = """You are Roura Agent, a friendly AI coding assistant running locally on the user's machine.

PERSONALITY: Be conversational, helpful, and concise. Talk like a knowledgeable colleague, not a formal assistant. Use casual language. Never output JSON or structured data as your response - always respond in natural language.

HOW YOU WORK:
- Use tools silently to gather info, then respond naturally
- Never show tool calls or JSON to the user - just describe what you found/did
- When exploring code, summarize insights rather than dumping raw output
- If something fails, adapt and try alternatives without complaining

CRITICAL RULES:
1. NEVER output JSON as a response. If you need to call a tool, just call it.
2. Discover files with fs.list before reading them - don't guess paths
3. Read files before modifying them
4. Keep responses brief and natural - no numbered lists unless asked
5. Do the work, then share results conversationally

When reviewing a project:
1. Use project.analyze for a quick overview of languages and structure
2. Use project.summary to understand what the project does
3. Read key files (README, main entry points, configs)
4. Provide a helpful, conversational summary

Available tools: fs.read, fs.write, fs.edit, fs.list, git.status, git.diff, git.log, git.add, git.commit, shell.exec, project.analyze, project.summary, project.related"""

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
        self._orchestrator: Optional[Orchestrator] = None
        self._current_agent: Optional[str] = None  # Track which agent is working
        self._consecutive_failures: int = 0  # Track failures for escalation

        # Initialize orchestrator if multi-agent mode is enabled
        if self.config.multi_agent_mode:
            self._orchestrator = initialize_agents(console=self.console)

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

    def enable_multi_agent(self) -> None:
        """Enable multi-agent orchestration mode."""
        if self.config.multi_agent_mode and self._orchestrator:
            self.console.print(f"[{Colors.DIM}]Multi-agent mode already enabled[/{Colors.DIM}]")
            return

        self.config.multi_agent_mode = True
        if not self._orchestrator:
            self._orchestrator = initialize_agents(console=self.console)
        self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Multi-agent mode enabled")
        agents = get_registry().list_agents()
        self.console.print(f"[{Colors.DIM}]Available agents: {', '.join(a.name.title() for a in agents)}[/{Colors.DIM}]")

    def disable_multi_agent(self) -> None:
        """Disable multi-agent mode."""
        self.config.multi_agent_mode = False
        self._orchestrator = None
        self._current_agent = None
        get_registry().clear()
        self.console.print(f"[{Colors.DIM}]Multi-agent mode disabled[/{Colors.DIM}]")

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

        def get_thinking_display() -> Group:
            """Get thinking spinner with elapsed time and agent info."""
            elapsed = time.time() - start_time
            spinner = Spinner("dots", style=Colors.PRIMARY)
            if self._current_agent:
                text = Text.from_markup(
                    f" [{Colors.INFO}]{self._current_agent}[/{Colors.INFO}] thinking... "
                    f"[{Colors.DIM}]({elapsed:.1f}s)[/{Colors.DIM}]"
                )
            else:
                text = Text.from_markup(
                    f" Thinking... [{Colors.DIM}]({elapsed:.1f}s)[/{Colors.DIM}]"
                )
            # Combine spinner and text
            from rich.table import Table
            t = Table.grid()
            t.add_row(spinner, text)
            return t

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
                refresh_per_second=20,  # Higher refresh for responsive ESC
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

                            # Don't display content that looks like a JSON tool call
                            # (some models output tool calls as text)
                            stripped = content_buffer.strip()
                            looks_like_json_tool = (
                                (stripped.startswith("{") or stripped.startswith("[")) and
                                ('"name"' in stripped or '"tool"' in stripped or '"function"' in stripped or '"arguments"' in stripped)
                            )

                            if not looks_like_json_tool:
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

        # Reset failure counter on any successful response
        if not response.error:
            self._consecutive_failures = 0

        if response.error:
            self._consecutive_failures += 1
            self.console.print(f"\n[{Colors.ERROR}]{Icons.ERROR} {response.error}[/{Colors.ERROR}]")
            # Check if we should offer escalation (only after multiple failures)
            if self._should_offer_escalation():
                if self._offer_escalation(f"Local model failed {self._consecutive_failures} times. Try cloud model?"):
                    self._consecutive_failures = 0  # Reset on escalation
                    return True  # Retry with new model
            return False

        # Display text content if any
        # But skip if it looks like a JSON tool call (some models output tool calls as text)
        if response.has_content:
            content = response.content.strip()
            is_json_tool_call = (
                (content.startswith("{") or content.startswith("[")) and
                ('"name"' in content or '"tool"' in content or '"function"' in content or '"arguments"' in content)
            )

            # Also skip if we have tool calls and content looks like JSON
            if response.has_tool_calls and is_json_tool_call:
                pass  # Don't display JSON tool output
            elif not is_json_tool_call:
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

    def _determine_agent(self, user_input: str) -> str:
        """
        Determine which agent should handle this task.

        Uses the orchestrator to analyze the task and pick the best agent.
        """
        if not self._orchestrator:
            return "roura"  # Default agent name

        # Use orchestrator's task analysis
        analysis = self._orchestrator._analyze_task(user_input)
        agent_type = analysis.get("primary_type", "code")

        # Map to display names
        agent_names = {
            "code": "Code Agent",
            "test": "Test Agent",
            "debug": "Debug Agent",
            "research": "Research Agent",
            "git": "Git Agent",
            "review": "Review Agent",
            "cursor": "Cursor Agent",
            "xcode": "Xcode Agent",
        }

        return agent_names.get(agent_type, "Roura Agent")

    def _enhance_with_project_context(self, user_input: str) -> str:
        """
        Enhance user input with project context if no specific files mentioned.

        If the user says "review my code" without specifying files,
        add context about the project structure.
        """
        import re

        # Check if input mentions specific files
        has_specific_files = bool(re.search(
            r'\b[\w/\\]+\.(py|js|ts|tsx|jsx|go|rs|java|c|cpp|h|rb|php|swift|kt)\b',
            user_input
        ))

        # Keywords that suggest user wants to work with the whole project
        project_wide_keywords = [
            r'\b(my|the|this)\s+(code|project|codebase|repo|repository)\b',
            r'\breview\s+(my|the|this)?\s*(code|changes)?\b',
            r'\banalyze\s+(my|the|this)?\s*(code|project)?\b',
            r'\bcheck\s+(my|the|this)?\s*(code|project)?\b',
            r'\bimprove\s+(my|the|this)?\s*(code|project)?\b',
            r'\brefactor\b',
            r'\bwhat\s+(does|is)\s+(this|my)\s+(project|code)\b',
        ]

        needs_project_context = any(
            re.search(pattern, user_input.lower())
            for pattern in project_wide_keywords
        )

        if needs_project_context and not has_specific_files and self.context.project_root:
            # Add brief hint to explore first
            return user_input + f"\n\n[Hint: Use fs.list to discover files first]"

        return user_input

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

        # Determine which agent should handle this task
        self._current_agent = self._determine_agent(user_input)

        # Enhance input with project context if needed
        enhanced_input = self._enhance_with_project_context(user_input)

        # Add user message
        self.context.add_message("user", enhanced_input)

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
        """Show brief summary of the completed turn."""
        # Only show if multiple iterations or many files
        if self.context.iteration > 2 or len(self.context.read_set) > 3:
            parts = []
            if self.context.iteration > 1:
                parts.append(f"{self.context.iteration} turns")
            if self.context.read_set:
                parts.append(f"{len(self.context.read_set)} files")
            if parts:
                self.console.print(f"\n[{Colors.DIM}]{' | '.join(parts)}[/{Colors.DIM}]")

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

        # Check for updates (non-blocking)
        self._check_for_updates_notification()

        # Show walkthrough on first run
        from ..onboarding import is_walkthrough_seen, mark_walkthrough_seen
        if not is_walkthrough_seen():
            self.console.print()
            self._show_walkthrough()
            mark_walkthrough_seen()
        else:
            self.console.print()

        # Setup prompt with tab completion
        from ..prompt import prompt_input

        try:
            while True:
                try:
                    # Prompt with tab completion
                    user_input = prompt_input("> ").strip()

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
                        old_count = len(self.context.messages)
                        self.context.clear()
                        # Re-add system message
                        system_prompt = self.BASE_SYSTEM_PROMPT
                        if self.project:
                            from ..config import get_project_context_prompt
                            project_context = get_project_context_prompt(self.project)
                            system_prompt += f"\n\n{project_context}"
                        self.context.add_message("system", system_prompt)
                        self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Conversation cleared")
                        self.console.print(f"[{Colors.DIM}]Ready for a fresh start[/{Colors.DIM}]")
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

                    if user_input.lower() == "/pricing":
                        self._show_upgrade()
                        continue

                    if user_input.lower() in ("/license", "/key"):
                        self._manage_license()
                        continue

                    if user_input.lower() in ("/agents",):
                        self._show_agents()
                        continue

                    if user_input.lower() in ("/multi", "/orchestrator"):
                        self._toggle_multi_agent()
                        continue

                    if user_input.lower().startswith("/model"):
                        parts = user_input.split(maxsplit=1)
                        provider_name = parts[1] if len(parts) > 1 else None
                        self._switch_model(provider_name)
                        continue

                    if user_input.lower() == "/upgrade":
                        self._do_update()
                        continue

                    if user_input.lower() == "/restart":
                        self._do_restart()
                        # If we get here, restart failed
                        continue

                    if user_input.lower() in ("/status", "/info"):
                        self._show_status()
                        continue

                    if user_input.lower() in ("/version", "/v"):
                        from ..constants import VERSION
                        self.console.print(f"[{Colors.PRIMARY}]Roura Agent[/{Colors.PRIMARY}] v{VERSION}")
                        continue

                    if user_input.lower() in ("/walkthrough", "/tutorial", "/tour"):
                        self._show_walkthrough()
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
            f"  [{Colors.PRIMARY}]/help[/{Colors.PRIMARY}]        - Show this help\n"
            f"  [{Colors.PRIMARY}]/status[/{Colors.PRIMARY}]      - Show session info\n"
            f"  [{Colors.PRIMARY}]/model[/{Colors.PRIMARY}]       - Switch LLM provider\n"
            f"  [{Colors.PRIMARY}]/upgrade[/{Colors.PRIMARY}]     - Check for & install updates\n"
            f"  [{Colors.PRIMARY}]/restart[/{Colors.PRIMARY}]     - Restart CLI (keeps session)\n"
            f"  [{Colors.PRIMARY}]/context[/{Colors.PRIMARY}]     - Show loaded files\n"
            f"  [{Colors.PRIMARY}]/undo[/{Colors.PRIMARY}]        - Undo last change\n"
            f"  [{Colors.PRIMARY}]/clear[/{Colors.PRIMARY}]       - Clear conversation\n"
            f"  [{Colors.PRIMARY}]exit[/{Colors.PRIMARY}]         - Quit\n\n"
            f"[{Styles.HEADER}]Smart Escalation:[/{Styles.HEADER}]\n"
            "  When using a local model (Ollama), if it struggles\n"
            "  you'll be offered to escalate to Claude or GPT-4.\n\n"
            f"[{Styles.HEADER}]Tips:[/{Styles.HEADER}]\n"
            "  \u2022 ESC to interrupt at any time\n"
            "  \u2022 I'll ask before risky operations\n"
            "  \u2022 /undo to revert file changes",
            title=f"[{Styles.HEADER}]Help[/{Styles.HEADER}]",
            border_style=Colors.BORDER_INFO,
        ))

    def _show_walkthrough(self) -> None:
        """Interactive walkthrough of Roura Agent features."""
        from rich.markdown import Markdown

        steps = [
            {
                "title": "Welcome to Roura Agent!",
                "content": """
**Roura Agent** is your local AI coding assistant. Let me show you how to get the most out of it.

**Key Concepts:**
- I can read, write, and edit files in your project
- I run shell commands and git operations
- I work in a loop: use tools → see results → continue
- Press **ESC** anytime to interrupt me

*Press Enter to continue...*
"""
            },
            {
                "title": "Talking to Me",
                "content": """
**Just ask naturally!** Here are some examples:

• "Read the main.py file and explain what it does"
• "Find all TODO comments in this project"
• "Fix the bug in the login function"
• "Create a new test file for the User class"
• "What does this codebase do?"

**Tips:**
- Be specific about what you want
- I'll ask for clarification if needed
- I'll show you diffs before making changes

*Press Enter to continue...*
"""
            },
            {
                "title": "Slash Commands",
                "content": """
**Quick commands** start with `/` — press **Tab** for autocomplete!

| Command | What it does |
|---------|-------------|
| `/help` | Show all commands |
| `/status` | Show session info |
| `/model` | Switch AI provider |
| `/upgrade` | Check for & install updates |
| `/restart` | Restart CLI (keeps session) |
| `/context` | See files I've read |
| `/undo` | Revert last file change |
| `/clear` | Reset conversation |

*Press Enter to continue...*
"""
            },
            {
                "title": "Multi-Model Power",
                "content": """
**Smart Escalation** — Use local models with cloud backup!

When using Ollama (local), if I struggle with a task, I'll offer to escalate to **Claude** or **GPT-4**.

**Switch models anytime:**
```
/model ollama      # Use local model
/model anthropic   # Use Claude
/model openai      # Use GPT-4
```

This lets you:
- Use fast local models for simple tasks
- Bring in powerful cloud models when needed
- Control costs by choosing when to use paid APIs

*Press Enter to continue...*
"""
            },
            {
                "title": "Safety & Approval",
                "content": """
**I ask before risky operations:**

• **File writes** — I'll show a diff before changing files
• **Shell commands** — I'll show the command and ask for approval
• **Git operations** — Commits need your OK

**Undo mistakes:**
- `/undo` reverts my last file change
- I keep a history of changes

**Safe modes:**
```bash
roura-agent --readonly     # No file modifications
roura-agent --dry-run      # Preview changes only
roura-agent --safe-mode    # Disable shell commands
```

*Press Enter to continue...*
"""
            },
            {
                "title": "Pro Tips",
                "content": """
**Get more out of Roura Agent:**

1. **Tab completion** — Type `/` and press Tab
2. **History** — Use ↑/↓ arrows for previous commands
3. **Search history** — Press Ctrl+R
4. **Interrupt** — Press ESC to stop me mid-task
5. **Context** — I remember files I've read in this session

**Integrations (PRO):**
- GitHub: `roura-agent` uses `gh` CLI
- Jira: Set JIRA_URL, JIRA_EMAIL, JIRA_TOKEN

**Reset anytime:**
```bash
roura-agent reset    # Factory reset, redo setup
roura-agent setup    # Reconfigure settings
```

*Press Enter to finish!*
"""
            },
        ]

        self.console.print()

        for i, step in enumerate(steps, 1):
            self.console.print(Panel(
                Markdown(step["content"]),
                title=f"[{Colors.PRIMARY_BOLD}]{step['title']}[/{Colors.PRIMARY_BOLD}] [{Colors.DIM}]({i}/{len(steps)})[/{Colors.DIM}]",
                border_style=Colors.BORDER_PRIMARY,
            ))

            try:
                input()
            except (EOFError, KeyboardInterrupt):
                self.console.print(f"\n[{Colors.DIM}]Walkthrough ended[/{Colors.DIM}]")
                return

        self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] You're ready to go! Just type what you need help with.\n")

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

    def _show_upgrade(self) -> None:
        """Show upgrade options and pricing."""
        from ..licensing import get_current_tier, Tier

        current_tier = get_current_tier()

        # Pricing table
        pricing_table = Table(show_header=True, header_style="bold", border_style=Colors.BORDER_PRIMARY)
        pricing_table.add_column("Plan", style=Colors.PRIMARY)
        pricing_table.add_column("Price", justify="right")
        pricing_table.add_column("Features")

        pricing_table.add_row(
            "FREE",
            "$0",
            "Ollama (local LLM), File ops, Git, Shell"
        )
        pricing_table.add_row(
            "PRO Monthly",
            "$19/mo",
            "+ OpenAI, Anthropic, Auto-fix loops, GitHub, Jira"
        )
        pricing_table.add_row(
            "PRO Annual",
            "$159/yr",
            "Same as PRO Monthly (save 30%)"
        )
        pricing_table.add_row(
            "PRO Lifetime",
            "$299",
            "Same as PRO (one-time payment)"
        )

        self.console.print()
        self.console.print(pricing_table)
        self.console.print()

        if current_tier == Tier.FREE:
            self.console.print(f"[{Colors.PRIMARY_BOLD}]Upgrade to PRO:[/{Colors.PRIMARY_BOLD}]")
            self.console.print()
            self.console.print(f"  Monthly:  https://buy.stripe.com/3cI28r8zl0tG92b6Cb5kk00")
            self.console.print(f"  Annual:   https://buy.stripe.com/14A7sL2aXa4g5PZ0dN5kk01")
            self.console.print(f"  Lifetime: https://buy.stripe.com/4gMfZh8zl90c3HR3pZ5kk02")
            self.console.print()
            self.console.print(f"[{Colors.DIM}]After purchase, use /license to enter your key.[/{Colors.DIM}]")
        else:
            self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} You're on the {current_tier.value.upper()} tier![/{Colors.SUCCESS}]")

        self.console.print()

    def _manage_license(self) -> None:
        """View or enter license key."""
        from ..licensing import get_current_tier, get_current_license, validate_license_key, clear_license_cache, Tier
        from ..onboarding import GLOBAL_ENV_FILE, load_env_file, save_env_file
        import os

        current_tier = get_current_tier()
        current_license = get_current_license()

        self.console.print()

        if current_license and current_license.is_valid:
            # Show current license info
            self.console.print(f"[{Colors.PRIMARY_BOLD}]Current License[/{Colors.PRIMARY_BOLD}]")
            self.console.print()
            self.console.print(f"  Tier:    [{Colors.SUCCESS}]{current_license.tier.value.upper()}[/{Colors.SUCCESS}]")
            self.console.print(f"  Email:   {current_license.email}")
            if current_license.valid_until:
                self.console.print(f"  Expires: {current_license.valid_until.strftime('%Y-%m-%d')}")
            else:
                self.console.print(f"  Expires: [{Colors.SUCCESS}]Never (Lifetime)[/{Colors.SUCCESS}]")
            self.console.print()

            # Ask if they want to enter a new key
            try:
                change = Prompt.ask(
                    f"[{Colors.DIM}]Enter a new license key?[/{Colors.DIM}]",
                    choices=["yes", "no"],
                    default="no",
                )
                if change.lower() != "yes":
                    return
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                return
        else:
            self.console.print(f"[{Colors.DIM}]No active license. Current tier: FREE[/{Colors.DIM}]")
            self.console.print()

        # Prompt for new license key
        try:
            new_key = Prompt.ask(f"[{Colors.PRIMARY}]Enter license key[/{Colors.PRIMARY}]")
        except (EOFError, KeyboardInterrupt):
            self.console.print(f"\n[{Colors.DIM}]Cancelled[/{Colors.DIM}]")
            return

        if not new_key.strip():
            self.console.print(f"[{Colors.DIM}]No key entered[/{Colors.DIM}]")
            return

        # Validate the key
        license_obj = validate_license_key(new_key.strip())
        if license_obj and license_obj.is_valid:
            # Save to .env file
            env_vars = {}
            if GLOBAL_ENV_FILE.exists():
                env_vars = load_env_file(GLOBAL_ENV_FILE)
            env_vars["ROURA_LICENSE_KEY"] = new_key.strip()
            save_env_file(GLOBAL_ENV_FILE, env_vars)

            # Apply to current session
            os.environ["ROURA_LICENSE_KEY"] = new_key.strip()
            clear_license_cache()

            self.console.print()
            self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS} License activated![/{Colors.SUCCESS}]")
            self.console.print(f"  Tier: [{Colors.SUCCESS}]{license_obj.tier.value.upper()}[/{Colors.SUCCESS}]")
            self.console.print()
            self.console.print(f"[{Colors.DIM}]Restart roura-agent to apply all PRO features.[/{Colors.DIM}]")
        else:
            self.console.print(f"[{Colors.ERROR}]{Icons.ERROR} Invalid license key[/{Colors.ERROR}]")

        self.console.print()

    def _show_agents(self) -> None:
        """Show available agents in the multi-agent system."""
        registry = get_registry()
        agents = registry.list_agents()

        if not agents:
            self.console.print(f"[{Colors.DIM}]No agents registered. Use /multi to enable multi-agent mode.[/{Colors.DIM}]")
            return

        table = Table(title="Available Agents")
        table.add_column("Agent", style=Colors.PRIMARY)
        table.add_column("Description")
        table.add_column("Capabilities", style=Colors.DIM)

        for agent in agents:
            caps = ", ".join(c.value for c in agent.capabilities[:3])
            if len(agent.capabilities) > 3:
                caps += f" +{len(agent.capabilities) - 3}"
            table.add_row(agent.name, agent.description, caps)

        self.console.print(table)

        # Show orchestrator status
        if self.config.multi_agent_mode:
            self.console.print(f"\n[{Colors.SUCCESS}]{Icons.SUCCESS} Multi-agent mode: ON[/{Colors.SUCCESS}]")
        else:
            self.console.print(f"\n[{Colors.DIM}]Multi-agent mode: OFF (use /multi to enable)[/{Colors.DIM}]")

    def _toggle_multi_agent(self) -> None:
        """Toggle multi-agent orchestration mode."""
        if self.config.multi_agent_mode:
            self.disable_multi_agent()
        else:
            self.enable_multi_agent()

    def _switch_model(self, provider_name: Optional[str] = None) -> None:
        """Switch to a different LLM provider."""
        from ..llm import detect_available_providers, get_provider, ProviderType

        available = detect_available_providers()

        if not provider_name:
            # Show available providers
            self.console.print(f"\n[{Styles.HEADER}]Available Models[/{Styles.HEADER}]")
            current = self._llm.provider_type if self._llm else None
            for pt in available:
                marker = f"[{Colors.SUCCESS}]●[/{Colors.SUCCESS}]" if pt == current else f"[{Colors.DIM}]○[/{Colors.DIM}]"
                self.console.print(f"  {marker} {pt.value}")
            self.console.print(f"\n[{Colors.DIM}]Usage: /model <provider>[/{Colors.DIM}]")
            return

        # Map name to provider type
        provider_map = {
            "ollama": ProviderType.OLLAMA,
            "openai": ProviderType.OPENAI,
            "anthropic": ProviderType.ANTHROPIC,
            "claude": ProviderType.ANTHROPIC,
            "gpt": ProviderType.OPENAI,
        }

        provider_type = provider_map.get(provider_name.lower())
        if not provider_type:
            self.console.print(f"[{Colors.ERROR}]Unknown provider: {provider_name}[/{Colors.ERROR}]")
            self.console.print(f"[{Colors.DIM}]Available: {', '.join(p.value for p in available)}[/{Colors.DIM}]")
            return

        if provider_type not in available:
            self.console.print(f"[{Colors.ERROR}]{provider_type.value} is not configured[/{Colors.ERROR}]")
            self.console.print(f"[{Colors.DIM}]Run 'roura-agent setup' or set API keys[/{Colors.DIM}]")
            return

        try:
            self._llm = get_provider(provider_type)
            self._provider_type = provider_type
            self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Switched to {self._llm.model_name}")

            # Save as last used provider
            from ..onboarding import save_last_provider
            save_last_provider(provider_type.value)
        except Exception as e:
            self.console.print(f"[{Colors.ERROR}]Failed to switch: {e}[/{Colors.ERROR}]")

    def _should_offer_escalation(self) -> bool:
        """Check if we should offer to escalate to a more powerful model.

        Escalation is very conservative - local models should handle 99% of tasks.
        Only offer after multiple consecutive failures.
        """
        if not self.config.escalation_enabled:
            return False

        # Only escalate from local models (Ollama)
        if not self._llm or self._llm.provider_type != ProviderType.OLLAMA:
            return False

        # Require multiple consecutive failures before offering escalation
        if self._consecutive_failures < self.config.escalation_min_failures:
            return False

        # Check if we have escalation providers available
        from ..llm import detect_available_providers
        available = detect_available_providers()
        return ProviderType.OPENAI in available or ProviderType.ANTHROPIC in available

    def _offer_escalation(self, reason: str) -> bool:
        """Offer to escalate to a more powerful model. Returns True if escalated.

        Escalation is a last resort - local models should handle most tasks.
        """
        from ..llm import detect_available_providers, get_provider

        # Always prompt user - never auto-escalate
        available = detect_available_providers()
        fallbacks = []
        if ProviderType.ANTHROPIC in available:
            fallbacks.append(("anthropic", "Claude"))
        if ProviderType.OPENAI in available:
            fallbacks.append(("openai", "GPT-4"))

        if not fallbacks:
            return False

        # Show escalation prompt - make it clear this uses cloud
        self.console.print()
        self.console.print(f"[{Colors.WARNING}]{Icons.WARNING} {reason}[/{Colors.WARNING}]")
        self.console.print(f"[{Colors.DIM}]This will use a cloud API (costs may apply).[/{Colors.DIM}]")

        try:
            choices = [name.lower() for _, name in fallbacks] + ["no"]
            response = Prompt.ask(
                f"[{Colors.PRIMARY}]Use cloud model?[/{Colors.PRIMARY}]",
                choices=choices,
                default="no",  # Default to staying local
            )

            if response.lower() == "no":
                self.console.print(f"[{Colors.DIM}]Continuing with local model.[/{Colors.DIM}]")
                return False

            # Map response to provider
            provider_map = {"claude": ProviderType.ANTHROPIC, "gpt-4": ProviderType.OPENAI}
            provider_type = provider_map.get(response.lower())

            if provider_type:
                self._llm = get_provider(provider_type)
                self._provider_type = provider_type
                self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Using {self._llm.model_name} for this task")

                # Save last provider
                from ..onboarding import save_last_provider
                save_last_provider(provider_type.value)
                return True

        except (EOFError, KeyboardInterrupt):
            self.console.print(f"\n[{Colors.DIM}]Cancelled[/{Colors.DIM}]")

        return False


    def _check_for_updates_notification(self) -> None:
        """Check for updates and show notification if available."""
        try:
            from ..update import check_for_updates
            update_info = check_for_updates()

            if update_info and update_info.has_update:
                self.console.print(
                    f"[{Colors.INFO}]{Icons.INFO} Update available: "
                    f"v{update_info.current_version} → v{update_info.latest_version}[/{Colors.INFO}]"
                )
                self.console.print(f"[{Colors.DIM}]Run /upgrade to install (will restart, context may be lost)[/{Colors.DIM}]")
        except Exception:
            pass  # Silently fail - don't block startup

    def _do_update(self) -> None:
        """Perform update and check for new features requiring setup."""
        from ..update import perform_update, check_for_updates, check_new_features_setup

        # Show current version
        update_info = check_for_updates(force=True)
        if update_info:
            if update_info.has_update:
                self.console.print(
                    f"\n[{Colors.INFO}]Current: v{update_info.current_version} → "
                    f"Latest: v{update_info.latest_version}[/{Colors.INFO}]"
                )
                if update_info.release_notes:
                    # Show brief release notes
                    notes_preview = update_info.release_notes.split("\n")[:5]
                    self.console.print(f"\n[{Colors.DIM}]What's new:[/{Colors.DIM}]")
                    for line in notes_preview:
                        if line.strip():
                            self.console.print(f"[{Colors.DIM}]  {line.strip()}[/{Colors.DIM}]")
            else:
                self.console.print(f"\n[{Colors.SUCCESS}]{Icons.SUCCESS} You're on the latest version (v{update_info.current_version})[/{Colors.SUCCESS}]")
                return

        # Perform update
        if perform_update(self.console):
            # Check if new features need setup
            check_new_features_setup(self.console)
            # Auto-restart to apply the update
            self._do_restart()

    def _do_restart(self) -> None:
        """Restart the CLI, preserving the current session."""
        import os
        import sys

        # Save current session first
        self._auto_save_session()
        session_id = self._current_session.id if self._current_session else None

        self.console.print(f"[{Colors.INFO}]Restarting...[/{Colors.INFO}]")

        # Get the executable and arguments
        executable = sys.executable
        script = sys.argv[0]

        # Build new args, adding --resume if we have a session
        args = [executable, script]
        if session_id:
            args.extend(["--resume", session_id])

        # Replace current process
        try:
            os.execv(executable, args)
        except Exception as e:
            self.console.print(f"[{Colors.ERROR}]Failed to restart: {e}[/{Colors.ERROR}]")

    def _show_status(self) -> None:
        """Show current session status and info."""
        from ..constants import VERSION
        from ..licensing import get_current_tier

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style=Colors.DIM)
        table.add_column("Value", style=Colors.PRIMARY)

        # Version
        table.add_row("Version", f"v{VERSION}")

        # Model info
        if self._llm:
            table.add_row("Model", self._llm.model_name)
            table.add_row("Provider", self._provider_type.value if self._provider_type else "unknown")

        # Session info
        if self._current_session:
            table.add_row("Session", self._current_session.id[:8])
            table.add_row("Messages", str(len(self.context.messages)))

        # Project info
        if self.project:
            table.add_row("Project", self.project.name)
            table.add_row("Path", str(self.context.project_root))

        # License tier
        tier = get_current_tier()
        table.add_row("Tier", tier.upper())

        # Context stats
        if self.context.read_set:
            table.add_row("Files read", str(len(self.context.read_set)))
        if self.context.undo_stack:
            table.add_row("Undoable changes", str(len(self.context.undo_stack)))

        self.console.print(Panel(table, title=f"[{Styles.HEADER}]Status[/{Styles.HEADER}]", border_style=Colors.BORDER_INFO))

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
        msg_count = len(session.messages)
        self.console.print(f"[{Colors.SUCCESS}]{Icons.SUCCESS}[/{Colors.SUCCESS}] Resumed session: {session.get_summary()}")
        if msg_count > 0:
            self.console.print(f"[{Colors.DIM}]Restored {msg_count} messages from previous conversation[/{Colors.DIM}]")
        else:
            self.console.print(f"[{Colors.DIM}]Session restored (no previous messages)[/{Colors.DIM}]")

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
