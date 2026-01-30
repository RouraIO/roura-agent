"""
Tests for the constraint checker.

© Roura.io
"""
import pytest
from unittest.mock import Mock
from pathlib import Path
import tempfile

from roura_agent.agents.constraints import (
    ConstraintChecker,
    ConstraintViolation,
    ConstraintResult,
    ViolationResult,
    AgentConstraints,
    get_constraint_checker,
)
from roura_agent.agents.context import SharedExecutionContext


class TestConstraintViolation:
    """Tests for ConstraintViolation enum."""

    def test_violations_exist(self):
        """Test all violation types exist."""
        assert ConstraintViolation.READ_BEFORE_WRITE.value == "read_before_write"
        assert ConstraintViolation.PERMISSION_DENIED.value == "permission_denied"
        assert ConstraintViolation.PATH_NOT_ALLOWED.value == "path_not_allowed"
        assert ConstraintViolation.TOOL_NOT_ALLOWED.value == "tool_not_allowed"
        assert ConstraintViolation.AGENT_RESTRICTED.value == "agent_restricted"
        assert ConstraintViolation.PATTERN_BLOCKED.value == "pattern_blocked"


class TestViolationResult:
    """Tests for ViolationResult dataclass."""

    def test_create_violation(self):
        """Test creating a violation result."""
        violation = ViolationResult(
            violation=ConstraintViolation.READ_BEFORE_WRITE,
            message="Must read before write",
            tool_name="fs.write",
            args={"path": "/file.py"},
            agent="code",
            suggestion="Use fs.read first",
        )
        assert violation.violation == ConstraintViolation.READ_BEFORE_WRITE
        assert "read" in violation.message.lower()
        assert violation.suggestion is not None


class TestConstraintResult:
    """Tests for ConstraintResult dataclass."""

    def test_allowed_result(self):
        """Test creating an allowed result."""
        result = ConstraintResult(allowed=True)
        assert result.allowed is True
        assert result.error_message is None

    def test_denied_result(self):
        """Test creating a denied result."""
        violation = ViolationResult(
            violation=ConstraintViolation.TOOL_NOT_ALLOWED,
            message="Tool not allowed",
            tool_name="shell.exec",
            args={},
            agent="review",
        )
        result = ConstraintResult(allowed=False, violations=[violation])
        assert result.allowed is False
        assert "Tool not allowed" in result.error_message


class TestAgentConstraints:
    """Tests for AgentConstraints dataclass."""

    def test_create_constraints(self):
        """Test creating agent constraints."""
        constraints = AgentConstraints(
            agent_name="test",
            allowed_tools={"fs.read", "fs.write"},
            can_create_files=True,
            can_delete_files=False,
            can_execute_shell=True,
        )
        assert constraints.agent_name == "test"
        assert "fs.read" in constraints.allowed_tools
        assert constraints.can_create_files is True
        assert constraints.can_delete_files is False


class TestConstraintChecker:
    """Tests for ConstraintChecker."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset singletons before each test."""
        ConstraintChecker.reset()
        SharedExecutionContext.reset()
        yield
        ConstraintChecker.reset()
        SharedExecutionContext.reset()

    def test_singleton_pattern(self):
        """Test that ConstraintChecker is a singleton."""
        c1 = ConstraintChecker()
        c2 = ConstraintChecker()
        assert c1 is c2

    def test_get_instance(self):
        """Test get_instance returns singleton."""
        c1 = ConstraintChecker.get_instance()
        c2 = ConstraintChecker.get_instance()
        assert c1 is c2

    def test_enabled_by_default(self):
        """Test constraint checking is enabled by default."""
        checker = ConstraintChecker()
        assert checker.is_enabled() is True

    def test_set_enabled(self):
        """Test disabling constraint checking."""
        checker = ConstraintChecker()
        checker.set_enabled(False)
        assert checker.is_enabled() is False

    def test_disabled_allows_all(self):
        """Test disabled checker allows everything."""
        checker = ConstraintChecker()
        checker.set_enabled(False)

        result = checker.check("dangerous.tool", {}, "any_agent")
        assert result.allowed is True


class TestToolPermissionConstraints:
    """Tests for tool permission constraints."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset singletons before each test."""
        ConstraintChecker.reset()
        SharedExecutionContext.reset()
        yield
        ConstraintChecker.reset()
        SharedExecutionContext.reset()

    def test_code_agent_allowed_tools(self):
        """Test code agent can use its allowed tools."""
        checker = ConstraintChecker()
        result = checker.check("fs.read", {"path": "/test.py"}, "code")
        assert result.allowed is True

    def test_review_agent_cannot_write(self):
        """Test review agent cannot write files."""
        checker = ConstraintChecker()
        result = checker.check("fs.write", {"path": "/test.py"}, "review")
        assert result.allowed is False
        assert any(
            v.violation == ConstraintViolation.TOOL_NOT_ALLOWED
            for v in result.violations
        )

    def test_review_agent_cannot_execute_shell(self):
        """Test review agent cannot execute shell commands."""
        checker = ConstraintChecker()
        result = checker.check("shell.exec", {"command": "ls"}, "review")
        assert result.allowed is False

    def test_test_agent_can_execute_shell(self):
        """Test test agent can execute shell (for running tests)."""
        checker = ConstraintChecker()
        result = checker.check("shell.exec", {"command": "pytest"}, "test")
        # Shell is allowed for test agent
        assert any(
            v.violation == ConstraintViolation.TOOL_NOT_ALLOWED
            for v in result.violations
        ) is False

    def test_custom_agent_constraints(self):
        """Test setting custom agent constraints."""
        checker = ConstraintChecker()
        constraints = AgentConstraints(
            agent_name="custom",
            allowed_tools={"fs.read"},
        )
        checker.set_agent_constraints(constraints)

        result = checker.check("fs.read", {"path": "/test.py"}, "custom")
        assert result.allowed is True

        result = checker.check("fs.write", {"path": "/test.py"}, "custom")
        assert result.allowed is False


