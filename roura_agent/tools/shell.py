"""
Roura Agent Shell Tool - Safe shell command execution.

© Roura.io
"""
from __future__ import annotations

import os
import subprocess
import shlex
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry


# Commands that are always blocked
BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # Fork bomb
    "> /dev/sda",
    "chmod -R 777 /",
    "chown -R",
}

# Patterns that require extra confirmation
DANGEROUS_PATTERNS = [
    "rm -rf",
    "rm -r",
    "sudo",
    "chmod",
    "chown",
    "kill -9",
    "pkill",
    "shutdown",
    "reboot",
    "format",
    "fdisk",
    "mkfs",
]


def is_command_blocked(command: str) -> tuple[bool, str]:
    """Check if a command is blocked for safety."""
    cmd_lower = command.lower().strip()

    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return True, f"Command blocked for safety: contains '{blocked}'"

    return False, ""


def is_command_dangerous(command: str) -> bool:
    """Check if a command is potentially dangerous."""
    cmd_lower = command.lower()
    return any(pattern in cmd_lower for pattern in DANGEROUS_PATTERNS)


@dataclass
class ShellExecTool(Tool):
    """Execute shell commands safely."""

    name: str = "shell.exec"
    description: str = "Execute a shell command and return output"
    risk_level: RiskLevel = RiskLevel.DANGEROUS
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("command", str, "The command to execute", required=True),
        ToolParam("cwd", str, "Working directory (default: current)", required=False, default=None),
        ToolParam("timeout", int, "Timeout in seconds (default: 30)", required=False, default=30),
    ])

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
    ) -> ToolResult:
        """Execute a shell command."""
        # Safety check
        blocked, reason = is_command_blocked(command)
        if blocked:
            return ToolResult(
                success=False,
                output=None,
                error=reason,
            )

        # Resolve working directory
        if cwd:
            work_dir = Path(cwd).resolve()
            if not work_dir.exists():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Working directory does not exist: {cwd}",
                )
        else:
            work_dir = Path.cwd()

        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(work_dir),
                env={**os.environ, "TERM": "dumb"},  # Disable colors in output
            )

            output = {
                "command": command,
                "cwd": str(work_dir),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }

            return ToolResult(
                success=True,  # Tool executed, even if command failed
                output=output,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output=None,
                error=f"Command timed out after {timeout} seconds",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
    ) -> str:
        """Describe what would be executed."""
        work_dir = Path(cwd).resolve() if cwd else Path.cwd()
        dangerous = " [DANGEROUS]" if is_command_dangerous(command) else ""
        return f"Would execute{dangerous}: {command}\n  in: {work_dir}"

    def preview(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
    ) -> dict:
        """Preview what would be executed."""
        work_dir = Path(cwd).resolve() if cwd else Path.cwd()

        blocked, reason = is_command_blocked(command)

        return {
            "command": command,
            "cwd": str(work_dir),
            "timeout": timeout,
            "blocked": blocked,
            "block_reason": reason if blocked else None,
            "dangerous": is_command_dangerous(command),
            "dangerous_patterns": [p for p in DANGEROUS_PATTERNS if p in command.lower()],
        }


@dataclass
class ShellExecBackgroundTool(Tool):
    """Execute shell commands in background."""

    name: str = "shell.background"
    description: str = "Execute a shell command in the background"
    risk_level: RiskLevel = RiskLevel.DANGEROUS
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("command", str, "The command to execute", required=True),
        ToolParam("cwd", str, "Working directory (default: current)", required=False, default=None),
    ])

    _processes: dict = field(default_factory=dict)
    _next_id: int = 1

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
    ) -> ToolResult:
        """Execute a shell command in background."""
        # Safety check
        blocked, reason = is_command_blocked(command)
        if blocked:
            return ToolResult(
                success=False,
                output=None,
                error=reason,
            )

        # Resolve working directory
        if cwd:
            work_dir = Path(cwd).resolve()
            if not work_dir.exists():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Working directory does not exist: {cwd}",
                )
        else:
            work_dir = Path.cwd()

        try:
            # Start process in background
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(work_dir),
                env={**os.environ, "TERM": "dumb"},
                start_new_session=True,
            )

            proc_id = self._next_id
            self._next_id += 1
            self._processes[proc_id] = process

            output = {
                "id": proc_id,
                "pid": process.pid,
                "command": command,
                "cwd": str(work_dir),
                "status": "running",
            }

            return ToolResult(success=True, output=output)

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(self, command: str, cwd: Optional[str] = None) -> str:
        """Describe what would be executed."""
        work_dir = Path(cwd).resolve() if cwd else Path.cwd()
        return f"Would start background process: {command}\n  in: {work_dir}"

    def preview(self, command: str, cwd: Optional[str] = None) -> dict:
        """Preview what would be executed."""
        work_dir = Path(cwd).resolve() if cwd else Path.cwd()
        blocked, reason = is_command_blocked(command)

        return {
            "command": command,
            "cwd": str(work_dir),
            "blocked": blocked,
            "block_reason": reason if blocked else None,
            "dangerous": is_command_dangerous(command),
        }


# Create tool instances
shell_exec = ShellExecTool()
shell_background = ShellExecBackgroundTool()

# Register tools
registry.register(shell_exec)
registry.register(shell_background)


# Convenience functions
def run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30,
) -> ToolResult:
    """Run a shell command."""
    return shell_exec.execute(command=command, cwd=cwd, timeout=timeout)


def run_background(command: str, cwd: Optional[str] = None) -> ToolResult:
    """Run a shell command in background."""
    return shell_background.execute(command=command, cwd=cwd)
