"""
Tests for the parallel execution system.

© Roura.io
"""
import pytest
import time
import threading
from unittest.mock import Mock, MagicMock

from roura_agent.agents.parallel import (
    ParallelExecutor,
    ParallelTask,
    TaskStatus,
    ExecutionPlan,
    DependencyGraph,
    ResourceManager,
    ParallelAgentRunner,
    run_agents_parallel,
)
from roura_agent.agents.base import AgentResult, AgentContext


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_statuses_exist(self):
        """Test all task statuses exist."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.BLOCKED.value == "blocked"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestParallelTask:
    """Tests for ParallelTask dataclass."""

    def test_create_task(self):
        """Test creating a parallel task."""
        task = ParallelTask(
            id="task_1",
            agent_name="code",
            task="Write a function",
        )
        assert task.id == "task_1"
        assert task.agent_name == "code"
        assert task.status == TaskStatus.PENDING
        assert task.dependencies == set()

    def test_task_with_dependencies(self):
        """Test creating a task with dependencies."""
        task = ParallelTask(
            id="task_2",
            agent_name="test",
            task="Write tests",
            dependencies={"task_1"},
        )
        assert "task_1" in task.dependencies

    def test_duration_calculation(self):
        """Test duration calculation."""
        from datetime import datetime, timedelta

        task = ParallelTask(
            id="task_1",
            agent_name="code",
            task="Test",
        )
        task.started_at = datetime.now() - timedelta(seconds=5)
        task.completed_at = datetime.now()

        assert task.duration is not None
        assert task.duration >= 4.5  # Allow for timing variations

    def test_duration_none_when_not_complete(self):
        """Test duration is None when task not complete."""
        task = ParallelTask(
            id="task_1",
            agent_name="code",
            task="Test",
        )
        assert task.duration is None


class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass."""

    def test_create_plan(self):
        """Test creating an execution plan."""
        tasks = [
            ParallelTask(id="t1", agent_name="code", task="Task 1"),
            ParallelTask(id="t2", agent_name="test", task="Task 2"),
        ]
        plan = ExecutionPlan(
            tasks=tasks,
            execution_order=[["t1", "t2"]],
        )
        assert len(plan.tasks) == 2
        assert plan.execution_order == [["t1", "t2"]]

    def test_get_task(self):
        """Test getting a task by ID."""
        tasks = [
            ParallelTask(id="t1", agent_name="code", task="Task 1"),
            ParallelTask(id="t2", agent_name="test", task="Task 2"),
        ]
        plan = ExecutionPlan(tasks=tasks, execution_order=[])

        assert plan.get_task("t1").agent_name == "code"
        assert plan.get_task("t2").agent_name == "test"
        assert plan.get_task("nonexistent") is None


class TestDependencyGraph:
    """Tests for DependencyGraph."""

    def test_add_task(self):
        """Test adding tasks to graph."""
        graph = DependencyGraph()
        task = graph.add_task(
            task_id="t1",
            agent_name="code",
            task="Task 1",
        )
        assert task.id == "t1"
        assert task.agent_name == "code"

    def test_add_task_with_dependencies(self):
        """Test adding task with dependencies."""
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2", depends_on=["t1"])

        # t2 depends on t1
        waves = graph.get_execution_waves()
        assert len(waves) == 2
        assert "t1" in waves[0]
        assert "t2" in waves[1]

    def test_no_cycle_detection(self):
        """Test cycle detection returns False for acyclic graph."""
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2", depends_on=["t1"])
        graph.add_task("t3", "review", "Task 3", depends_on=["t2"])

        assert graph.has_cycle() is False

    def test_cycle_detection(self):
        """Test cycle detection returns True for cyclic graph."""
        graph = DependencyGraph()
        # Create a cycle: t1 -> t2 -> t3 -> t1
        graph.add_task("t1", "code", "Task 1", depends_on=["t3"])
        graph.add_task("t2", "test", "Task 2", depends_on=["t1"])
        graph.add_task("t3", "review", "Task 3", depends_on=["t2"])

        # This creates a cycle
        assert graph.has_cycle() is True

    def test_execution_waves_independent_tasks(self):
        """Test waves for independent tasks."""
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2")
        graph.add_task("t3", "review", "Task 3")

        waves = graph.get_execution_waves()
        # All tasks can run in parallel
        assert len(waves) == 1
        assert len(waves[0]) == 3

    def test_execution_waves_sequential_tasks(self):
        """Test waves for sequential dependencies."""
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2", depends_on=["t1"])
        graph.add_task("t3", "review", "Task 3", depends_on=["t2"])

        waves = graph.get_execution_waves()
        # Tasks must run sequentially
        assert len(waves) == 3
        assert waves[0] == ["t1"]
        assert waves[1] == ["t2"]
        assert waves[2] == ["t3"]

    def test_execution_waves_diamond_pattern(self):
        """Test waves for diamond dependency pattern."""
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2", depends_on=["t1"])
        graph.add_task("t3", "review", "Task 3", depends_on=["t1"])
        graph.add_task("t4", "git", "Task 4", depends_on=["t2", "t3"])

        waves = graph.get_execution_waves()
        # t1 first, then t2 and t3 in parallel, then t4
        assert len(waves) == 3
        assert waves[0] == ["t1"]
        assert set(waves[1]) == {"t2", "t3"}
        assert waves[2] == ["t4"]

    def test_create_plan(self):
        """Test creating execution plan from graph."""
        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2", depends_on=["t1"])

        plan = graph.create_plan()
        assert len(plan.tasks) == 2
        assert len(plan.execution_order) == 2