class TestPathConstraints:
    """Tests for path-based constraints."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset singletons before each test."""
        ConstraintChecker.reset()
        SharedExecutionContext.reset()
        yield
        ConstraintChecker.reset()
        SharedExecutionContext.reset()

    def test_blocked_system_paths(self):
        """Test system paths are blocked."""
        checker = ConstraintChecker()
        result = checker.check("fs.write", {"path": "/etc/passwd"}, "code")
        assert result.allowed is False
        assert any(
            v.violation == ConstraintViolation.PATH_NOT_ALLOWED
            for v in result.violations
        )

    def test_blocked_sensitive_patterns(self):
        """Test sensitive file patterns are blocked."""
        checker = ConstraintChecker()

        # .env files
        result = checker.check("fs.write", {"path": "/project/.env"}, "code")
        assert result.allowed is False

        # Key files
        result = checker.check("fs.write", {"path": "/project/server.key"}, "code")
        assert result.allowed is False

    def test_add_blocked_path(self):
        """Test adding custom blocked path."""
        checker = ConstraintChecker()
        checker.add_blocked_path("/custom/blocked")

        result = checker.check("fs.write", {"path": "/custom/blocked/file.py"}, "code")
        assert result.allowed is False

    def test_add_blocked_pattern(self):
        """Test adding custom blocked pattern."""
        checker = ConstraintChecker()
        checker.add_blocked_pattern(r".*\.bak$")

        result = checker.check("fs.write", {"path": "/project/file.bak"}, "code")
        assert result.allowed is False


class TestReadBeforeWriteConstraint:
    """Tests for read-before-write constraint."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset singletons before each test."""
        ConstraintChecker.reset()
        SharedExecutionContext.reset()
        yield
        ConstraintChecker.reset()
        SharedExecutionContext.reset()

    def test_write_without_read_blocked(self):
        """Test writing without reading is blocked for existing files."""
        checker = ConstraintChecker()

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("existing content")
            temp_path = f.name

        try:
            result = checker.check("fs.write", {"path": temp_path}, "code")
            assert result.allowed is False
            assert any(
                v.violation == ConstraintViolation.READ_BEFORE_WRITE
                for v in result.violations
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_write_after_read_allowed(self):
        """Test writing after reading is allowed."""
        checker = ConstraintChecker()
        context = checker.get_context()

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("existing content")
            temp_path = f.name

        try:
            # Record the read
            context.record_read(temp_path, "existing content")

            result = checker.check("fs.write", {"path": temp_path}, "code")
            # Should not have read-before-write violation
            assert not any(
                v.violation == ConstraintViolation.READ_BEFORE_WRITE
                for v in result.violations
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_write_new_file_allowed(self):
        """Test writing new file is allowed (no read required)."""
        checker = ConstraintChecker()

        # Non-existent file path
        result = checker.check("fs.write", {"path": "/nonexistent/new_file.py"}, "code")

        # Should not have read-before-write violation
        assert not any(
            v.violation == ConstraintViolation.READ_BEFORE_WRITE
            for v in result.violations
        )


class TestShellCommandConstraints:
    """Tests for shell command safety constraints."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset singletons before each test."""
        ConstraintChecker.reset()
        SharedExecutionContext.reset()
        yield
        ConstraintChecker.reset()
        SharedExecutionContext.reset()

    def test_agent_without_shell_blocked(self):
        """Test agent without shell permission is blocked."""
        checker = ConstraintChecker()

        # Code agent cannot run shell by default
        result = checker.check("shell.exec", {"command": "ls"}, "code")
        assert result.allowed is False

    def test_dangerous_command_blocked(self):
        """Test dangerous shell commands are blocked."""
        checker = ConstraintChecker()

        # rm -rf /
        result = checker.check("shell.exec", {"command": "rm -rf /"}, "test")
        assert result.allowed is False

        # Fork bomb
        result = checker.check("shell.exec", {"command": ":(){:|:&};:"}, "test")
        assert result.allowed is False

    def test_safe_command_allowed(self):
        """Test safe commands are allowed for agents with shell permission."""
        checker = ConstraintChecker()

        # Test agent can run pytest
        result = checker.check("shell.exec", {"command": "pytest tests/"}, "test")
        # Should not have dangerous command violation
        assert not any(
            v.violation == ConstraintViolation.PATTERN_BLOCKED
            for v in result.violations
        )


class TestGetConstraintChecker:
    """Tests for get_constraint_checker helper."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset singletons before each test."""
        ConstraintChecker.reset()
        yield
        ConstraintChecker.reset()

    def test_returns_singleton(self):
        """Test get_constraint_checker returns singleton."""
        c1 = get_constraint_checker()
        c2 = get_constraint_checker()
        assert c1 is c2
