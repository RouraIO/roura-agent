"""
Roura Agent IDE Integrations - Cursor, Xcode, and other IDE agents.

© Roura.io
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from .base import (
    AgentCapability,
    AgentContext,
    AgentResult,
    BaseAgent,
)


class CursorAgent(BaseAgent):
    """
    Agent for integrating with Cursor IDE.

    Cursor is an AI-powered code editor. This agent can:
    - Open files/projects in Cursor
    - Send prompts to Cursor's AI (Composer)
    - Coordinate with Cursor for code generation
    """

    name = "cursor"
    description = "Integrates with Cursor IDE for AI-assisted coding"
    capabilities = [
        AgentCapability.CODE_WRITE,
        AgentCapability.CODE_READ,
        AgentCapability.DELEGATE,
    ]

    PATTERNS = [
        r"cursor\b",
        r"open\s+in\s+cursor",
        r"use\s+cursor",
        r"send\s+to\s+cursor",
        r"cursor\s+composer",
    ]

    def __init__(
        self,
        console: Optional[Console] = None,
        llm: Optional[Any] = None,
    ):
        super().__init__(console, llm)
        self._cursor_path = self._find_cursor()

    def _find_cursor(self) -> Optional[str]:
        """Find Cursor CLI or app path."""
        # Check for cursor CLI in PATH
        try:
            result = subprocess.run(
                ["which", "cursor"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        # Check common macOS locations
        mac_paths = [
            "/Applications/Cursor.app/Contents/MacOS/Cursor",
            os.path.expanduser("~/Applications/Cursor.app/Contents/MacOS/Cursor"),
        ]
        for path in mac_paths:
            if os.path.exists(path):
                return path

        return None

    @property
    def system_prompt(self) -> str:
        return """You are a Cursor IDE Agent that integrates with the Cursor code editor.

Your responsibilities:
- Open files and projects in Cursor
- Coordinate code generation tasks with Cursor's AI
- Bridge between Roura Agent and Cursor for seamless workflows