class TestResourceManager:
    """Tests for ResourceManager."""

    def test_llm_semaphore(self):
        """Test LLM call semaphore."""
        manager = ResourceManager(max_concurrent_llm_calls=2)

        # Should be able to acquire 2 slots
        assert manager.acquire_llm_slot() is True
        assert manager.acquire_llm_slot() is True

        # Third should timeout
        assert manager.acquire_llm_slot(timeout=0.1) is False

        # Release one
        manager.release_llm_slot()

        # Now should succeed
        assert manager.acquire_llm_slot() is True

    def test_agent_semaphore(self):
        """Test agent execution semaphore."""
        manager = ResourceManager(max_concurrent_agents=1)

        assert manager.acquire_agent_slot() is True
        assert manager.acquire_agent_slot(timeout=0.1) is False

        manager.release_agent_slot()
        assert manager.acquire_agent_slot() is True

    def test_file_lock(self):
        """Test file locking."""
        manager = ResourceManager()
        lock1 = manager.acquire_file_lock("/test/file.py")
        assert lock1 is not None

        # Same file should return same lock (but it's already acquired)
        # So trying to acquire again from another thread would block
        # Here we just verify we can release
        manager.release_file_lock("/test/file.py")


class TestParallelExecutor:
    """Tests for ParallelExecutor."""

    @pytest.fixture
    def mock_agents(self):
        """Create mock agents."""
        def create_mock_agent(name):
            agent = Mock()
            agent.name = name
            agent.execute.return_value = AgentResult(
                success=True,
                output=f"Completed {name} task",
            )
            return agent

        return {
            "code": create_mock_agent("code"),
            "test": create_mock_agent("test"),
            "review": create_mock_agent("review"),
        }

    def test_execute_single_task(self, mock_agents):
        """Test executing a single task."""
        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        plan = graph.create_plan()

        results = executor.execute_plan(plan)
        assert len(results) == 1
        assert results[0].status == TaskStatus.COMPLETED
        mock_agents["code"].execute.assert_called_once()

    def test_execute_parallel_tasks(self, mock_agents):
        """Test executing independent tasks in parallel."""
        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        graph.add_task("t2", "test", "Task 2")
        plan = graph.create_plan()

        results = executor.execute_plan(plan)
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_execute_with_dependencies(self, mock_agents):
        """Test executing tasks with dependencies."""
        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        graph = DependencyGraph()
        graph.add_task("t1", "code", "Write code")
        graph.add_task("t2", "test", "Test code", depends_on=["t1"])
        plan = graph.create_plan()

        results = executor.execute_plan(plan)
        assert len(results) == 2

        # Verify order - code should be called before test
        call_order = []
        for result in results:
            if result.agent_name == "code":
                call_order.append("code")
            elif result.agent_name == "test":
                call_order.append("test")

        # code should appear before test
        assert call_order.index("code") < call_order.index("test")

    def test_execute_failed_task(self, mock_agents):
        """Test handling a failed task."""
        mock_agents["code"].execute.return_value = AgentResult(
            success=False,
            error="Something went wrong",
        )

        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        graph = DependencyGraph()
        graph.add_task("t1", "code", "Task 1")
        plan = graph.create_plan()

        results = executor.execute_plan(plan)
        assert len(results) == 1
        assert results[0].status == TaskStatus.FAILED

    def test_execute_unknown_agent(self, mock_agents):
        """Test handling unknown agent."""
        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        graph = DependencyGraph()
        graph.add_task("t1", "unknown", "Task 1")
        plan = graph.create_plan()

        results = executor.execute_plan(plan)
        assert len(results) == 1
        assert results[0].status == TaskStatus.FAILED
        assert "Unknown agent" in results[0].error

    def test_execute_tasks_convenience(self, mock_agents):
        """Test execute_tasks convenience method."""
        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        tasks = [
            {"agent": "code", "task": "Write code"},
            {"agent": "test", "task": "Test code"},
        ]

        results = executor.execute_tasks(tasks, show_progress=False)
        assert len(results) == 2

    def test_cancel_execution(self, mock_agents):
        """Test cancelling execution."""
        # Make one agent slow
        def slow_execute(context):
            time.sleep(1)
            return AgentResult(success=True, output="Done")

        mock_agents["code"].execute.side_effect = slow_execute

        executor = ParallelExecutor(
            agents=mock_agents,
            console=Mock(),
        )

        # Start execution in thread
        results = []
        def run():
            graph = DependencyGraph()
            graph.add_task("t1", "code", "Slow task")
            plan = graph.create_plan()
            nonlocal results
            results = executor.execute_plan(plan)

        thread = threading.Thread(target=run)
        thread.start()

        # Cancel immediately
        executor.cancel()
        thread.join(timeout=2)


