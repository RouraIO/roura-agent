"""
Roura Agent Approval Manager - Centralized approval handling for tool execution.

This module provides a unified approval system that:
- Assesses tool risk levels
- Manages user approval prompts
- Supports "approve all" mode for bulk operations
- Provides callback-based UI flexibility
- Tracks approval decisions for audit

© Roura.io
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from ..tools.base import RiskLevel


class ApprovalMode(Enum):
    """Approval behavior modes."""
    STRICT = "strict"           # Always prompt for moderate/dangerous
    PERMISSIVE = "permissive"   # Auto-approve moderate, prompt for dangerous
    AUTO = "auto"               # Auto-approve all (dangerous mode)
    DISABLED = "disabled"       # No approvals required (testing only)


@dataclass
class ApprovalRequest:
    """A request for user approval."""
    tool_name: str
    args: Dict[str, Any]
    risk_level: RiskLevel
    agent: str
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ApprovalDecision:
    """Record of an approval decision."""
    request: ApprovalRequest
    approved: bool
    reason: Optional[str] = None
    auto_approved: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


# Type for approval callback: (request) -> (approved, reason)
ApprovalCallback = Callable[[ApprovalRequest], tuple[bool, Optional[str]]]


class ApprovalManager:
    """
    Centralized manager for tool approval decisions.

    Features:
    - Risk-based approval requirements
    - Configurable approval modes
    - "Approve all" for batch operations
    - Pattern-based auto-approval (e.g., approve all fs.read)
    - Approval history for audit
    - Callback-based UI integration

    Thread-safe for parallel agent execution.
    """

    _instance: Optional[ApprovalManager] = None
    _lock = threading.Lock()

    def __new__(cls) -> ApprovalManager:
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
        self._mode = ApprovalMode.STRICT
        self._approval_callback: Optional[ApprovalCallback] = None
        self._auto_approved_tools: Set[str] = set()
        self._auto_approved_patterns: Set[str] = set()
        self._approval_history: List[ApprovalDecision] = []
        self._session_approved_all = False
        self._data_lock = threading.RLock()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing or new sessions)."""
        with cls._lock:
            cls._instance = None

    @classmethod
    def get_instance(cls) -> ApprovalManager:
        """Get the singleton instance."""
        return cls()

    # ===== Configuration =====

    def set_mode(self, mode: ApprovalMode) -> None:
        """Set the approval mode."""
        with self._data_lock:
            self._mode = mode

    def get_mode(self) -> ApprovalMode:
        """Get the current approval mode."""
        with self._data_lock:
            return self._mode

    def set_callback(self, callback: ApprovalCallback) -> None:
        """Set the approval callback for UI prompts."""
        with self._data_lock:
            self._approval_callback = callback

    def approve_all(self, enabled: bool = True) -> None:
        """Enable or disable approve-all mode for the session."""
        with self._data_lock:
            self._session_approved_all = enabled

    def is_approve_all(self) -> bool:
        """Check if approve-all mode is enabled."""
        with self._data_lock:
            return self._session_approved_all

    # ===== Auto-Approval Patterns =====

    def auto_approve_tool(self, tool_name: str) -> None:
        """Add a tool to auto-approve list."""
        with self._data_lock:
            self._auto_approved_tools.add(tool_name)

    def auto_approve_pattern(self, pattern: str) -> None:
        """
        Add a pattern to auto-approve.

        Patterns:
        - "fs.*" - All file system tools
        - "git.*" - All git tools
        - "*.read" - All read operations
        """
        with self._data_lock:
            self._auto_approved_patterns.add(pattern)

    def clear_auto_approvals(self) -> None:
        """Clear all auto-approval rules."""
        with self._data_lock:
            self._auto_approved_tools.clear()
            self._auto_approved_patterns.clear()

    def _is_auto_approved(self, tool_name: str) -> bool:
        """Check if a tool is auto-approved."""
        with self._data_lock:
            # Check exact match
            if tool_name in self._auto_approved_tools:
                return True

            # Check patterns
            for pattern in self._auto_approved_patterns:
                if self._matches_pattern(tool_name, pattern):
                    return True

            return False

    def _matches_pattern(self, tool_name: str, pattern: str) -> bool:
        """Check if a tool name matches a pattern."""
        if "*" not in pattern:
            return tool_name == pattern

        # Handle patterns like "fs.*", "*.read", etc.
        parts = pattern.split("*")
        if len(parts) == 2:
            prefix, suffix = parts
            return (
                (not prefix or tool_name.startswith(prefix))
                and (not suffix or tool_name.endswith(suffix))
            )
        return False

    # ===== Risk Assessment =====

    def needs_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel,
    ) -> bool:
        """
        Check if a tool needs approval based on current settings.

        Args:
            tool_name: Name of the tool
            risk_level: Risk level of the tool

        Returns:
            True if approval is needed
        """
        with self._data_lock:
            # Disabled mode - no approvals needed
            if self._mode == ApprovalMode.DISABLED:
                return False

            # Session approve-all mode
            if self._session_approved_all:
                return False

            # Auto-approved tools/patterns
            if self._is_auto_approved(tool_name):
                return False

            # Safe tools never need approval
            if risk_level == RiskLevel.SAFE:
                return False

            # Auto mode - approve everything
            if self._mode == ApprovalMode.AUTO:
                return False

            # Permissive mode - only dangerous needs approval
            if self._mode == ApprovalMode.PERMISSIVE:
                return risk_level == RiskLevel.DANGEROUS

            # Strict mode - moderate and dangerous need approval
            return risk_level in (RiskLevel.MODERATE, RiskLevel.DANGEROUS)

    def get_risk_description(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Generate a human-readable risk description."""
        descriptions = {
            "fs.write": f"Write file: {args.get('path', 'unknown')}",
            "fs.edit": f"Edit file: {args.get('path', 'unknown')}",
            "fs.delete": f"Delete file: {args.get('path', 'unknown')}",
            "shell.exec": f"Run command: {args.get('command', 'unknown')[:50]}",
            "git.commit": f"Git commit: {args.get('message', 'unknown')[:30]}",
            "git.push": "Push to remote repository",
            "git.reset": "Reset git state",
            "web.fetch": f"Fetch URL: {args.get('url', 'unknown')[:50]}",
        }
        return descriptions.get(tool_name, f"Execute {tool_name}")

    # ===== Approval Request =====

    def request_approval(
        self,
        tool_name: str,
        args: Dict[str, Any],
        risk_level: RiskLevel,
        agent: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Request approval for a tool execution.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            risk_level: Risk level of the tool
            agent: Name of the requesting agent

        Returns:
            (approved, reason) tuple
        """
        request = ApprovalRequest(
            tool_name=tool_name,
            args=args,
            risk_level=risk_level,
            agent=agent,
            description=self.get_risk_description(tool_name, args),
        )

        # Check if approval is needed
        if not self.needs_approval(tool_name, risk_level):
            decision = ApprovalDecision(
                request=request,
                approved=True,
                auto_approved=True,
                reason="Auto-approved",
            )
            self._record_decision(decision)
            return True, None

        # Use callback if available
        with self._data_lock:
            callback = self._approval_callback

        if callback:
            try:
                approved, reason = callback(request)
                decision = ApprovalDecision(
                    request=request,
                    approved=approved,
                    reason=reason,
                )
                self._record_decision(decision)
                return approved, reason
            except Exception as e:
                # Callback failed - deny for safety
                decision = ApprovalDecision(
                    request=request,
                    approved=False,
                    reason=f"Approval callback error: {e}",
                )
                self._record_decision(decision)
                return False, f"Approval error: {e}"

        # No callback - default deny for safety
        decision = ApprovalDecision(
            request=request,
            approved=False,
            reason="No approval callback configured",
        )
        self._record_decision(decision)
        return False, "Approval required but no callback configured"

    def _record_decision(self, decision: ApprovalDecision) -> None:
        """Record an approval decision."""
        with self._data_lock:
            self._approval_history.append(decision)

    # ===== History =====

    def get_history(self) -> List[ApprovalDecision]:
        """Get approval history."""
        with self._data_lock:
            return list(self._approval_history)

    def get_history_for_agent(self, agent: str) -> List[ApprovalDecision]:
        """Get approval history for a specific agent."""
        with self._data_lock:
            return [d for d in self._approval_history if d.request.agent == agent]

    def get_denied_requests(self) -> List[ApprovalDecision]:
        """Get all denied requests."""
        with self._data_lock:
            return [d for d in self._approval_history if not d.approved]

    def clear_history(self) -> None:
        """Clear approval history."""
        with self._data_lock:
            self._approval_history.clear()

    # ===== Summary =====

    def get_summary(self) -> Dict[str, Any]:
        """Get approval summary statistics."""
        with self._data_lock:
            total = len(self._approval_history)
            approved = sum(1 for d in self._approval_history if d.approved)
            auto_approved = sum(
                1 for d in self._approval_history if d.auto_approved
            )
            denied = total - approved

            return {
                "mode": self._mode.value,
                "session_approve_all": self._session_approved_all,
                "total_requests": total,
                "approved": approved,
                "auto_approved": auto_approved,
                "denied": denied,
                "auto_approved_tools": list(self._auto_approved_tools),
                "auto_approved_patterns": list(self._auto_approved_patterns),
            }


# Convenience function
def get_approval_manager() -> ApprovalManager:
    """Get the approval manager singleton."""
    return ApprovalManager.get_instance()


def create_console_approval_callback(console: Any) -> ApprovalCallback:
    """
    Create an approval callback that prompts on the console.

    Args:
        console: Rich console instance

    Returns:
        Approval callback function
    """
    def callback(request: ApprovalRequest) -> tuple[bool, Optional[str]]:
        # Format the request
        risk_color = {
            RiskLevel.SAFE: "green",
            RiskLevel.MODERATE: "yellow",
            RiskLevel.DANGEROUS: "red",
        }.get(request.risk_level, "white")

        console.print()
        console.print("[bold]Approval Required[/bold]")
        console.print(f"  Agent: {request.agent}")
        console.print(f"  Tool: {request.tool_name}")
        console.print(f"  Risk: [{risk_color}]{request.risk_level.value}[/{risk_color}]")
        console.print(f"  Action: {request.description}")
        console.print()

        # Get user input
        try:
            from rich.prompt import Confirm
            approved = Confirm.ask("Allow this action?", default=False)
            return approved, None
        except Exception:
            # If prompt fails, deny
            return False, "Unable to get user input"

    return callback
