"""
Roura Agent Execution Loop - Apply → Run → Feed → Repeat.

Implements the verification loop that iterates until builds/tests pass.
Maximum 12 iterations (local powerhouse - can grind).

© Roura.io
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


class ExecutionStatus(Enum):
    """Status of execution loop."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    STALLED = "stalled"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class ExecutionResult:
    """Result of running a command."""
    success: bool
    commands_run: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""
    exit_code: int = -1
    failure_signature: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class FileEdit:
    """A file edit operation."""
    path: str
    action: str  # "create", "modify", "delete"
    content: Optional[str] = None
    old_content: Optional[str] = None


@dataclass
class LoopIteration:
    """Record of a single loop iteration."""
    iteration: int
    edits_applied: int
    commands_run: list[str]
    success: bool
    failure_signature: Optional[str]
    duration: float


@dataclass
class VerificationResult:
    """Complete result of verification loop."""
    status: ExecutionStatus
    iterations: list[LoopIteration] = field(default_factory=list)
    final_result: Optional[ExecutionResult] = None
    total_duration: float = 0.0
    edits_total: int = 0
    unblocker_invoked: bool = False
    message: str = ""


# Maximum lines to capture from stdout/stderr
MAX_OUTPUT_LINES = 100

# Default timeout for commands
DEFAULT_TIMEOUT = 120


def apply_edits(edits: list[FileEdit], root: Path) -> list[str]:
    """
    Apply file edits atomically.

    Writes to temp file first, then moves to final location.

    Args:
        edits: List of FileEdit operations
        root: Repository root

    Returns:
        List of paths that were modified
    """
    root = Path(root).resolve()
    modified = []

    for edit in edits:
        path = root / edit.path

        try:
            if edit.action == "delete":
                if path.exists():
                    path.unlink()
                    modified.append(edit.path)

            elif edit.action in ("create", "modify"):
                if edit.content is None:
                    continue

                # Ensure parent directory exists
                path.parent.mkdir(parents=True, exist_ok=True)

                # Write atomically via temp file
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    dir=path.parent,
                    delete=False,
                    suffix=".tmp",
                ) as tmp:
                    tmp.write(edit.content)
                    tmp_path = tmp.name

                # Move to final location
                os.replace(tmp_path, path)
                modified.append(edit.path)

        except Exception as e:
            # Log but continue
            print(f"Warning: Failed to apply edit to {edit.path}: {e}")

    return modified


def run_commands(
    commands: list[str],
    cwd: Optional[Path] = None,
    timeout_s: int = DEFAULT_TIMEOUT,
    env: Optional[dict] = None,
) -> ExecutionResult:
    """
    Run a list of commands and collect output.

    Args:
        commands: Commands to run
        cwd: Working directory
        timeout_s: Timeout in seconds
        env: Environment variables

    Returns:
        ExecutionResult with output and status
    """
    start_time = time.time()
    result = ExecutionResult(
        success=True,
        commands_run=commands,
    )

    # Merge environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    stdout_lines = []
    stderr_lines = []

    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=run_env,
            )

            # Collect output
            if proc.stdout:
                stdout_lines.extend(proc.stdout.splitlines()[-MAX_OUTPUT_LINES:])
            if proc.stderr:
                stderr_lines.extend(proc.stderr.splitlines()[-MAX_OUTPUT_LINES:])

            result.exit_code = proc.returncode

            if proc.returncode != 0:
                result.success = False
                result.failure_signature = _derive_failure_signature(
                    proc.stderr or proc.stdout
                )
                break

        except subprocess.TimeoutExpired:
            result.success = False
            result.failure_signature = "TIMEOUT"
            stderr_lines.append(f"Command timed out after {timeout_s}s: {cmd}")
            break

        except Exception as e:
            result.success = False
            result.failure_signature = f"EXCEPTION:{type(e).__name__}"
            stderr_lines.append(str(e))
            break

    result.stdout_tail = "\n".join(stdout_lines[-MAX_OUTPUT_LINES:])
    result.stderr_tail = "\n".join(stderr_lines[-MAX_OUTPUT_LINES:])
    result.duration_seconds = time.time() - start_time

    return result


def _derive_failure_signature(output: str) -> str:
    """
    Derive a stable failure signature from output.

    Used to detect repeated failures (stalls).
    """
    if not output:
        return "EMPTY_OUTPUT"

    # Look for common error patterns
    lines = output.splitlines()

    # Try to find the most informative error line
    for line in reversed(lines):
        line = line.strip()

        # Skip empty lines and common noise
        if not line:
            continue
        if line.startswith("FAILED"):
            return f"FAILED:{line[:50]}"
        if "error" in line.lower():
            return f"ERROR:{line[:50]}"
        if "exception" in line.lower():
            return f"EXCEPTION:{line[:50]}"
        if "traceback" in line.lower():
            return "TRACEBACK"

    # Fallback: hash of last few lines
    import hashlib
    sig = hashlib.md5("\n".join(lines[-5:]).encode()).hexdigest()[:12]
    return f"HASH:{sig}"


