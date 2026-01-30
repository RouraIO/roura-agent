"""
Roura Agent Parallel Executor - Concurrent agent execution with dependency management.

This module enables:
- Parallel execution of independent agent tasks
- Dependency graph for task ordering
- Resource management (rate limiting, file locking)
- Progress tracking for concurrent operations

© Roura.io
"""
from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict, List, Callable, Set, TYPE_CHECKING
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn, TimeElapsedColumn

if TYPE_CHECKING:
    from .base import BaseAgent, AgentContext, AgentResult


class TaskStatus(Enum):
    """Status of a parallel task."""
    PENDING = "pending"
    BLOCKED = "blocked"     # Waiting for dependencies
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ParallelTask:
    """A task for parallel execution."""
    id: str
    agent_name: str
    task: str
    context: Optional["AgentContext"] = None
    dependencies: Set[str] = field(default_factory=set)  # IDs of tasks this depends on
    status: TaskStatus = TaskStatus.PENDING
    result: Optional["AgentResult"] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class ExecutionPlan:
    """Plan for parallel execution with dependency ordering."""
    tasks: List[ParallelTask]
    execution_order: List[List[str]]  # Waves of task IDs that can run in parallel

    def get_task(self, task_id: str) -> Optional[ParallelTask]:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


class DependencyGraph:
    """
    Manages task dependencies for proper execution ordering.

    Supports:
    - Adding tasks with dependencies
    - Topological sorting for execution order
    - Cycle detection
    - Parallel wave calculation
    """

    def __init__(self):
        self._tasks: Dict[str, ParallelTask] = {}
        self._dependencies: Dict[str, Set[str]] = {}  # task_id -> set of dependency IDs
        self._dependents: Dict[str, Set[str]] = {}    # task_id -> set of dependent IDs

    def add_task(
        self,
        task_id: str,
        agent_name: str,
        task: str,
        depends_on: Optional[List[str]] = None,
        context: Optional["AgentContext"] = None,
    ) -> ParallelTask:
        """Add a task to the graph."""
        parallel_task = ParallelTask(
            id=task_id,
            agent_name=agent_name,
            task=task,
            context=context,
            dependencies=set(depends_on or []),
        )

        self._tasks[task_id] = parallel_task
        self._dependencies[task_id] = set(depends_on or [])

        # Only create dependents set if it doesn't exist (avoid overwriting)
        if task_id not in self._dependents:
            self._dependents[task_id] = set()

        # Update dependents for each dependency
        for dep_id in (depends_on or []):
            if dep_id not in self._dependents:
                self._dependents[dep_id] = set()
            self._dependents[dep_id].add(task_id)

        return parallel_task

    def has_cycle(self) -> bool:
        """Check if the graph has any cycles."""
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for dep in self._dependents.get(node, []):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for task_id in self._tasks:
            if task_id not in visited:
                if dfs(task_id):
                    return True
        return False

    def get_execution_waves(self) -> List[List[str]]:
        """
        Get execution waves - groups of tasks that can run in parallel.

        Returns a list of lists, where each inner list contains task IDs
        that can be executed concurrently.
        """
        if self.has_cycle():
            raise ValueError("Dependency graph has cycles")

        waves: List[List[str]] = []
        remaining = set(self._tasks.keys())
        completed = set()

        while remaining:
            # Find all tasks with no unmet dependencies
            ready = []
            for task_id in remaining:
                deps = self._dependencies.get(task_id, set())
                if deps.issubset(completed):
                    ready.append(task_id)

            if not ready:
                # Deadlock - remaining tasks have unmet dependencies
                raise ValueError(
                    f"Deadlock detected. Remaining tasks: {remaining}, "
                    f"completed: {completed}"
                )

            waves.append(ready)
            completed.update(ready)
            remaining -= set(ready)

        return waves

    def create_plan(self) -> ExecutionPlan:
        """Create an execution plan from the graph."""
        waves = self.get_execution_waves()
        return ExecutionPlan(
            tasks=list(self._tasks.values()),
            execution_order=waves,
        )


class ResourceManager:
    """
    Manages resources for parallel execution.

    Handles:
    - Rate limiting for LLM API calls
    - File locking to prevent concurrent writes
    - Memory/concurrency limits
    """

    def __init__(
        self,
        max_concurrent_llm_calls: int = 3,
        max_concurrent_agents: int = 5,
    ):
        self._llm_semaphore = threading.Semaphore(max_concurrent_llm_calls)
        self._agent_semaphore = threading.Semaphore(max_concurrent_agents)
        self._file_locks: Dict[str, threading.Lock] = {}
        self._file_locks_lock = threading.Lock()

    def acquire_llm_slot(self, timeout: Optional[float] = None) -> bool:
        """Acquire a slot for an LLM call."""
        return self._llm_semaphore.acquire(timeout=timeout)

    def release_llm_slot(self) -> None:
        """Release an LLM call slot."""
        self._llm_semaphore.release()

    def acquire_agent_slot(self, timeout: Optional[float] = None) -> bool:
        """Acquire a slot for agent execution."""
        return self._agent_semaphore.acquire(timeout=timeout)

    def release_agent_slot(self) -> None:
        """Release an agent slot."""
        self._agent_semaphore.release()

    def acquire_file_lock(self, path: str) -> threading.Lock:
        """Get or create a lock for a file path."""
        resolved = str(Path(path).resolve())
        with self._file_locks_lock:
            if resolved not in self._file_locks:
                self._file_locks[resolved] = threading.Lock()
            lock = self._file_locks[resolved]
        lock.acquire()
        return lock

    def release_file_lock(self, path: str) -> None:
        """Release a file lock."""
        resolved = str(Path(path).resolve())
        with self._file_locks_lock:
            if resolved in self._file_locks:
                try:
                    self._file_locks[resolved].release()
                except RuntimeError:
                    pass  # Lock not held


