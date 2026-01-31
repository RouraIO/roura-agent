"""
Roura Agent PRO Automation - Workflow automation.

Provides:
- Workflow definition and execution
- Trigger-based automation
- Step chaining with context
- Scheduling support

© Roura.io
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from ..logging import get_logger

logger = get_logger(__name__)


class AutomationTrigger(str, Enum):
    """Types of automation triggers."""
    MANUAL = "manual"  # Triggered manually
    FILE_CHANGE = "file_change"  # On file modification
    GIT_COMMIT = "git_commit"  # On git commit
    GIT_PUSH = "git_push"  # On git push
    SCHEDULE = "schedule"  # Scheduled (cron-like)
    PR_OPEN = "pr_open"  # On PR opened
    PR_MERGE = "pr_merge"  # On PR merged
    WEBHOOK = "webhook"  # External webhook


class StepStatus(str, Enum):
    """Status of a workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    name: str
    action: str  # Action type (e.g., "review", "fix", "command")
    config: dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None  # Condition expression
    continue_on_error: bool = False
    timeout_seconds: int = 300
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Runtime state
    status: StepStatus = StepStatus.PENDING
    output: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "action": self.action,
            "config": self.config,
            "condition": self.condition,
            "continue_on_error": self.continue_on_error,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowStep":
        step = cls(
            name=data["name"],
            action=data["action"],
            config=data.get("config", {}),
            condition=data.get("condition"),
            continue_on_error=data.get("continue_on_error", False),
            timeout_seconds=data.get("timeout_seconds", 300),
            step_id=data.get("step_id", str(uuid.uuid4())),
        )
        step.status = StepStatus(data.get("status", "pending"))
        step.output = data.get("output")
        step.error = data.get("error")
        step.started_at = data.get("started_at")
        step.finished_at = data.get("finished_at")
        return step


@dataclass
class Workflow:
    """A workflow definition with multiple steps."""
    name: str
    description: str = ""
    trigger: AutomationTrigger = AutomationTrigger.MANUAL
    trigger_config: dict[str, Any] = field(default_factory=dict)
    steps: list[WorkflowStep] = field(default_factory=list)
    enabled: bool = True
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_step(
        self,
        name: str,
        action: str,
        **config,
    ) -> WorkflowStep:
        """Add a step to the workflow."""
        step = WorkflowStep(name=name, action=action, config=config)
        self.steps.append(step)
        return step

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.value,
            "trigger_config": self.trigger_config,
            "steps": [s.to_dict() for s in self.steps],
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        workflow = cls(
            name=data["name"],
            description=data.get("description", ""),
            trigger=AutomationTrigger(data.get("trigger", "manual")),
            trigger_config=data.get("trigger_config", {}),
            enabled=data.get("enabled", True),
            workflow_id=data.get("workflow_id", str(uuid.uuid4())),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )
        workflow.steps = [
            WorkflowStep.from_dict(s)
            for s in data.get("steps", [])
        ]
        return workflow

    @classmethod
    def from_yaml(cls, yaml_content: str) -> "Workflow":
        """Create workflow from YAML definition."""
        try:
            import yaml
            data = yaml.safe_load(yaml_content)
            return cls.from_dict(data)
        except ImportError:
            raise ImportError("PyYAML is required for YAML workflow definitions")


@dataclass
class WorkflowRun:
    """A single execution of a workflow."""
    workflow_id: str
    workflow_name: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger: AutomationTrigger = AutomationTrigger.MANUAL
    trigger_data: dict[str, Any] = field(default_factory=dict)
    status: str = "running"
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None
    step_results: list[dict] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "trigger": self.trigger.value,
            "trigger_data": self.trigger_data,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "step_results": self.step_results,
            "context": self.context,
        }


# Step action handlers
StepHandler = Callable[[WorkflowStep, dict], Any]
_step_handlers: dict[str, StepHandler] = {}


def register_step_handler(action: str) -> Callable[[StepHandler], StepHandler]:
    """Decorator to register a step handler."""
    def decorator(func: StepHandler) -> StepHandler:
        _step_handlers[action] = func
        return func
    return decorator


@register_step_handler("command")
def handle_command(step: WorkflowStep, context: dict) -> str:
    """Execute a shell command."""
    import subprocess

    command = step.config.get("command", "")
    if not command:
        raise ValueError("No command specified")

    # Substitute context variables
    for key, value in context.items():
        command = command.replace(f"${{{key}}}", str(value))

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=step.timeout_seconds,
    )

    if result.returncode != 0 and not step.continue_on_error:
        raise RuntimeError(f"Command failed: {result.stderr}")

    return result.stdout


@register_step_handler("review")
def handle_review(step: WorkflowStep, context: dict) -> dict:
    """Run code review."""
    from .ci import CIConfig, CIMode, CIRunner

    config = CIConfig(
        mode=CIMode.REVIEW,
        target_path=step.config.get("target", "."),
        max_files=step.config.get("max_files", 50),
        timeout_seconds=step.timeout_seconds,
    )

    runner = CIRunner(config)
    result = runner.run()

    return result.to_dict()


@register_step_handler("fix")
def handle_fix(step: WorkflowStep, context: dict) -> dict:
    """Apply automatic fixes."""
    from .ci import CIConfig, CIMode, CIRunner

    config = CIConfig(
        mode=CIMode.FIX,
        target_path=step.config.get("target", "."),
        max_files=step.config.get("max_files", 50),
        timeout_seconds=step.timeout_seconds,
    )

    runner = CIRunner(config)
    result = runner.run()

    return result.to_dict()


