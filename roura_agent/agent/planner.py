"""
Roura Agent Planner - Generates and formats execution plans.

© Roura.io
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree


class StepType(Enum):
    """Types of plan steps."""
    READ = "read"        # Read a file (safe)
    LIST = "list"        # List directory (safe)
    WRITE = "write"      # Write/create file (needs approval)
    EDIT = "edit"        # Edit file (needs approval)
    DELETE = "delete"    # Delete file (needs approval)
    SHELL = "shell"      # Run shell command (needs approval)
    GIT = "git"          # Git operation (varies)
    GITHUB = "github"    # GitHub operation (needs approval)
    JIRA = "jira"        # Jira operation (needs approval)
    THINK = "think"      # Agent reasoning (no tool)


@dataclass
class PlanStep:
    """A single step in a plan."""
    number: int
    action: StepType
    description: str
    tool: Optional[str] = None
    args: dict = field(default_factory=dict)
    requires_approval: bool = False
    depends_on: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "action": self.action.value,
            "description": self.description,
            "tool": self.tool,
            "args": self.args,
            "requires_approval": self.requires_approval,
            "depends_on": self.depends_on,
        }


@dataclass
class Plan:
    """An execution plan."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    estimated_changes: int = 0
    requires_approval: bool = True

    def add_step(
        self,
        action: StepType,
        description: str,
        tool: Optional[str] = None,
        args: dict = None,
        requires_approval: bool = None,
        depends_on: list[int] = None,
    ) -> PlanStep:
        """Add a step to the plan."""
        # Auto-determine if approval needed based on action type
        if requires_approval is None:
            requires_approval = action in {
                StepType.WRITE,
                StepType.EDIT,
                StepType.DELETE,
                StepType.SHELL,
                StepType.GITHUB,
                StepType.JIRA,
            }

        step = PlanStep(
            number=len(self.steps) + 1,
            action=action,
            description=description,
            tool=tool,
            args=args or {},
            requires_approval=requires_approval,
            depends_on=depends_on or [],
        )
        self.steps.append(step)

        if requires_approval:
            self.requires_approval = True

        return step

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "context_files": self.context_files,
            "estimated_changes": self.estimated_changes,
            "requires_approval": self.requires_approval,
        }


class Planner:
    """
    Generates and formats execution plans.

    Constraint #1: Always propose a plan before acting.
    """

    # Action icons for pretty display
    ICONS = {
        StepType.READ: "📖",
        StepType.LIST: "📂",
        StepType.WRITE: "✏️",
        StepType.EDIT: "🔧",
        StepType.DELETE: "🗑️",
        StepType.SHELL: "💻",
        StepType.GIT: "🌿",
        StepType.GITHUB: "🐙",
        StepType.JIRA: "📋",
        StepType.THINK: "💭",
    }

    # Action colors
    COLORS = {
        StepType.READ: "cyan",
        StepType.LIST: "cyan",
        StepType.WRITE: "yellow",
        StepType.EDIT: "yellow",
        StepType.DELETE: "red",
        StepType.SHELL: "magenta",
        StepType.GIT: "green",
        StepType.GITHUB: "blue",
        StepType.JIRA: "blue",
        StepType.THINK: "dim",
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def format_plan(self, plan: Plan) -> Panel:
        """Format a plan as a Rich panel."""
        # Create tree structure
        tree = Tree(f"[bold]{plan.goal}[/bold]")

        for step in plan.steps:
            icon = self.ICONS.get(step.action, "•")
            color = self.COLORS.get(step.action, "white")

            # Build step text
            approval = " [red]⚠ approval[/red]" if step.requires_approval else ""
            step_text = f"{icon} [{color}]{step.description}[/{color}]{approval}"

            # Add tool info if present
            if step.tool:
                step_text += f" [dim]({step.tool})[/dim]"

            tree.add(step_text)

        # Summary line
        safe_count = sum(1 for s in plan.steps if not s.requires_approval)
        approval_count = sum(1 for s in plan.steps if s.requires_approval)

        summary = f"\n[dim]{len(plan.steps)} steps: {safe_count} safe, {approval_count} need approval[/dim]"

        # Wrap in panel
        content = Text()
        content.append_text(Text.from_markup(str(tree)))
        content.append(summary)

        return Panel(
            tree,
            title="[bold cyan]📋 Plan[/bold cyan]",
            subtitle=f"[dim]{safe_count} safe, {approval_count} need approval[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )

    def format_plan_simple(self, plan: Plan) -> str:
        """Format a plan as simple text."""
        lines = [f"Plan: {plan.goal}", ""]

        for step in plan.steps:
            icon = self.ICONS.get(step.action, "•")
            approval = " ⚠" if step.requires_approval else ""
            lines.append(f"  {step.number}. {icon} {step.description}{approval}")

        return "\n".join(lines)

    def display_plan(self, plan: Plan) -> None:
        """Display a plan to the console."""
        self.console.print()
        self.console.print(self.format_plan(plan))
        self.console.print()

    def create_plan(self, goal: str) -> Plan:
        """Create a new empty plan."""
        return Plan(goal=goal)


# Singleton planner instance
_planner: Optional[Planner] = None


def get_planner(console: Optional[Console] = None) -> Planner:
    """Get or create the planner instance."""
    global _planner
    if _planner is None:
        _planner = Planner(console)
    return _planner