class ParallelExecutor:
    """
    Executes agent tasks in parallel with proper dependency handling.

    Features:
    - Parallel execution of independent tasks
    - Dependency-based scheduling
    - Progress tracking and UI updates
    - Resource management
    - Error handling and task cancellation
    """

    def __init__(
        self,
        agents: Dict[str, "BaseAgent"],
        console: Optional[Console] = None,
        max_workers: int = 5,
        max_llm_calls: int = 3,
    ):
        """
        Initialize the parallel executor.

        Args:
            agents: Dict mapping agent names to agent instances
            console: Console for output
            max_workers: Maximum concurrent workers
            max_llm_calls: Maximum concurrent LLM API calls
        """
        self._agents = agents
        self._console = console or Console()
        self._max_workers = max_workers
        self._resources = ResourceManager(
            max_concurrent_llm_calls=max_llm_calls,
            max_concurrent_agents=max_workers,
        )
        self._executor: Optional[ThreadPoolExecutor] = None
        self._cancelled = False
        self._lock = threading.Lock()

    def execute_plan(
        self,
        plan: ExecutionPlan,
        on_task_start: Optional[Callable[[ParallelTask], None]] = None,
        on_task_complete: Optional[Callable[[ParallelTask], None]] = None,
    ) -> List[ParallelTask]:
        """
        Execute a plan with proper dependency ordering.

        Args:
            plan: The execution plan
            on_task_start: Callback when a task starts
            on_task_complete: Callback when a task completes

        Returns:
            List of completed tasks
        """
        self._cancelled = False
        completed_tasks: List[ParallelTask] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            self._executor = executor

            for wave in plan.execution_order:
                if self._cancelled:
                    break

                # Execute all tasks in this wave in parallel
                futures: Dict[Future, ParallelTask] = {}
                for task_id in wave:
                    task = plan.get_task(task_id)
                    if task and not self._cancelled:
                        future = executor.submit(
                            self._execute_task,
                            task,
                            on_task_start,
                            on_task_complete,
                        )
                        futures[future] = task

                # Wait for all tasks in this wave to complete
                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        future.result()
                        completed_tasks.append(task)
                    except Exception as e:
                        task.status = TaskStatus.FAILED
                        task.error = str(e)
                        completed_tasks.append(task)

        self._executor = None
        return completed_tasks

    def _execute_task(
        self,
        task: ParallelTask,
        on_start: Optional[Callable[[ParallelTask], None]],
        on_complete: Optional[Callable[[ParallelTask], None]],
    ) -> None:
        """Execute a single task."""
        # Acquire resource slot
        if not self._resources.acquire_agent_slot(timeout=60):
            task.status = TaskStatus.FAILED
            task.error = "Timeout waiting for agent slot"
            return

        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()

            if on_start:
                on_start(task)

            # Get the agent
            agent = self._agents.get(task.agent_name)
            if not agent:
                task.status = TaskStatus.FAILED
                task.error = f"Unknown agent: {task.agent_name}"
                return

            # Create context
            from .base import AgentContext
            context = task.context or AgentContext(task=task.task)

            # Execute the agent
            result = agent.execute(context)

            task.result = result
            task.status = (
                TaskStatus.COMPLETED if result.success
                else TaskStatus.FAILED
            )
            if not result.success:
                task.error = result.error

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            task.completed_at = datetime.now()
            self._resources.release_agent_slot()

            if on_complete:
                on_complete(task)

    def execute_tasks(
        self,
        tasks: List[Dict[str, Any]],
        show_progress: bool = True,
    ) -> List[ParallelTask]:
        """
        Execute a list of tasks, automatically determining parallelism.

        Args:
            tasks: List of task dicts with 'agent', 'task', and optional 'depends_on'
            show_progress: Whether to show progress UI

        Returns:
            List of completed tasks
        """
        # Build dependency graph
        graph = DependencyGraph()
        for i, task_spec in enumerate(tasks):
            task_id = task_spec.get("id", f"task_{i}")
            graph.add_task(
                task_id=task_id,
                agent_name=task_spec["agent"],
                task=task_spec["task"],
                depends_on=task_spec.get("depends_on"),
            )

        # Create and execute plan
        plan = graph.create_plan()

        if show_progress:
            return self._execute_with_progress(plan)
        else:
            return self.execute_plan(plan)

    def _execute_with_progress(self, plan: ExecutionPlan) -> List[ParallelTask]:
        """Execute plan with progress display."""
        task_progress: Dict[str, str] = {}

        def on_start(task: ParallelTask):
            task_progress[task.id] = "running"

        def on_complete(task: ParallelTask):
            task_progress[task.id] = (
                "completed" if task.status == TaskStatus.COMPLETED else "failed"
            )

        def make_progress_table() -> Table:
            table = Table(title="Parallel Execution Progress")
            table.add_column("Task", style="cyan")
            table.add_column("Agent", style="blue")
            table.add_column("Status", style="green")
            table.add_column("Duration", style="dim")

            for task in plan.tasks:
                status = task_progress.get(task.id, "pending")
                status_style = {
                    "pending": "dim",
                    "running": "yellow",
                    "completed": "green",
                    "failed": "red",
                }.get(status, "white")

                duration = ""
                if task.duration:
                    duration = f"{task.duration:.1f}s"
                elif task.started_at:
                    elapsed = (datetime.now() - task.started_at).total_seconds()
                    duration = f"{elapsed:.1f}s"

                table.add_row(
                    task.task[:40] + "..." if len(task.task) > 40 else task.task,
                    task.agent_name,
                    f"[{status_style}]{status}[/{status_style}]",
                    duration,
                )

            return table

        # Show progress while executing
        results: List[ParallelTask] = []

        with Live(
            make_progress_table(),
            console=self._console,
            refresh_per_second=2,
        ) as live:
            def update_live(_):
                live.update(make_progress_table())

            results = self.execute_plan(
                plan,
                on_task_start=lambda t: (on_start(t), update_live(t)),
                on_task_complete=lambda t: (on_complete(t), update_live(t)),
            )

        return results

    def cancel(self) -> None:
        """Cancel all pending/running tasks."""
        with self._lock:
            self._cancelled = True
            if self._executor:
                self._executor.shutdown(wait=False, cancel_futures=True)