def verification_loop(
    job_prompt: str,
    model_call_fn: Callable[[str], dict],
    root: Path,
    commands: Optional[list[str]] = None,
    max_iterations: int = 12,
    unblocker_fn: Optional[Callable[[str], str]] = None,
) -> VerificationResult:
    """
    Run the verification loop until success or max iterations.

    Algorithm:
    1. Call model with job_prompt + context
    2. Parse model output into edits + commands
    3. Apply edits
    4. Run commands
    5. If success: return
    6. If same failure signature twice: invoke unblocker
    7. Continue until max_iterations

    Args:
        job_prompt: Initial prompt describing the task
        model_call_fn: Function to call the LLM (returns dict with edits/commands)
        root: Repository root
        commands: Commands to run for verification (auto-detect if None)
        max_iterations: Maximum iterations (default 12)
        unblocker_fn: Function to call when stalled

    Returns:
        VerificationResult with complete history
    """
    root = Path(root).resolve()
    start_time = time.time()

    result = VerificationResult(
        status=ExecutionStatus.MAX_ITERATIONS,
    )

    # Auto-detect verification commands if not provided
    if commands is None:
        commands = _auto_detect_commands(root)

    # Track failure signatures for stall detection
    failure_history: list[str] = []
    context = job_prompt

    for i in range(1, max_iterations + 1):
        iteration_start = time.time()

        # Call model
        try:
            model_output = model_call_fn(context)
        except Exception as e:
            result.message = f"Model call failed: {e}"
            result.status = ExecutionStatus.FAILURE
            break

        # Parse edits from model output
        edits = _parse_edits(model_output)

        # Apply edits
        modified = apply_edits(edits, root)
        result.edits_total += len(modified)

        # Run verification commands
        exec_result = run_commands(commands, cwd=root)

        # Record iteration
        iteration = LoopIteration(
            iteration=i,
            edits_applied=len(modified),
            commands_run=commands,
            success=exec_result.success,
            failure_signature=exec_result.failure_signature,
            duration=time.time() - iteration_start,
        )
        result.iterations.append(iteration)

        if exec_result.success:
            result.status = ExecutionStatus.SUCCESS
            result.final_result = exec_result
            result.message = f"Verification passed after {i} iteration(s)"
            break

        # Check for stall (same failure twice)
        if exec_result.failure_signature:
            if exec_result.failure_signature in failure_history:
                # Stall detected - invoke unblocker
                if unblocker_fn:
                    result.unblocker_invoked = True
                    unblocker_output = unblocker_fn(exec_result.failure_signature)
                    context = f"{job_prompt}\n\nUNBLOCKER DIAGNOSIS:\n{unblocker_output}\n\nLAST ERROR:\n{exec_result.stderr_tail}"
                else:
                    result.status = ExecutionStatus.STALLED
                    result.message = f"Stalled on repeated failure: {exec_result.failure_signature}"
                    result.final_result = exec_result
                    break
            else:
                failure_history.append(exec_result.failure_signature)

        # Update context for next iteration
        context = f"""{job_prompt}

ITERATION {i} FAILED:
Exit code: {exec_result.exit_code}
Failure signature: {exec_result.failure_signature}

STDERR:
{exec_result.stderr_tail[-2000:]}

STDOUT:
{exec_result.stdout_tail[-1000:]}

Fix the issue and try again. Focus on the error above."""

    result.total_duration = time.time() - start_time

    if result.status == ExecutionStatus.MAX_ITERATIONS:
        result.message = f"Max iterations ({max_iterations}) reached without success"
        if result.iterations:
            result.final_result = ExecutionResult(
                success=False,
                failure_signature=result.iterations[-1].failure_signature,
            )

    return result


def _auto_detect_commands(root: Path) -> list[str]:
    """Auto-detect verification commands based on project type."""
    commands = []

    # Python
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        if (root / "tests").exists():
            commands.append("python -m pytest --tb=short -q")
        else:
            commands.append("python -m py_compile $(find . -name '*.py' -not -path './.venv/*' | head -10)")

    # Node.js
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                commands.append("npm test")
            if "build" in scripts:
                commands.append("npm run build")
        except Exception:
            pass

    # Swift
    if (root / "Package.swift").exists():
        commands.append("swift build")

    # Go
    if (root / "go.mod").exists():
        commands.append("go build ./...")

    # Rust
    if (root / "Cargo.toml").exists():
        commands.append("cargo build")

    # Default
    if not commands:
        commands.append("echo 'No verification commands detected'")

    return commands


def _parse_edits(model_output: dict) -> list[FileEdit]:
    """Parse file edits from model output."""
    edits = []

    # Handle direct edits list
    if "edits" in model_output:
        for edit_data in model_output["edits"]:
            edits.append(FileEdit(
                path=edit_data.get("path", ""),
                action=edit_data.get("action", "modify"),
                content=edit_data.get("content"),
                old_content=edit_data.get("old_content"),
            ))

    # Handle files dict format
    if "files" in model_output:
        for path, content in model_output["files"].items():
            edits.append(FileEdit(
                path=path,
                action="create" if content else "delete",
                content=content,
            ))

    return edits


def format_verification_result(result: VerificationResult) -> str:
    """Format verification result for display."""
    lines = [
        "=" * 50,
        "VERIFICATION LOOP RESULT",
        "=" * 50,
        f"Status: {result.status.value}",
        f"Iterations: {len(result.iterations)}",
        f"Total edits: {result.edits_total}",
        f"Duration: {result.total_duration:.1f}s",
    ]

    if result.unblocker_invoked:
        lines.append("Unblocker: Invoked")

    lines.append("")
    lines.append("ITERATION HISTORY:")

    for it in result.iterations:
        status = "✓" if it.success else "✗"
        lines.append(f"  {status} Iteration {it.iteration}: {it.edits_applied} edits, {it.duration:.1f}s")
        if it.failure_signature:
            lines.append(f"      Failure: {it.failure_signature}")

    if result.message:
        lines.append("")
        lines.append(f"Message: {result.message}")

    return "\n".join(lines)