class TestParallelAgentRunner:
    """Tests for ParallelAgentRunner."""

    def test_add_task(self):
        """Test adding tasks."""
        runner = ParallelAgentRunner()
        task_id = runner.add_task("code", "Write code")
        assert task_id == "task_0"

        task_id2 = runner.add_task("test", "Test code")
        assert task_id2 == "task_1"

    def test_add_task_with_custom_id(self):
        """Test adding task with custom ID."""
        runner = ParallelAgentRunner()
        task_id = runner.add_task("code", "Write code", task_id="custom_id")
        assert task_id == "custom_id"

    def test_add_task_with_dependencies(self):
        """Test adding task with dependencies."""
        runner = ParallelAgentRunner()
        t1 = runner.add_task("code", "Write code")
        t2 = runner.add_task("test", "Test code", depends_on=[t1])
        assert t2 == "task_1"

    def test_register_agent(self):
        """Test registering agents."""
        runner = ParallelAgentRunner()
        mock_agent = Mock()
        runner.register_agent("code", mock_agent)
        assert "code" in runner._agents

    def test_run_no_agents_error(self):
        """Test running with no agents raises error."""
        runner = ParallelAgentRunner()
        runner.add_task("code", "Write code")

        with pytest.raises(ValueError, match="No agents registered"):
            runner.run()

    def test_clear(self):
        """Test clearing tasks."""
        runner = ParallelAgentRunner()
        runner.add_task("code", "Task 1")
        runner.add_task("test", "Task 2")
        runner.clear()

        assert len(runner._tasks) == 0
        assert runner._task_counter == 0


class TestRunAgentsParallel:
    """Tests for run_agents_parallel convenience function."""

    def test_run_agents_parallel(self):
        """Test the convenience function."""
        mock_agent = Mock()
        mock_agent.execute.return_value = AgentResult(
            success=True,
            output="Done",
        )

        tasks = [
            {"agent": "code", "task": "Task 1"},
        ]

        results = run_agents_parallel(
            tasks=tasks,
            agents={"code": mock_agent},
            console=Mock(),
            show_progress=False,
        )

        assert len(results) == 1
        assert results[0].status == TaskStatus.COMPLETED
