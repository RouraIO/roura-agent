"""
Tests for the approval manager.

© Roura.io
"""
import pytest
from unittest.mock import Mock

from roura_agent.agents.approval import (
    ApprovalManager,
    ApprovalMode,
    ApprovalRequest,
    ApprovalDecision,
    get_approval_manager,
    create_console_approval_callback,
)
from roura_agent.tools.base import RiskLevel


class TestApprovalMode:
    """Tests for ApprovalMode enum."""

    def test_modes_exist(self):
        """Test all approval modes exist."""
        assert ApprovalMode.STRICT.value == "strict"
        assert ApprovalMode.PERMISSIVE.value == "permissive"
        assert ApprovalMode.AUTO.value == "auto"
        assert ApprovalMode.DISABLED.value == "disabled"


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_create_request(self):
        """Test creating an approval request."""
        request = ApprovalRequest(
            tool_name="fs.write",
            args={"path": "/file.py"},
            risk_level=RiskLevel.MODERATE,
            agent="code",
            description="Write file",
        )
        assert request.tool_name == "fs.write"
        assert request.risk_level == RiskLevel.MODERATE
        assert request.agent == "code"
        assert request.timestamp is not None


class TestApprovalDecision:
    """Tests for ApprovalDecision dataclass."""

    def test_create_decision(self):
        """Test creating an approval decision."""
        request = ApprovalRequest(
            tool_name="fs.write",
            args={},
            risk_level=RiskLevel.MODERATE,
            agent="code",
        )
        decision = ApprovalDecision(
            request=request,
            approved=True,
            reason="User approved",
        )
        assert decision.approved is True
        assert decision.reason == "User approved"


class TestApprovalManager:
    """Tests for ApprovalManager."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_singleton_pattern(self):
        """Test that ApprovalManager is a singleton."""
        m1 = ApprovalManager()
        m2 = ApprovalManager()
        assert m1 is m2

    def test_get_instance(self):
        """Test get_instance returns singleton."""
        m1 = ApprovalManager.get_instance()
        m2 = ApprovalManager.get_instance()
        assert m1 is m2

    def test_default_mode_is_strict(self):
        """Test default mode is STRICT."""
        manager = ApprovalManager()
        assert manager.get_mode() == ApprovalMode.STRICT

    def test_set_mode(self):
        """Test setting approval mode."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.PERMISSIVE)
        assert manager.get_mode() == ApprovalMode.PERMISSIVE

    def test_approve_all(self):
        """Test approve all mode."""
        manager = ApprovalManager()
        assert manager.is_approve_all() is False

        manager.approve_all(True)
        assert manager.is_approve_all() is True

        manager.approve_all(False)
        assert manager.is_approve_all() is False


class TestNeedsApproval:
    """Tests for needs_approval logic."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_safe_tools_never_need_approval(self):
        """Test SAFE tools never need approval."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        assert manager.needs_approval("fs.read", RiskLevel.SAFE) is False

    def test_strict_mode_requires_moderate(self):
        """Test STRICT mode requires approval for moderate."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is True

    def test_strict_mode_requires_dangerous(self):
        """Test STRICT mode requires approval for dangerous."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is True

    def test_permissive_mode_auto_approves_moderate(self):
        """Test PERMISSIVE mode auto-approves moderate."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.PERMISSIVE)
        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is False
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is True

    def test_auto_mode_approves_everything(self):
        """Test AUTO mode approves everything."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.AUTO)
        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is False
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is False

    def test_disabled_mode_no_approval(self):
        """Test DISABLED mode needs no approval."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.DISABLED)
        assert manager.needs_approval("anything", RiskLevel.DANGEROUS) is False

    def test_session_approve_all_overrides(self):
        """Test session approve-all overrides mode."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        manager.approve_all(True)
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is False


class TestAutoApprovalPatterns:
    """Tests for auto-approval patterns."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_auto_approve_tool(self):
        """Test auto-approving a specific tool."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        manager.auto_approve_tool("fs.write")

        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is False
        assert manager.needs_approval("fs.edit", RiskLevel.MODERATE) is True

    def test_auto_approve_pattern_prefix(self):
        """Test auto-approving with prefix pattern."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        manager.auto_approve_pattern("fs.*")

        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is False
        assert manager.needs_approval("fs.edit", RiskLevel.MODERATE) is False
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is True

    def test_auto_approve_pattern_suffix(self):
        """Test auto-approving with suffix pattern."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        manager.auto_approve_pattern("*.read")

        assert manager.needs_approval("fs.read", RiskLevel.SAFE) is False
        assert manager.needs_approval("db.read", RiskLevel.MODERATE) is False

    def test_clear_auto_approvals(self):
        """Test clearing auto-approval rules."""
        manager = ApprovalManager()
        manager.auto_approve_tool("fs.write")
        manager.auto_approve_pattern("git.*")
        manager.clear_auto_approvals()

        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is True


