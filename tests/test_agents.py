"""
Tests for the multi-agent orchestration system.

© Roura.io
"""
import pytest
from unittest.mock import Mock, MagicMock

from roura_agent.agents import (
    BaseAgent,
    AgentCapability,
    AgentContext,
    AgentResult,
    AgentRegistry,
    get_registry,
    Orchestrator,
    CodeAgent,
    TestAgent,
    DebugAgent,
    ResearchAgent,
    GitAgent,
    ReviewAgent,
    initialize_agents,
)


class TestAgentCapability:
    """Tests for AgentCapability enum."""

    def test_capabilities_exist(self):
        """Test that key capabilities are defined."""
        assert AgentCapability.CODE_WRITE.value == "code_write"
        assert AgentCapability.CODE_READ.value == "code_read"
        assert AgentCapability.DEBUG.value == "debug"
        assert AgentCapability.RESEARCH.value == "research"
        assert AgentCapability.GIT.value == "git"

    def test_all_capabilities_have_values(self):
        """Test all capabilities have string values."""
        for cap in AgentCapability:
            assert isinstance(cap.value, str)
            assert len(cap.value) > 0


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_success_result(self):
        """Test creating a successful result."""
        result = AgentResult(success=True, output="Done")
        assert result.success is True
        assert result.output == "Done"
        assert result.error is None

    def test_error_result(self):
        """Test creating an error result."""
        result = AgentResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = AgentResult(
            success=True,
            output="test output",
            artifacts={"file": "test.py"},
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "test output"
        assert d["artifacts"]["file"] == "test.py"


class TestAgentContext:
    """Tests for AgentContext dataclass."""

    def test_create_context(self):
        """Test creating an agent context."""
        from roura_agent.agents.base import AgentContext

        ctx = AgentContext(
            task="Fix the bug",
            project_root="/path/to/project",
            files_in_context=["main.py", "utils.py"],
        )
        assert ctx.task == "Fix the bug"
        assert ctx.project_root == "/path/to/project"
        assert len(ctx.files_in_context) == 2


class TestAgentRegistry:
    """Tests for AgentRegistry."""

    def test_register_and_get(self):
        """Test registering and retrieving an agent."""
        registry = AgentRegistry()
        agent = CodeAgent()

        registry.register(agent)
        retrieved = registry.get("code")

        assert retrieved is agent
        assert retrieved.name == "code"

    def test_unregister(self):
        """Test unregistering an agent."""
        registry = AgentRegistry()
        agent = CodeAgent()

        registry.register(agent)
        assert registry.get("code") is not None

        result = registry.unregister("code")
        assert result is True
        assert registry.get("code") is None

    def test_list_agents(self):
        """Test listing all agents."""
        registry = AgentRegistry()
        registry.register(CodeAgent())
        registry.register(TestAgent())

        agents = registry.list_agents()
        assert len(agents) == 2
        names = {a.name for a in agents}
        assert "code" in names
        assert "test" in names

    def test_find_capable(self):
        """Test finding capable agents for a task."""
        registry = AgentRegistry()
        registry.register(CodeAgent())
        registry.register(TestAgent())
        registry.register(DebugAgent())

        # Task that matches code agent
        capable = registry.find_capable("write a function to add numbers")
        assert len(capable) > 0
        # Code agent should have highest confidence
        assert capable[0][0].name == "code"

    def test_best_agent(self):
        """Test finding the best agent for a task."""
        registry = AgentRegistry()
        registry.register(CodeAgent())
        registry.register(DebugAgent())

        best = registry.best_agent("fix the bug in main.py")
        assert best is not None
        assert best.name == "debug"

    def test_clear(self):
        """Test clearing the registry."""
        registry = AgentRegistry()
        registry.register(CodeAgent())
        registry.register(TestAgent())

        assert len(registry) == 2
        registry.clear()
        assert len(registry) == 0


class TestCodeAgent:
    """Tests for CodeAgent."""

    def test_name_and_capabilities(self):
        """Test agent name and capabilities."""
        agent = CodeAgent()
        assert agent.name == "code"
        assert AgentCapability.CODE_WRITE in agent.capabilities
        assert AgentCapability.CODE_READ in agent.capabilities

    def test_can_handle_code_tasks(self):
        """Test that agent can handle code-related tasks."""
        agent = CodeAgent()

        can, conf = agent.can_handle("write code for sorting a list")
        assert can is True
        assert conf >= 0.6  # "write code" matches pattern

        can, conf = agent.can_handle("implement a new class for users")
        assert can is True

        can, conf = agent.can_handle("refactor the authentication module")
        assert can is True

    def test_cannot_handle_unrelated_tasks(self):
        """Test that agent does not handle unrelated tasks."""
        agent = CodeAgent()

        can, conf = agent.can_handle("run all tests")
        assert can is False or conf < 0.5

    def test_system_prompt(self):
        """Test that system prompt is defined."""
        agent = CodeAgent()
        prompt = agent.system_prompt
        assert "Code Agent" in prompt
        assert "clean" in prompt.lower() or "code" in prompt.lower()


class TestTestAgent:
    """Tests for TestAgent."""

    def test_can_handle_test_tasks(self):
        """Test that agent handles test-related tasks."""
        agent = TestAgent()

        can, conf = agent.can_handle("write unit tests for the parser")
        assert can is True
        assert conf > 0.5

        can, conf = agent.can_handle("add integration tests")
        assert can is True

        can, conf = agent.can_handle("check test coverage")
        assert can is True


class TestDebugAgent:
    """Tests for DebugAgent."""

    def test_can_handle_debug_tasks(self):
        """Test that agent handles debug-related tasks."""
        agent = DebugAgent()

        can, conf = agent.can_handle("fix the bug in the login function")
        assert can is True
        assert conf > 0.5

        can, conf = agent.can_handle("debug the crashing issue")
        assert can is True

        can, conf = agent.can_handle("why is the app not working?")
        assert can is True


class TestResearchAgent:
    """Tests for ResearchAgent."""

    def test_can_handle_research_tasks(self):
        """Test that agent handles research-related tasks."""
        agent = ResearchAgent()

        can, conf = agent.can_handle("what is the best way to implement caching?")
        assert can is True

        can, conf = agent.can_handle("search for documentation on async/await")
        assert can is True

        can, conf = agent.can_handle("explain how promises work")
        assert can is True


class TestGitAgent:
    """Tests for GitAgent."""

    def test_can_handle_git_tasks(self):
        """Test that agent handles git-related tasks."""
        agent = GitAgent()

        can, conf = agent.can_handle("commit the changes")
        assert can is True
        assert conf > 0.5

        can, conf = agent.can_handle("create a new branch for the feature")
        assert can is True

        can, conf = agent.can_handle("git push to origin")
        assert can is True


class TestReviewAgent:
    """Tests for ReviewAgent."""

    def test_can_handle_review_tasks(self):
        """Test that agent handles review-related tasks."""
        agent = ReviewAgent()

        can, conf = agent.can_handle("review the code in utils.py")
        assert can is True
        assert conf > 0.5

        can, conf = agent.can_handle("do a code review on the PR")
        assert can is True


class TestOrchestrator:
    """Tests for Orchestrator."""

    def test_name_and_capabilities(self):
        """Test orchestrator name and capabilities."""
        orchestrator = Orchestrator()
        assert orchestrator.name == "orchestrator"
        assert AgentCapability.PLAN in orchestrator.capabilities
        assert AgentCapability.DELEGATE in orchestrator.capabilities

    def test_can_handle_any_task(self):
        """Test that orchestrator can handle any task."""
        orchestrator = Orchestrator()

        can, conf = orchestrator.can_handle("any random task")
        assert can is True
        assert conf == 0.5  # Moderate confidence

    def test_analyze_task_code(self):
        """Test task analysis for code tasks."""
        orchestrator = Orchestrator()

        analysis = orchestrator._analyze_task("implement a new feature")
        assert analysis["primary_type"] == "code"

    def test_analyze_task_debug(self):
        """Test task analysis for debug tasks."""
        orchestrator = Orchestrator()

        analysis = orchestrator._analyze_task("fix the bug in main.py")
        assert analysis["primary_type"] == "debug"

    def test_analyze_task_test(self):
        """Test task analysis for test tasks."""
        orchestrator = Orchestrator()

        analysis = orchestrator._analyze_task("write unit tests")
        assert analysis["primary_type"] == "test"

    def test_analyze_task_git(self):
        """Test task analysis for git tasks."""
        orchestrator = Orchestrator()

        analysis = orchestrator._analyze_task("commit the changes")
        assert analysis["primary_type"] == "git"


class TestInitializeAgents:
    """Tests for the initialize_agents function."""

    def test_initialize_creates_orchestrator(self):
        """Test that initialization creates orchestrator."""
        # Clear registry first
        registry = get_registry()
        registry.clear()

        orchestrator = initialize_agents()

        assert orchestrator is not None
        assert isinstance(orchestrator, Orchestrator)

    def test_initialize_registers_agents(self):
        """Test that initialization registers all agents."""
        registry = get_registry()
        registry.clear()

        initialize_agents()
        agents = registry.list_agents()

        names = {a.name for a in agents}
        assert "code" in names
        assert "test" in names
        assert "debug" in names
        assert "research" in names
        assert "git" in names
        assert "review" in names
