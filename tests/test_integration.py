"""
Integration tests for the Roura Agent system.

These tests exercise the full agent orchestration pipeline,
including task routing, multi-agent workflows, and tool execution.

© Roura.io
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from roura_agent.agents import (
    # Base
    BaseAgent,
    AgentCapability,
    AgentContext,
    AgentResult,
    # Registry
    AgentRegistry,
    get_registry,
    # Orchestrator
    Orchestrator,
    # Specialized Agents
    CodeAgent,
    TestAgent,
    DebugAgent,
    ResearchAgent,
    GitAgent,
    ReviewAgent,
    # IDE Integrations
    CursorAgent,
    # Shared Context
    SharedExecutionContext,
    get_shared_context,
    # Approval
    ApprovalManager,
    ApprovalMode,
    get_approval_manager,
    # Constraints
    ConstraintChecker,
    get_constraint_checker,
    # Parallel
    ParallelExecutor,
    DependencyGraph,
    ParallelAgentRunner,
    run_agents_parallel,
    TaskStatus,
    # Messaging
    MessageBus,
    get_message_bus,
    send_to_agent,
    MessagePriority,
    # Cursor Bridge
    CursorBridge,
    create_cursor_bridge,
    CursorTaskStatus,
    # Initialization
    initialize_agents,
)
from roura_agent.tools.base import RiskLevel


class TestAgentRegistryIntegration:
    """Integration tests for the agent registry."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before each test."""
        registry = get_registry()
        registry._agents.clear()
        yield
        registry._agents.clear()

    def test_register_and_retrieve_agents(self):
        """Test registering and retrieving multiple agents."""
        registry = get_registry()
        console = Mock()

        # Register multiple agents
        code_agent = CodeAgent(console=console)
        test_agent = TestAgent(console=console)
        debug_agent = DebugAgent(console=console)

        registry.register(code_agent)
        registry.register(test_agent)
        registry.register(debug_agent)

        # Verify retrieval
        assert registry.get("code") is code_agent
        assert registry.get("test") is test_agent
        assert registry.get("debug") is debug_agent

    def test_list_agents(self):
        """Test listing all registered agents."""
        registry = get_registry()
        console = Mock()

        registry.register(CodeAgent(console=console))
        registry.register(TestAgent(console=console))
        registry.register(GitAgent(console=console))

        # Should have all three agents
        agents = registry.list_agents()
        assert len(agents) == 3
        agent_names = [a.name for a in agents]
        assert "code" in agent_names
        assert "test" in agent_names
        assert "git" in agent_names


