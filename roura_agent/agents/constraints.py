"""
Roura Agent Constraint Checker - Validation rules for tool execution.

This module enforces safety constraints on tool execution:
- Must read before write
- File permission boundaries
- Agent-specific restrictions
- Path safety checks

© Roura.io
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, Dict, List, Set, Callable
from enum import Enum

from .context import get_shared_context, SharedExecutionContext


class ConstraintViolation(Enum):
    """Types of constraint violations."""
    READ_BEFORE_WRITE = "read_before_write"
    PERMISSION_DENIED = "permission_denied"
    PATH_NOT_ALLOWED = "path_not_allowed"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    AGENT_RESTRICTED = "agent_restricted"
    PATTERN_BLOCKED = "pattern_blocked"


@dataclass
class ViolationResult:
    """Result of a constraint check that failed."""
    violation: ConstraintViolation
    message: str
    tool_name: str
    args: Dict[str, Any]
    agent: str
    suggestion: Optional[str] = None


@dataclass
class ConstraintResult:
    """Result of a constraint check."""
    allowed: bool
    violations: List[ViolationResult] = field(default_factory=list)

    @property
    def error_message(self) -> Optional[str]:
        """Get combined error message from violations."""
        if self.allowed:
            return None
        return "; ".join(v.message for v in self.violations)


@dataclass
class AgentConstraints:
    """Constraints specific to an agent."""
    agent_name: str
    allowed_tools: Set[str] = field(default_factory=set)
    allowed_paths: List[str] = field(default_factory=list)  # Patterns
    blocked_paths: List[str] = field(default_factory=list)  # Patterns
    require_read_before_write: bool = True
    max_file_size_bytes: int = 1_000_000  # 1MB default
    can_create_files: bool = True
    can_delete_files: bool = False
    can_execute_shell: bool = False


class ConstraintChecker:
    """
    Checks and enforces constraints on tool execution.

    Constraints include:
    - Read-before-write requirement
    - Path-based restrictions (protect system files, etc.)
    - Agent-specific tool permissions
    - File size limits
    - Pattern-based blocking

    Thread-safe for parallel agent execution.
    """

    _instance: Optional["ConstraintChecker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConstraintChecker":
        """Singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize()
                    cls._instance = instance
        return cls._instance

    def _initialize(self) -> None:
        """Initialize instance state."""
        self._agent_constraints: Dict[str, AgentConstraints] = {}
        self._global_blocked_paths: Set[str] = set()
        self._global_blocked_patterns: List[str] = []
        self._context: Optional[SharedExecutionContext] = None
        self._enabled = True
        self._data_lock = threading.RLock()

        # Set up default blocked paths
        self._setup_default_constraints()

    def _setup_default_constraints(self) -> None:
        """Set up default safety constraints."""
        # Globally blocked paths (never modify these)
        self._global_blocked_paths = {
            "/etc",
            "/bin",
            "/sbin",
            "/usr/bin",
            "/usr/sbin",
            "/System",
            "/Library",
            "/var",
            "~/.ssh",
            "~/.gnupg",
            "~/.aws",
        }

        # Blocked patterns (sensitive files)
        self._global_blocked_patterns = [
            r".*\.env$",           # Environment files
            r".*\.pem$",           # Private keys
            r".*\.key$",           # Key files
            r".*\.p12$",           # PKCS12 files
            r".*id_rsa.*",         # SSH keys
            r".*id_ed25519.*",     # SSH keys
            r".*\.credentials.*",  # Credential files
            r".*\.secret.*",       # Secret files
        ]

        # Default agent constraints
        self._setup_agent_defaults()

    def _setup_agent_defaults(self) -> None:
        """Set up default constraints for each agent type."""
        # Code agent - can read/write source files
        self._agent_constraints["code"] = AgentConstraints(
            agent_name="code",
            allowed_tools={
                "fs.read", "fs.list", "fs.write", "fs.edit",
                "glob.find", "grep.search",
            },
            can_create_files=True,
            can_delete_files=False,
            can_execute_shell=False,
        )

        # Test agent - can run tests, write test files
        self._agent_constraints["test"] = AgentConstraints(
            agent_name="test",
            allowed_tools={
                "fs.read", "fs.list", "fs.write", "fs.edit",
                "shell.exec", "glob.find", "grep.search",
            },
            allowed_paths=["tests/", "test/", "*_test.py", "test_*.py"],
            can_create_files=True,
            can_execute_shell=True,
        )

        # Debug agent - can read, edit, run commands
        self._agent_constraints["debug"] = AgentConstraints(
            agent_name="debug",
            allowed_tools={
                "fs.read", "fs.list", "fs.edit",
                "shell.exec", "glob.find", "grep.search",
            },
            can_create_files=False,
            can_execute_shell=True,
        )

        # Git agent - can use git tools
        self._agent_constraints["git"] = AgentConstraints(
            agent_name="git",
            allowed_tools={
                "fs.read", "fs.list",
                "git.status", "git.diff", "git.log",
                "git.add", "git.commit",
            },
            can_create_files=False,
            can_delete_files=False,
        )

        # Review agent - read only
        self._agent_constraints["review"] = AgentConstraints(
            agent_name="review",
            allowed_tools={
                "fs.read", "fs.list",
                "glob.find", "grep.search",
            },
            can_create_files=False,
            can_delete_files=False,
            require_read_before_write=False,  # Can't write anyway
        )

        # Research agent - can search web
        self._agent_constraints["research"] = AgentConstraints(
            agent_name="research",
            allowed_tools={
                "fs.read", "fs.list",
                "glob.find", "grep.search",
                "web.fetch", "web.search",
            },
            can_create_files=False,
        )

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing or new sessions)."""
        with cls._lock:
            cls._instance = None

    @classmethod
    def get_instance(cls) -> "ConstraintChecker":
        """Get the singleton instance."""
        return cls()

    # ===== Configuration =====

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable constraint checking."""
        with self._data_lock:
            self._enabled = enabled

    def is_enabled(self) -> bool:
        """Check if constraint checking is enabled."""
        with self._data_lock:
            return self._enabled

    def set_context(self, context: SharedExecutionContext) -> None:
        """Set the shared execution context."""
        with self._data_lock:
            self._context = context

    def get_context(self) -> SharedExecutionContext:
        """Get the shared execution context (creates if needed)."""
        with self._data_lock:
            if self._context is None:
                self._context = get_shared_context()
            return self._context

    def set_agent_constraints(self, constraints: AgentConstraints) -> None:
        """Set constraints for an agent."""
        with self._data_lock:
            self._agent_constraints[constraints.agent_name] = constraints

    def get_agent_constraints(self, agent_name: str) -> Optional[AgentConstraints]:
        """Get constraints for an agent."""
        with self._data_lock:
            return self._agent_constraints.get(agent_name)

    def add_blocked_path(self, path: str) -> None:
        """Add a globally blocked path."""
        with self._data_lock:
            self._global_blocked_paths.add(path)

    def add_blocked_pattern(self, pattern: str) -> None:
        """Add a globally blocked pattern."""
        with self._data_lock:
            self._global_blocked_patterns.append(pattern)

    # ===== Constraint Checking =====

    def check(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
    ) -> ConstraintResult:
        """
        Check if a tool execution is allowed.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            agent: Name of the requesting agent

        Returns:
            ConstraintResult with allowed status and any violations
        """
        with self._data_lock:
            if not self._enabled:
                return ConstraintResult(allowed=True)

        violations: List[ViolationResult] = []

        # Check agent tool permissions
        violation = self._check_tool_permission(tool_name, agent)
        if violation:
            violations.append(violation)

        # Check path constraints if applicable
        path = args.get("path")
        if path:
            path_violations = self._check_path_constraints(tool_name, path, agent)
            violations.extend(path_violations)

        # Check read-before-write
        if tool_name in ("fs.write", "fs.edit"):
            violation = self._check_read_before_write(path, agent)
            if violation:
                violations.append(violation)

        # Check shell command if applicable
        if tool_name == "shell.exec":
            command = args.get("command", "")
            violation = self._check_shell_command(command, agent)
            if violation:
                violations.append(violation)

        return ConstraintResult(
            allowed=len(violations) == 0,
            violations=violations,
        )

    def _check_tool_permission(
        self,
        tool_name: str,
        agent: str,
    ) -> Optional[ViolationResult]:
        """Check if agent is allowed to use the tool."""
        constraints = self.get_agent_constraints(agent)
        if constraints is None:
            return None  # No constraints = allowed

        if tool_name not in constraints.allowed_tools:
            return ViolationResult(
                violation=ConstraintViolation.TOOL_NOT_ALLOWED,
                message=f"Agent '{agent}' is not allowed to use tool '{tool_name}'",
                tool_name=tool_name,
                args={},
                agent=agent,
                suggestion=f"Available tools for {agent}: {', '.join(sorted(constraints.allowed_tools))}",
            )
        return None

    def _check_path_constraints(
        self,
        tool_name: str,
        path: str,
        agent: str,
    ) -> List[ViolationResult]:
        """Check path-based constraints."""
        violations = []
        resolved = str(Path(path).expanduser().resolve())

        # Check global blocked paths
        for blocked in self._global_blocked_paths:
            blocked_resolved = str(Path(blocked).expanduser().resolve())
            if resolved.startswith(blocked_resolved):
                violations.append(ViolationResult(
                    violation=ConstraintViolation.PATH_NOT_ALLOWED,
                    message=f"Path '{path}' is in a protected directory",
                    tool_name=tool_name,
                    args={"path": path},
                    agent=agent,
                    suggestion="System directories cannot be modified",
                ))
                break

        # Check global blocked patterns
        for pattern in self._global_blocked_patterns:
            if re.match(pattern, path, re.IGNORECASE):
                violations.append(ViolationResult(
                    violation=ConstraintViolation.PATTERN_BLOCKED,
                    message=f"Path '{path}' matches blocked pattern (sensitive file)",
                    tool_name=tool_name,
                    args={"path": path},
                    agent=agent,
                    suggestion="Cannot modify sensitive files like .env, keys, etc.",
                ))
                break

        # Check agent-specific path constraints
        constraints = self.get_agent_constraints(agent)
        if constraints and constraints.blocked_paths:
            for pattern in constraints.blocked_paths:
                if self._path_matches_pattern(path, pattern):
                    violations.append(ViolationResult(
                        violation=ConstraintViolation.AGENT_RESTRICTED,
                        message=f"Agent '{agent}' cannot access path matching '{pattern}'",
                        tool_name=tool_name,
                        args={"path": path},
                        agent=agent,
                    ))
                    break

        return violations

    def _check_read_before_write(
        self,
        path: Optional[str],
        agent: str,
    ) -> Optional[ViolationResult]:
        """Check read-before-write constraint."""
        if not path:
            return None

        constraints = self.get_agent_constraints(agent)
        if constraints and not constraints.require_read_before_write:
            return None

        # Check if file exists and hasn't been read
        file_path = Path(path).expanduser().resolve()
        if file_path.exists():
            context = self.get_context()
            if not context.has_read(str(file_path)):
                return ViolationResult(
                    violation=ConstraintViolation.READ_BEFORE_WRITE,
                    message=f"Must read file before modifying: {path}",
                    tool_name="fs.write",
                    args={"path": path},
                    agent=agent,
                    suggestion=f"Use fs.read to read '{path}' first",
                )

        return None

    def _check_shell_command(
        self,
        command: str,
        agent: str,
    ) -> Optional[ViolationResult]:
        """Check shell command safety."""
        constraints = self.get_agent_constraints(agent)
        if constraints and not constraints.can_execute_shell:
            return ViolationResult(
                violation=ConstraintViolation.AGENT_RESTRICTED,
                message=f"Agent '{agent}' is not allowed to execute shell commands",
                tool_name="shell.exec",
                args={"command": command},
                agent=agent,
            )

        # Check for dangerous commands
        dangerous_patterns = [
            r"\brm\s+-rf\s+/",       # rm -rf /
            r"\brm\s+-rf\s+\*",      # rm -rf *
            r"\bmkfs\b",              # Format disk
            r"\bdd\s+if=",            # Disk operations
            r":(){:|:&};:",           # Fork bomb
            r"\bsudo\s+rm\b",         # sudo rm
            r"\bchmod\s+777\s+/",     # chmod 777 /
            r">\s*/dev/sd",           # Write to disk device
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return ViolationResult(
                    violation=ConstraintViolation.PATTERN_BLOCKED,
                    message=f"Dangerous shell command pattern detected",
                    tool_name="shell.exec",
                    args={"command": command},
                    agent=agent,
                    suggestion="This command is blocked for safety",
                )

        return None

    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches a pattern."""
        # Simple glob-like matching
        if "*" not in pattern:
            return path == pattern or path.endswith(f"/{pattern}")

        # Convert glob to regex
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        return bool(re.match(regex, path))

    # ===== Auto-fix =====

    def auto_fix_violation(
        self,
        violation: ViolationResult,
        tool_executor: Any,
    ) -> bool:
        """
        Attempt to automatically fix a constraint violation.

        Args:
            violation: The violation to fix
            tool_executor: Tool executor to use for fixes

        Returns:
            True if violation was fixed
        """
        if violation.violation == ConstraintViolation.READ_BEFORE_WRITE:
            # Auto-read the file
            path = violation.args.get("path")
            if path and hasattr(tool_executor, "execute_tool"):
                try:
                    result = tool_executor.execute_tool("fs.read", path=path)
                    return result.success
                except Exception:
                    return False

        return False


# Convenience function
def get_constraint_checker() -> ConstraintChecker:
    """Get the constraint checker singleton."""
    return ConstraintChecker.get_instance()