class TestRequestApproval:
    """Tests for request_approval method."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_auto_approves_safe(self):
        """Test safe tools are auto-approved."""
        manager = ApprovalManager()
        approved, reason = manager.request_approval(
            tool_name="fs.read",
            args={"path": "/file.py"},
            risk_level=RiskLevel.SAFE,
            agent="code",
        )
        assert approved is True

    def test_uses_callback_for_approval(self):
        """Test callback is used for approval decision."""
        manager = ApprovalManager()

        def approve_callback(request):
            return True, "User approved"

        manager.set_callback(approve_callback)

        approved, reason = manager.request_approval(
            tool_name="fs.write",
            args={"path": "/file.py"},
            risk_level=RiskLevel.MODERATE,
            agent="code",
        )
        assert approved is True

    def test_callback_can_deny(self):
        """Test callback can deny approval."""
        manager = ApprovalManager()

        def deny_callback(request):
            return False, "User denied"

        manager.set_callback(deny_callback)

        approved, reason = manager.request_approval(
            tool_name="fs.write",
            args={"path": "/file.py"},
            risk_level=RiskLevel.MODERATE,
            agent="code",
        )
        assert approved is False
        assert reason == "User denied"

    def test_no_callback_denies_by_default(self):
        """Test no callback means denial for risky operations."""
        manager = ApprovalManager()
        # No callback set

        approved, reason = manager.request_approval(
            tool_name="fs.write",
            args={"path": "/file.py"},
            risk_level=RiskLevel.MODERATE,
            agent="code",
        )
        assert approved is False
        assert "callback" in reason.lower()

    def test_records_decisions(self):
        """Test that decisions are recorded."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.AUTO)

        manager.request_approval(
            tool_name="fs.write",
            args={},
            risk_level=RiskLevel.MODERATE,
            agent="code",
        )

        history = manager.get_history()
        assert len(history) == 1
        assert history[0].approved is True


class TestApprovalHistory:
    """Tests for approval history."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_get_history(self):
        """Test getting approval history."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.AUTO)

        manager.request_approval("fs.read", {}, RiskLevel.SAFE, "code")
        manager.request_approval("fs.write", {}, RiskLevel.MODERATE, "test")

        history = manager.get_history()
        assert len(history) == 2

    def test_get_history_for_agent(self):
        """Test filtering history by agent."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.AUTO)

        manager.request_approval("fs.read", {}, RiskLevel.SAFE, "code")
        manager.request_approval("shell.exec", {}, RiskLevel.DANGEROUS, "test")

        code_history = manager.get_history_for_agent("code")
        assert len(code_history) == 1
        assert code_history[0].request.agent == "code"

    def test_get_denied_requests(self):
        """Test getting denied requests."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.STRICT)
        # No callback means denials

        manager.request_approval("fs.write", {}, RiskLevel.MODERATE, "code")

        denied = manager.get_denied_requests()
        assert len(denied) == 1

    def test_clear_history(self):
        """Test clearing history."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.AUTO)

        manager.request_approval("fs.read", {}, RiskLevel.SAFE, "code")
        assert len(manager.get_history()) == 1

        manager.clear_history()
        assert len(manager.get_history()) == 0


class TestRiskDescription:
    """Tests for risk description generation."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_write_description(self):
        """Test description for file write."""
        manager = ApprovalManager()
        desc = manager.get_risk_description("fs.write", {"path": "/test.py"})
        assert "Write" in desc
        assert "/test.py" in desc

    def test_shell_description(self):
        """Test description for shell command."""
        manager = ApprovalManager()
        desc = manager.get_risk_description("shell.exec", {"command": "npm test"})
        assert "command" in desc.lower()
        assert "npm" in desc

    def test_unknown_tool_description(self):
        """Test description for unknown tool."""
        manager = ApprovalManager()
        desc = manager.get_risk_description("unknown.tool", {})
        assert "unknown.tool" in desc


class TestGetSummary:
    """Tests for summary statistics."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_get_summary(self):
        """Test getting summary statistics."""
        manager = ApprovalManager()
        manager.set_mode(ApprovalMode.AUTO)
        manager.auto_approve_tool("fs.read")

        manager.request_approval("fs.read", {}, RiskLevel.SAFE, "code")

        summary = manager.get_summary()
        assert summary["mode"] == "auto"
        assert summary["total_requests"] == 1
        assert "fs.read" in summary["auto_approved_tools"]


class TestGetApprovalManager:
    """Tests for get_approval_manager helper."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ApprovalManager.reset()
        yield
        ApprovalManager.reset()

    def test_returns_singleton(self):
        """Test get_approval_manager returns singleton."""
        m1 = get_approval_manager()
        m2 = get_approval_manager()
        assert m1 is m2