class TestOrchestratorIntegration:
    """Integration tests for the orchestrator."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        # Reset singletons
        AgentRegistry._instance = None
        SharedExecutionContext.reset()
        ApprovalManager._instance = None
        ConstraintChecker._instance = None

        self.console = Mock()
        self.registry = get_registry()
        yield

        # Cleanup
        AgentRegistry._instance = None
        SharedExecutionContext.reset()

    def test_orchestrator_routes_to_code_agent(self):
        """Test that orchestrator routes code tasks to code agent."""
        # Register a mock code agent
        mock_code_agent = Mock(spec=CodeAgent)
        mock_code_agent.name = "code"
        mock_code_agent.capabilities = {AgentCapability.CODE_WRITE}
        # can_handle returns (bool, confidence) tuple
        mock_code_agent.can_handle.return_value = (True, 0.9)
        mock_code_agent.execute.return_value = AgentResult(
            success=True,
            output="def hello(): pass",
        )

        self.registry.register(mock_code_agent)

        orchestrator = Orchestrator(console=self.console)
        context = AgentContext(task="Write a Python function to say hello")

        result = orchestrator.execute(context)

        # Verify the code agent was called
        mock_code_agent.execute.assert_called()

    def test_orchestrator_routes_to_test_agent(self):
        """Test that orchestrator routes test tasks to test agent."""
        mock_test_agent = Mock(spec=TestAgent)
        mock_test_agent.name = "test"
        mock_test_agent.capabilities = {AgentCapability.TEST_RUN}
        # can_handle returns (bool, confidence) tuple - high confidence
        mock_test_agent.can_handle.return_value = (True, 0.95)
        mock_test_agent.execute.return_value = AgentResult(
            success=True,
            output="All tests passed",
        )

        # Also need to add a lower-confidence code agent
        mock_code_agent = Mock()
        mock_code_agent.name = "code"
        mock_code_agent.capabilities = {AgentCapability.CODE_WRITE}
        mock_code_agent.can_handle.return_value = (True, 0.3)  # Lower confidence
        mock_code_agent.execute.return_value = AgentResult(success=True, output="")

        self.registry.register(mock_code_agent)
        self.registry.register(mock_test_agent)

        orchestrator = Orchestrator(console=self.console)
        context = AgentContext(task="Run the unit tests")

        result = orchestrator.execute(context)

        # The test agent with higher confidence should be selected
        mock_test_agent.execute.assert_called()

    def test_orchestrator_handles_no_suitable_agent(self):
        """Test orchestrator behavior when no agent can handle task."""
        # Register an agent that can't handle the task
        mock_agent = Mock()
        mock_agent.name = "mock"
        mock_agent.capabilities = set()
        mock_agent.can_handle.return_value = (False, 0.0)

        self.registry.register(mock_agent)

        orchestrator = Orchestrator(console=self.console)
        context = AgentContext(task="Do something no agent can do")

        result = orchestrator.execute(context)

        # Should return a result indicating no agent found
        assert result is not None


class TestSharedContextIntegration:
    """Integration tests for shared execution context."""

    @pytest.fixture(autouse=True)
    def reset_context(self):
        """Reset shared context before each test."""
        SharedExecutionContext.reset()
        yield
        SharedExecutionContext.reset()

    def test_context_tracks_reads_across_agents(self):
        """Test that context tracks file reads across multiple agents."""
        context = get_shared_context()

        # Simulate reads from different agents
        context.record_read("/path/file1.py", "content1", "agent_1")
        context.record_read("/path/file2.py", "content2", "agent_2")
        context.record_read("/path/file1.py", "content1", "agent_2")  # Same file, different agent

        assert context.has_read("/path/file1.py")
        assert context.has_read("/path/file2.py")
        assert not context.has_read("/path/file3.py")

    def test_context_tracks_modifications(self):
        """Test that context tracks file modifications."""
        context = get_shared_context()

        # First record a read (required for modification)
        context.record_read("/path/file.py", "old", "code_agent")

        # Record a modification
        context.record_modification(
            path="/path/file.py",
            old_content="old",
            new_content="new",
            action="edit",
            agent="code_agent",
        )

        modified_files = context.get_modified_files()
        assert "/path/file.py" in str(modified_files[0])  # Path is resolved

    def test_context_provides_file_content(self):
        """Test that context stores and retrieves file content."""
        context = get_shared_context()

        # Record read
        context.record_read("/path/file.py", "file content", "agent")

        # Retrieve content
        content = context.get_file_content("/path/file.py")
        assert content == "file content"


class TestApprovalIntegration:
    """Integration tests for the approval system."""

    @pytest.fixture(autouse=True)
    def reset_approval(self):
        """Reset approval manager."""
        ApprovalManager._instance = None
        yield
        ApprovalManager._instance = None

    def test_strict_mode_requires_approval(self):
        """Test that strict mode requires approval for moderate/dangerous tools."""
        manager = get_approval_manager()
        manager.set_mode(ApprovalMode.STRICT)

        # Moderate tools should require approval in strict mode
        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is True
        # Dangerous tools should require approval
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is True

    def test_permissive_mode_allows_safe_tools(self):
        """Test that permissive mode allows safe tools."""
        manager = get_approval_manager()
        manager.set_mode(ApprovalMode.PERMISSIVE)

        # Safe tools should not require approval
        assert manager.needs_approval("fs.read", RiskLevel.SAFE) is False
        # But dangerous tools still should
        assert manager.needs_approval("shell.exec", RiskLevel.DANGEROUS) is True

    def test_auto_mode_with_patterns(self):
        """Test auto-approval with patterns."""
        manager = get_approval_manager()
        manager.set_mode(ApprovalMode.AUTO)
        manager.auto_approve_pattern("fs.*")

        # fs tools should be auto-approved
        # In AUTO mode, everything is auto-approved anyway
        assert manager.needs_approval("fs.read", RiskLevel.SAFE) is False
        assert manager.needs_approval("fs.write", RiskLevel.MODERATE) is False


class TestConstraintIntegration:
    """Integration tests for constraint checking."""

    @pytest.fixture(autouse=True)
    def reset_constraints(self):
        """Reset constraint checker."""
        ConstraintChecker._instance = None
        SharedExecutionContext.reset()
        yield
        ConstraintChecker._instance = None
        SharedExecutionContext.reset()

    def test_constraint_check_passes_for_valid_action(self):
        """Test that valid actions pass constraint checks."""
        context = get_shared_context()
        checker = get_constraint_checker()
        checker.set_context(context)

        # First read a file
        context.record_read("/project/test.py", "content", "code")

        # Check that writing is allowed after reading
        result = checker.check(
            tool_name="fs.write",
            args={"path": "/project/test.py"},
            agent="code",
        )
        # Should be allowed (file was read)
        assert result.allowed is True

    def test_constraint_blocks_sensitive_files(self):
        """Test that sensitive file patterns are blocked."""
        checker = get_constraint_checker()

        # Attempt to write to .env file
        result = checker.check(
            tool_name="fs.write",
            args={"path": "/project/.env"},
            agent="code",
        )
        assert result.allowed is False


class TestParallelExecutionIntegration:
    """Integration tests for parallel agent execution."""

    def test_parallel_independent_tasks(self):
        """Test executing independent tasks in parallel."""
        # Create mock agents
        def create_agent(name):
            agent = Mock()
            agent.name = name
            agent.execute.return_value = AgentResult(
                success=True,
                output=f"Result from {name}",
            )
            return agent

        agents = {
            "code": create_agent("code"),
            "test": create_agent("test"),
            "review": create_agent("review"),
        }

        # Build dependency graph with independent tasks
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2")
        graph.add_task("t3", "review", "Task 3")

        # All should be in one wave (parallel)
        waves = graph.get_execution_waves()
        assert len(waves) == 1
        assert len(waves[0]) == 3

        # Execute
        executor = ParallelExecutor(agents=agents, console=Mock())
        plan = graph.create_plan()
        results = executor.execute_plan(plan)

        assert len(results) == 3
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_parallel_dependent_tasks(self):
        """Test executing tasks with dependencies."""
        def create_agent(name):
            agent = Mock()
            agent.name = name
            agent.execute.return_value = AgentResult(
                success=True,
                output=f"Result from {name}",
            )
            return agent

        agents = {
            "code": create_agent("code"),
            "test": create_agent("test"),
            "review": create_agent("review"),
        }

        # Build graph: code -> test -> review
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Write code")
        graph.add_task("t2", "test", "Test code", depends_on=["t1"])
        graph.add_task("t3", "review", "Review code", depends_on=["t2"])

        # Should be 3 waves (sequential)
        waves = graph.get_execution_waves()
        assert len(waves) == 3

        # Execute
        executor = ParallelExecutor(agents=agents, console=Mock())
        plan = graph.create_plan()
        results = executor.execute_plan(plan)

        assert len(results) == 3
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_parallel_diamond_pattern(self):
        """Test diamond dependency pattern."""
        def create_agent(name):
            agent = Mock()
            agent.name = name
            agent.execute.return_value = AgentResult(success=True, output="done")
            return agent

        agents = {
            "code": create_agent("code"),
            "test": create_agent("test"),
            "lint": create_agent("lint"),
            "review": create_agent("review"),
        }

        # Diamond: code -> (test, lint) -> review
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Write code")
        graph.add_task("t2", "test", "Test", depends_on=["t1"])
        graph.add_task("t3", "lint", "Lint", depends_on=["t1"])
        graph.add_task("t4", "review", "Review", depends_on=["t2", "t3"])

        waves = graph.get_execution_waves()
        assert len(waves) == 3
        assert waves[0] == ["t1"]
        assert set(waves[1]) == {"t2", "t3"}
        assert waves[2] == ["t4"]

    def test_parallel_runner_convenience(self):
        """Test ParallelAgentRunner convenience class."""
        mock_agent = Mock()
        mock_agent.name = "code"
        mock_agent.execute.return_value = AgentResult(success=True, output="done")

        runner = ParallelAgentRunner()
        runner.register_agent("code", mock_agent)

        t1 = runner.add_task("code", "Task 1")
        t2 = runner.add_task("code", "Task 2")

        results = runner.run()
        assert len(results) == 2


class TestCursorBridgeIntegration:
    """Integration tests for Cursor IDE bridge."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_full_task_lifecycle(self, temp_project):
        """Test complete task lifecycle: create -> complete."""
        bridge = CursorBridge(temp_project, console=Mock())

        # Create task
        task = bridge.create_task(
            task_id="feature_1",
            task_description="Implement user authentication",
            context={"priority": "high"},
            files=["auth.py", "models.py"],
        )

        assert task.status == CursorTaskStatus.PENDING
        assert task.id == "feature_1"

        # Verify files created
        roura_dir = Path(temp_project) / ".roura"
        assert (roura_dir / "tasks" / "feature_1.md").exists()
        assert (roura_dir / "tasks" / "feature_1.json").exists()

        # Mark complete
        task = bridge.mark_complete("feature_1", "Successfully implemented")
        assert task.status == CursorTaskStatus.COMPLETED
        assert task.result == "Successfully implemented"
        assert task.completed_at is not None

    def test_multiple_tasks(self, temp_project):
        """Test managing multiple tasks."""
        bridge = CursorBridge(temp_project, console=Mock())

        # Create multiple tasks
        bridge.create_task("task_1", "Task 1")
        bridge.create_task("task_2", "Task 2")
        bridge.create_task("task_3", "Task 3")

        # Complete one, fail one
        bridge.mark_complete("task_1")
        bridge.cancel_task("task_2")

        # Check status summary
        summary = bridge.get_status_summary()
        assert summary["total"] == 3
        assert summary["pending"] == 1
        assert summary["completed"] == 1
        assert summary["failed"] == 1

    def test_task_with_file_contents(self, temp_project):
        """Test creating task with file contents."""
        bridge = CursorBridge(temp_project, console=Mock())

        task = bridge.create_task(
            task_id="code_task",
            task_description="Fix the bug in this code",
            file_contents={
                "buggy.py": "def bug():\n    return 1 / 0",
            },
        )

        # Verify file contents in markdown
        md_file = Path(temp_project) / ".roura" / "tasks" / "code_task.md"
        content = md_file.read_text()
        assert "return 1 / 0" in content