class ParallelAgentRunner:
    """
    High-level interface for running agents in parallel.

    Example usage:
        runner = ParallelAgentRunner(console=console)
        runner.add_task("code", "Implement login function")
        runner.add_task("test", "Write tests for login", depends_on=["task_0"])
        results = runner.run()
    """

    def __init__(
        self,
        agents: Optional[Dict[str, "BaseAgent"]] = None,
        console: Optional[Console] = None,
    ):
        self._console = console or Console()
        self._agents = agents or {}
        self._tasks: List[Dict[str, Any]] = []
        self._task_counter = 0

    def register_agent(self, name: str, agent: "BaseAgent") -> None:
        """Register an agent for parallel execution."""
        self._agents[name] = agent

    def add_task(
        self,
        agent_name: str,
        task: str,
        task_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a task for parallel execution.

        Args:
            agent_name: Name of the agent to execute the task
            task: Task description
            task_id: Optional custom task ID
            depends_on: List of task IDs this task depends on
            metadata: Optional metadata dict

        Returns:
            The task ID
        """
        if task_id is None:
            task_id = f"task_{self._task_counter}"
            self._task_counter += 1

        self._tasks.append({
            "id": task_id,
            "agent": agent_name,
            "task": task,
            "depends_on": depends_on,
            "metadata": metadata or {},
        })

        return task_id

    def run(self, show_progress: bool = True) -> List[ParallelTask]:
        """
        Run all added tasks.

        Args:
            show_progress: Whether to show progress UI

        Returns:
            List of completed tasks
        """
        if not self._agents:
            raise ValueError("No agents registered")

        executor = ParallelExecutor(
            agents=self._agents,
            console=self._console,
        )

        return executor.execute_tasks(self._tasks, show_progress=show_progress)

    def clear(self) -> None:
        """Clear all tasks."""
        self._tasks.clear()
        self._task_counter = 0


# Convenience function
def run_agents_parallel(
    tasks: List[Dict[str, Any]],
    agents: Dict[str, "BaseAgent"],
    console: Optional[Console] = None,
    show_progress: bool = True,
) -> List[ParallelTask]:
    """
    Run multiple agent tasks in parallel.

    Args:
        tasks: List of task dicts with 'agent', 'task', and optional 'depends_on'
        agents: Dict mapping agent names to agent instances
        console: Console for output
        show_progress: Whether to show progress UI

    Returns:
        List of completed tasks

    Example:
        results = run_agents_parallel(
            tasks=[
                {"agent": "code", "task": "Implement feature", "id": "impl"},
                {"agent": "test", "task": "Write tests", "depends_on": ["impl"]},
            ],
            agents={"code": code_agent, "test": test_agent},
        )
    """
    executor = ParallelExecutor(
        agents=agents,
        console=console,
    )
    return executor.execute_tasks(tasks, show_progress=show_progress)