When working with Cursor:
1. Check if Cursor is available
2. Open relevant files/projects
3. Delegate appropriate tasks to Cursor's Composer
4. Report back results and coordinate next steps"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        import re
        task_lower = task.lower()

        # Explicit Cursor mentions
        if "cursor" in task_lower:
            return True, 0.9

        # Check patterns
        for pattern in self.PATTERNS:
            if re.search(pattern, task_lower):
                return True, 0.8

        return False, 0.0

    def is_available(self) -> bool:
        """Check if Cursor is installed and available."""
        return self._cursor_path is not None

    def open_in_cursor(self, path: str) -> AgentResult:
        """Open a file or directory in Cursor."""
        if not self._cursor_path:
            return AgentResult(
                success=False,
                error="Cursor not found. Install from https://cursor.sh",
            )

        try:
            subprocess.Popen(
                [self._cursor_path, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return AgentResult(
                success=True,
                output=f"Opened {path} in Cursor",
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute Cursor-related task."""
        self.log(f"Cursor task: {context.task[:50]}...")

        if not self.is_available():
            return AgentResult(
                success=False,
                error="Cursor IDE not found. Install from https://cursor.sh",
            )

        task_lower = context.task.lower()

        # Open project in Cursor
        if "open" in task_lower and context.project_root:
            return self.open_in_cursor(context.project_root)

        # For other tasks, provide guidance
        return AgentResult(
            success=True,
            output=(
                f"Cursor is available at {self._cursor_path}\n\n"
                "To use Cursor for this task:\n"
                "1. Open your project in Cursor\n"
                "2. Use Cursor Composer (Cmd+K) for AI assistance\n"
                "3. Results will sync back through your project files"
            ),
        )


class XcodeAgent(BaseAgent):
    """
    Agent for integrating with Xcode.

    Handles iOS/macOS development tasks:
    - Open projects in Xcode
    - Build and run projects
    - Run tests
    - Archive for distribution
    """

    name = "xcode"
    description = "Integrates with Xcode for iOS/macOS development"
    capabilities = [
        AgentCapability.CODE_READ,
        AgentCapability.TEST_RUN,
        AgentCapability.SHELL,
    ]

    PATTERNS = [
        r"xcode\b",
        r"ios\b",
        r"macos\b",
        r"swift\b",
        r"xcworkspace\b",
        r"xcodeproj\b",
        r"simulator\b",
        r"iphone\b",
        r"ipad\b",
    ]

    def __init__(
        self,
        console: Optional[Console] = None,
        llm: Optional[Any] = None,
    ):
        super().__init__(console, llm)

    @property
    def system_prompt(self) -> str:
        return """You are an Xcode Agent specialized in iOS/macOS development.

Your responsibilities:
- Open projects in Xcode
- Build projects using xcodebuild
- Run tests using xcodebuild test
- Manage simulators
- Archive for App Store/TestFlight

When working with Xcode:
1. Identify the .xcodeproj or .xcworkspace
2. Use xcodebuild for command-line operations
3. Open Xcode for visual tasks
4. Coordinate with other agents for Swift code changes"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        import re
        task_lower = task.lower()

        # Check patterns
        for pattern in self.PATTERNS:
            if re.search(pattern, task_lower):
                return True, 0.85

        # Check if project has Xcode files
        if context and context.project_root:
            project_path = Path(context.project_root)
            has_xcode = (
                list(project_path.glob("*.xcodeproj")) or
                list(project_path.glob("*.xcworkspace"))
            )
            if has_xcode and any(
                word in task_lower
                for word in ["build", "run", "test", "archive", "open"]
            ):
                return True, 0.7

        return False, 0.0

    def is_available(self) -> bool:
        """Check if Xcode/xcodebuild is available."""
        try:
            result = subprocess.run(
                ["xcodebuild", "-version"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def find_xcode_project(self, root: str) -> Optional[str]:
        """Find .xcworkspace or .xcodeproj in directory."""
        root_path = Path(root)

        # Prefer workspace over project
        workspaces = list(root_path.glob("*.xcworkspace"))
        if workspaces:
            return str(workspaces[0])

        projects = list(root_path.glob("*.xcodeproj"))
        if projects:
            return str(projects[0])

        return None

    def open_in_xcode(self, path: str) -> AgentResult:
        """Open a file or project in Xcode."""
        try:
            subprocess.Popen(
                ["open", "-a", "Xcode", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return AgentResult(
                success=True,
                output=f"Opened {path} in Xcode",
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def build(self, project: str, scheme: Optional[str] = None) -> AgentResult:
        """Build an Xcode project."""
        cmd = ["xcodebuild"]

        if project.endswith(".xcworkspace"):
            cmd.extend(["-workspace", project])
        else:
            cmd.extend(["-project", project])

        if scheme:
            cmd.extend(["-scheme", scheme])

        cmd.append("build")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode == 0:
                return AgentResult(
                    success=True,
                    output="Build succeeded",
                    artifacts={"stdout": result.stdout[-2000:]},  # Last 2000 chars
                )
            else:
                return AgentResult(
                    success=False,
                    error=f"Build failed:\n{result.stderr[-1000:]}",
                )
        except subprocess.TimeoutExpired:
            return AgentResult(success=False, error="Build timed out after 5 minutes")
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def run_tests(self, project: str, scheme: Optional[str] = None) -> AgentResult:
        """Run tests for an Xcode project."""
        cmd = ["xcodebuild", "test"]

        if project.endswith(".xcworkspace"):
            cmd.extend(["-workspace", project])
        else:
            cmd.extend(["-project", project])

        if scheme:
            cmd.extend(["-scheme", scheme])

        # Use simulator
        cmd.extend(["-destination", "platform=iOS Simulator,name=iPhone 15"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for tests
            )

            if result.returncode == 0:
                return AgentResult(
                    success=True,
                    output="All tests passed",
                    artifacts={"stdout": result.stdout[-3000:]},
                )
            else:
                return AgentResult(
                    success=False,
                    error=f"Tests failed:\n{result.stderr[-1500:]}",
                )
        except subprocess.TimeoutExpired:
            return AgentResult(success=False, error="Tests timed out after 10 minutes")
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute Xcode-related task."""
        self.log(f"Xcode task: {context.task[:50]}...")

        if not self.is_available():
            return AgentResult(
                success=False,
                error="Xcode not found. Install from the Mac App Store.",
            )

        task_lower = context.task.lower()

        # Find Xcode project
        project = None
        if context.project_root:
            project = self.find_xcode_project(context.project_root)

        # Open in Xcode
        if "open" in task_lower:
            path = project or context.project_root or "."
            return self.open_in_xcode(path)

        # Build
        if "build" in task_lower and project:
            return self.build(project)

        # Test
        if "test" in task_lower and project:
            return self.run_tests(project)

        # Default - provide info
        if project:
            return AgentResult(
                success=True,
                output=f"Found Xcode project: {project}\n\nAvailable commands:\n- build\n- test\n- open",
            )
        else:
            return AgentResult(
                success=True,
                output="No Xcode project found in current directory.",
            )


class IDEBridgeAgent(BaseAgent):
    """
    Agent that bridges between multiple IDEs and coordinates workflows.

    Manages handoffs between:
    - Roura Agent (local AI)
    - Cursor (AI code editor)
    - Xcode (iOS/macOS development)
    - VS Code (general development)
    """

    name = "ide-bridge"
    description = "Coordinates work across multiple IDEs"
    capabilities = [
        AgentCapability.DELEGATE,
        AgentCapability.PLAN,
    ]

    def __init__(
        self,
        console: Optional[Console] = None,
        llm: Optional[Any] = None,
    ):
        super().__init__(console, llm)
        self._cursor = CursorAgent(console=console, llm=llm)
        self._xcode = XcodeAgent(console=console, llm=llm)

    @property
    def system_prompt(self) -> str:
        return """You are an IDE Bridge Agent that coordinates work across multiple development environments.

Your responsibilities:
- Route tasks to the appropriate IDE/tool
- Coordinate multi-step workflows across tools
- Handle handoffs between Cursor, Xcode, and command line
- Track work progress across environments

Workflow patterns:
1. Idea → Cursor (code generation) → Roura (review) → Xcode (build/test)
2. Bug report → Roura (analyze) → Cursor (fix) → Git (commit)
3. Feature request → Plan → Cursor (implement) → Test → Deploy"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        # Multi-IDE tasks
        if any(word in task_lower for word in ["cursor", "xcode", "vscode"]):
            if any(word in task_lower for word in ["and", "then", "after", "workflow"]):
                return True, 0.9

        return False, 0.0

    def execute(self, context: AgentContext) -> AgentResult:
        """Coordinate work across IDEs."""
        self.log(f"Coordinating: {context.task[:50]}...")

        # Check available tools
        available = []
        if self._cursor.is_available():
            available.append("Cursor")
        if self._xcode.is_available():
            available.append("Xcode")

        task_lower = context.task.lower()

        # Route to appropriate agent
        results = []

        if "cursor" in task_lower:
            result = self._cursor.execute(context)
            results.append(("Cursor", result))

        if "xcode" in task_lower or "build" in task_lower or "ios" in task_lower:
            result = self._xcode.execute(context)
            results.append(("Xcode", result))

        if not results:
            return AgentResult(
                success=True,
                output=f"Available IDEs: {', '.join(available) or 'None detected'}\n\n"
                "Specify which IDE to use or describe your workflow.",
            )

        # Combine results
        output_parts = []
        all_success = True
        for name, result in results:
            status = "✓" if result.success else "✗"
            output_parts.append(f"{status} {name}: {result.output or result.error}")
            if not result.success:
                all_success = False

        return AgentResult(
            success=all_success,
            output="\n\n".join(output_parts),
        )