class TestMessageBusIntegration:
    """Integration tests for inter-agent messaging."""

    @pytest.fixture(autouse=True)
    def reset_bus(self):
        """Reset message bus."""
        MessageBus._instance = None
        yield
        MessageBus._instance = None

    def test_send_and_receive_message(self):
        """Test sending and receiving messages between agents."""
        bus = get_message_bus()
        received_messages = []

        def handler(message):
            received_messages.append(message)
            return AgentResult(success=True, output="Handled")

        bus.register_handler("target_agent", handler)

        # Send a message using correct signature
        bus.send(
            from_agent="source_agent",
            to_agent="target_agent",
            task="Do something",
        )

        # Process the message
        bus.process_next()

        assert len(received_messages) == 1
        assert received_messages[0].task == "Do something"

    def test_message_priority(self):
        """Test message priority ordering."""
        bus = get_message_bus()
        received_order = []

        def handler(message):
            received_order.append(message.task)
            return AgentResult(success=True, output="ok")

        bus.register_handler("agent", handler)

        # Send messages with different priorities (from_agent, task, to_agent)
        bus.send(from_agent="source", task="Low priority", to_agent="agent", priority=MessagePriority.LOW)
        bus.send(from_agent="source", task="High priority", to_agent="agent", priority=MessagePriority.HIGH)
        bus.send(from_agent="source", task="Normal priority", to_agent="agent", priority=MessagePriority.NORMAL)

        # Process all messages
        bus.process_next()
        bus.process_next()
        bus.process_next()

        # High priority should be first
        assert len(received_order) == 3
        assert received_order[0] == "High priority"


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset all singletons."""
        AgentRegistry._instance = None
        SharedExecutionContext.reset()
        ApprovalManager._instance = None
        ConstraintChecker._instance = None
        MessageBus._instance = None
        yield
        AgentRegistry._instance = None
        SharedExecutionContext.reset()
        ApprovalManager._instance = None
        ConstraintChecker._instance = None
        MessageBus._instance = None

    def test_code_review_workflow(self):
        """Test a complete code review workflow."""
        console = Mock()

        # Create agents
        code_agent = Mock()
        code_agent.name = "code"
        code_agent.capabilities = {AgentCapability.CODE_WRITE}
        code_agent.execute.return_value = AgentResult(
            success=True,
            output="def hello(): print('Hello')",
        )

        review_agent = Mock()
        review_agent.name = "review"
        review_agent.capabilities = {AgentCapability.CODE_REVIEW}
        review_agent.execute.return_value = AgentResult(
            success=True,
            output="Code looks good, approved",
        )

        # Set up parallel execution
        graph = DependencyGraph()
        graph.add_task("write", "code", "Write the hello function")
        graph.add_task("review", "review", "Review the code", depends_on=["write"])

        executor = ParallelExecutor(
            agents={"code": code_agent, "review": review_agent},
            console=console,
        )

        results = executor.execute_plan(graph.create_plan())

        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_full_development_cycle(self):
        """Test a full development cycle: code -> test -> review -> deploy."""
        console = Mock()

        def create_agent(name, output):
            agent = Mock()
            agent.name = name
            agent.execute.return_value = AgentResult(success=True, output=output)
            return agent

        agents = {
            "code": create_agent("code", "Function implemented"),
            "test": create_agent("test", "All tests pass"),
            "review": create_agent("review", "Approved"),
            "git": create_agent("git", "Committed and pushed"),
        }

        # Build the workflow
        graph = DependencyGraph()
        graph.add_task("implement", "code", "Implement feature")
        graph.add_task("test", "test", "Run tests", depends_on=["implement"])
        graph.add_task("review", "review", "Code review", depends_on=["implement"])
        graph.add_task("deploy", "git", "Commit and push", depends_on=["test", "review"])

        # Execute
        executor = ParallelExecutor(agents=agents, console=console)
        results = executor.execute_plan(graph.create_plan())

        assert len(results) == 4
        assert all(r.status == TaskStatus.COMPLETED for r in results)

        # Verify order: implement first, test and review in parallel, deploy last
        result_order = {r.agent_name: r for r in results}
        assert result_order["code"].started_at <= result_order["test"].started_at
        assert result_order["code"].started_at <= result_order["review"].started_at

    def test_workflow_with_failure_handling(self):
        """Test workflow handles failures gracefully."""
        console = Mock()

        # Test agent that fails
        failing_test = Mock()
        failing_test.name = "test"
        failing_test.execute.return_value = AgentResult(
            success=False,
            error="Tests failed: 3 failures",
        )

        code_agent = Mock()
        code_agent.name = "code"
        code_agent.execute.return_value = AgentResult(success=True, output="ok")

        agents = {
            "code": code_agent,
            "test": failing_test,
        }

        graph = DependencyGraph()
        graph.add_task("code", "code", "Write code")
        graph.add_task("test", "test", "Run tests", depends_on=["code"])

        executor = ParallelExecutor(agents=agents, console=console)
        results = executor.execute_plan(graph.create_plan())

        # Code should succeed, test should fail
        code_result = next(r for r in results if r.agent_name == "code")
        test_result = next(r for r in results if r.agent_name == "test")

        assert code_result.status == TaskStatus.COMPLETED
        assert test_result.status == TaskStatus.FAILED


class TestConstraintEnforcement:
    """Tests for constraint enforcement across the system."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset singletons."""
        SharedExecutionContext.reset()
        ConstraintChecker._instance = None
        yield
        SharedExecutionContext.reset()
        ConstraintChecker._instance = None

    def test_blocked_file_patterns(self):
        """Test that sensitive files are blocked."""
        checker = get_constraint_checker()

        # These should be blocked
        blocked_files = [
            "/project/.env",
            "/project/config.key",
            "/home/user/.ssh/id_rsa",
        ]

        for path in blocked_files:
            result = checker.check(
                tool_name="fs.write",
                args={"path": path},
                agent="code",
            )
            assert result.allowed is False, f"Expected {path} to be blocked"

    def test_allowed_file_patterns(self):
        """Test that normal source files are allowed."""
        context = get_shared_context()
        checker = get_constraint_checker()
        checker.set_context(context)

        # First record a read
        context.record_read("/project/src/main.py", "content", "code")

        result = checker.check(
            tool_name="fs.write",
            args={"path": "/project/src/main.py"},
            agent="code",
        )
        assert result.allowed is True