@register_step_handler("notify")
def handle_notify(step: WorkflowStep, context: dict) -> dict:
    """Send notification."""
    # Placeholder for notification integration
    message = step.config.get("message", "Workflow notification")
    channel = step.config.get("channel", "default")

    logger.info(f"Notification [{channel}]: {message}")

    return {"sent": True, "channel": channel, "message": message}


class WorkflowRunner:
    """
    Executes workflows.

    Provides:
    - Sequential step execution
    - Context passing between steps
    - Error handling and recovery
    - Run history
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path or self._default_storage_path()
        self._workflows: dict[str, Workflow] = {}
        self._runs: list[WorkflowRun] = []
        self._load()

    @staticmethod
    def _default_storage_path() -> Path:
        path = Path.home() / ".config" / "roura-agent" / "workflows.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self) -> None:
        """Load workflows from storage."""
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text())
                self._workflows = {
                    w["workflow_id"]: Workflow.from_dict(w)
                    for w in data.get("workflows", [])
                }
                self._runs = [
                    WorkflowRun(**r) if isinstance(r, dict) else r
                    for r in data.get("runs", [])[-100:]  # Keep last 100 runs
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load workflows: {e}")

    def _save(self) -> None:
        """Save workflows to storage."""
        data = {
            "workflows": [w.to_dict() for w in self._workflows.values()],
            "runs": [r.to_dict() for r in self._runs[-100:]],
        }
        self._storage_path.write_text(json.dumps(data, indent=2))

    def add_workflow(self, workflow: Workflow) -> None:
        """Add or update a workflow."""
        self._workflows[workflow.workflow_id] = workflow
        self._save()

    def remove_workflow(self, workflow_id: str) -> bool:
        """Remove a workflow."""
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            self._save()
            return True
        return False

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        """List all workflows."""
        return list(self._workflows.values())

    def run(
        self,
        workflow: Workflow,
        trigger_data: Optional[dict] = None,
        initial_context: Optional[dict] = None,
    ) -> WorkflowRun:
        """
        Execute a workflow.

        Args:
            workflow: Workflow to execute
            trigger_data: Data from the trigger
            initial_context: Initial context variables

        Returns:
            WorkflowRun with results
        """
        run = WorkflowRun(
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.name,
            trigger=workflow.trigger,
            trigger_data=trigger_data or {},
            context=initial_context or {},
        )

        # Reset step states
        for step in workflow.steps:
            step.status = StepStatus.PENDING
            step.output = None
            step.error = None
            step.started_at = None
            step.finished_at = None

        try:
            for step in workflow.steps:
                # Check condition
                if step.condition:
                    if not self._evaluate_condition(step.condition, run.context):
                        step.status = StepStatus.SKIPPED
                        run.step_results.append(step.to_dict())
                        continue

                # Execute step
                step.status = StepStatus.RUNNING
                step.started_at = datetime.now().isoformat()

                try:
                    handler = _step_handlers.get(step.action)
                    if not handler:
                        raise ValueError(f"Unknown action: {step.action}")

                    output = handler(step, run.context)
                    step.output = output
                    step.status = StepStatus.SUCCESS

                    # Update context with output
                    run.context[f"{step.name}_output"] = output

                except Exception as e:
                    step.error = str(e)
                    step.status = StepStatus.FAILED
                    logger.error(f"Step {step.name} failed: {e}")

                    if not step.continue_on_error:
                        run.status = "failed"
                        break

                finally:
                    step.finished_at = datetime.now().isoformat()
                    run.step_results.append(step.to_dict())

            # Determine final status
            if run.status != "failed":
                failed_steps = [s for s in workflow.steps if s.status == StepStatus.FAILED]
                run.status = "failed" if failed_steps else "success"

        except Exception as e:
            run.status = "error"
            logger.exception(f"Workflow execution failed: {e}")

        run.finished_at = datetime.now().isoformat()
        self._runs.append(run)
        self._save()

        return run

    async def run_async(
        self,
        workflow: Workflow,
        trigger_data: Optional[dict] = None,
        initial_context: Optional[dict] = None,
    ) -> WorkflowRun:
        """Execute workflow asynchronously."""
        return await asyncio.to_thread(
            self.run,
            workflow,
            trigger_data,
            initial_context,
        )

    def _evaluate_condition(self, condition: str, context: dict) -> bool:
        """Evaluate a condition expression."""
        # Simple condition evaluation
        # In production, use a proper expression evaluator
        try:
            # Support simple comparisons like "step_output == 'success'"
            return eval(condition, {"__builtins__": {}}, context)
        except Exception:
            return True

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Get a workflow run by ID."""
        for run in self._runs:
            if run.run_id == run_id:
                return run
        return None

    def list_runs(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[WorkflowRun]:
        """List workflow runs."""
        runs = self._runs
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        return runs[-limit:]


# Default workflow runner
_workflow_runner: Optional[WorkflowRunner] = None


def get_workflow_runner() -> WorkflowRunner:
    """Get the global workflow runner."""
    global _workflow_runner
    if _workflow_runner is None:
        _workflow_runner = WorkflowRunner()
    return _workflow_runner
