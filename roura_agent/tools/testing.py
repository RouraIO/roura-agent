"""
Roura Agent Testing Tools - Auto-detect and run tests with failure parsing.

The killer feature: autonomous test fixing loops.

© Roura.io
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry


@dataclass
class TestFailure:
    """A single test failure with parsed details."""
    test_name: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    error_type: str = ""
    error_message: str = ""
    stack_trace: str = ""
    stdout: str = ""

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "stdout": self.stdout,
        }


@dataclass
class TestResult:
    """Result of running tests."""
    framework: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total: int = 0
    duration: float = 0.0
    success: bool = True
    failures: list[TestFailure] = field(default_factory=list)
    raw_output: str = ""
    command: str = ""

    def to_dict(self) -> dict:
        return {
            "framework": self.framework,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "total": self.total,
            "duration": self.duration,
            "success": self.success,
            "failures": [f.to_dict() for f in self.failures],
            "command": self.command,
        }


# Framework detection patterns
FRAMEWORK_MARKERS = {
    "pytest": ["pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py"],
    "unittest": ["test_*.py", "*_test.py"],
    "cargo": ["Cargo.toml"],
    "go": ["go.mod", "*_test.go"],
    "npm": ["package.json"],
    "swift": ["Package.swift", "*.xcodeproj"],
    "gradle": ["build.gradle", "build.gradle.kts"],
    "maven": ["pom.xml"],
    "rspec": ["Gemfile", "spec/"],
    "jest": ["jest.config.js", "jest.config.ts"],
    "vitest": ["vitest.config.ts", "vitest.config.js"],
}

# Test commands by framework
TEST_COMMANDS = {
    "pytest": "python -m pytest -v",
    "unittest": "python -m unittest discover -v",
    "cargo": "cargo test",
    "go": "go test -v ./...",
    "npm": "npm test",
    "jest": "npx jest",
    "vitest": "npx vitest run",
    "swift": "swift test",
    "gradle": "./gradlew test",
    "maven": "mvn test",
    "rspec": "bundle exec rspec",
}


def detect_test_framework(cwd: Optional[str] = None) -> Optional[str]:
    """Auto-detect the test framework based on project files."""
    root = Path(cwd) if cwd else Path.cwd()

    # Check for specific markers
    for framework, markers in FRAMEWORK_MARKERS.items():
        for marker in markers:
            if marker.startswith("*"):
                # Glob pattern
                if list(root.glob(marker)) or list(root.glob(f"**/{marker}")):
                    return framework
            elif marker.endswith("/"):
                # Directory
                if (root / marker.rstrip("/")).is_dir():
                    return framework
            else:
                # File
                if (root / marker).exists():
                    # Special handling for package.json - check for test script
                    if marker == "package.json":
                        try:
                            pkg = json.loads((root / marker).read_text())
                            scripts = pkg.get("scripts", {})
                            if "test" in scripts:
                                test_cmd = scripts["test"]
                                if "vitest" in test_cmd:
                                    return "vitest"
                                elif "jest" in test_cmd:
                                    return "jest"
                                return "npm"
                        except Exception:
                            pass
                    # Special handling for pyproject.toml - check for pytest
                    elif marker == "pyproject.toml":
                        try:
                            content = (root / marker).read_text()
                            if "[tool.pytest" in content or "pytest" in content:
                                return "pytest"
                        except Exception:
                            pass
                    else:
                        return framework

    return None


def get_test_command(framework: str, specific_test: Optional[str] = None) -> str:
    """Get the test command for a framework."""
    base_cmd = TEST_COMMANDS.get(framework, "")

    if specific_test:
        if framework == "pytest":
            return f"{base_cmd} {specific_test}"
        elif framework == "cargo":
            return f"{base_cmd} {specific_test}"
        elif framework == "go":
            return f"go test -v -run {specific_test} ./..."
        elif framework in ("jest", "vitest"):
            return f"{base_cmd} {specific_test}"
        elif framework == "swift":
            return f"{base_cmd} --filter {specific_test}"

    return base_cmd


def parse_pytest_output(output: str) -> TestResult:
    """Parse pytest output into structured result."""
    result = TestResult(framework="pytest", raw_output=output)

    # Parse summary line: "X passed, Y failed, Z skipped in N.NNs"
    summary_match = re.search(
        r"(?:=+\s+)?(\d+)\s+passed(?:,\s+(\d+)\s+failed)?(?:,\s+(\d+)\s+skipped)?(?:,\s+(\d+)\s+error)?.*?in\s+([\d.]+)s",
        output,
        re.IGNORECASE
    )

    if summary_match:
        result.passed = int(summary_match.group(1) or 0)
        result.failed = int(summary_match.group(2) or 0)
        result.skipped = int(summary_match.group(3) or 0)
        result.errors = int(summary_match.group(4) or 0)
        result.duration = float(summary_match.group(5) or 0)

    # Also check for "X failed" pattern
    failed_match = re.search(r"(\d+)\s+failed", output, re.IGNORECASE)
    if failed_match and result.failed == 0:
        result.failed = int(failed_match.group(1))

    result.total = result.passed + result.failed + result.skipped + result.errors
    result.success = result.failed == 0 and result.errors == 0

    # Parse individual failures
    # Pattern: "FAILED test_file.py::test_name - ErrorType: message"
    failure_blocks = re.split(r"_{10,}\s+FAILURES\s+_{10,}", output)
    if len(failure_blocks) > 1:
        failures_section = failure_blocks[1]

        # Split by test headers
        test_blocks = re.split(r"_{5,}\s+([\w./]+::\w+)", failures_section)

        for i in range(1, len(test_blocks), 2):
            if i + 1 < len(test_blocks):
                test_name = test_blocks[i].strip()
                test_body = test_blocks[i + 1]

                failure = TestFailure(test_name=test_name)

                # Extract file and line
                loc_match = re.search(r"([\w/]+\.py):(\d+):", test_body)
                if loc_match:
                    failure.file_path = loc_match.group(1)
                    failure.line_number = int(loc_match.group(2))

                # Extract error type and message
                error_match = re.search(r"([\w.]+Error|[\w.]+Exception):\s*(.+?)(?:\n|$)", test_body)
                if error_match:
                    failure.error_type = error_match.group(1)
                    failure.error_message = error_match.group(2).strip()

                failure.stack_trace = test_body.strip()[:2000]  # Limit size
                result.failures.append(failure)

    # Alternative: parse short summary failures
    short_failures = re.findall(r"FAILED\s+([\w./]+::\w+)\s+-\s+(\w+):\s*(.+)", output)
    if short_failures and not result.failures:
        for match in short_failures:
            test_name, error_type, message = match
            result.failures.append(TestFailure(
                test_name=test_name,
                error_type=error_type,
                error_message=message,
            ))

    return result


def parse_cargo_output(output: str) -> TestResult:
    """Parse cargo test output into structured result."""
    result = TestResult(framework="cargo", raw_output=output)

    # Parse summary: "test result: ok/FAILED. X passed; Y failed; Z ignored"
    summary_match = re.search(
        r"test result:\s*(\w+)\.\s*(\d+)\s+passed;\s*(\d+)\s+failed;\s*(\d+)\s+ignored",
        output
    )

    if summary_match:
        result.success = summary_match.group(1).lower() == "ok"
        result.passed = int(summary_match.group(2))
        result.failed = int(summary_match.group(3))
        result.skipped = int(summary_match.group(4))
        result.total = result.passed + result.failed + result.skipped

    # Parse failures
    # Pattern: "---- test_name stdout ----" followed by assertion/panic info
    failure_blocks = re.findall(
        r"----\s+([\w:]+)\s+stdout\s+----\n(.*?)(?=----|\nfailures:|\ntest result:)",
        output,
        re.DOTALL
    )

    for test_name, body in failure_blocks:
        failure = TestFailure(test_name=test_name)

        # Extract panic message
        panic_match = re.search(r"panicked at ['\"](.+?)['\"]", body)
        if panic_match:
            failure.error_message = panic_match.group(1)
            failure.error_type = "panic"

        # Extract assertion failure
        assert_match = re.search(r"assertion (?:failed|`[\w!]+` failed).*?:\s*(.+)", body, re.DOTALL)
        if assert_match:
            failure.error_message = assert_match.group(1).strip()[:500]
            failure.error_type = "assertion"

        # Extract file location
        loc_match = re.search(r"([\w/]+\.rs):(\d+):\d+", body)
        if loc_match:
            failure.file_path = loc_match.group(1)
            failure.line_number = int(loc_match.group(2))

        failure.stack_trace = body.strip()[:2000]
        result.failures.append(failure)

    return result


def parse_go_output(output: str) -> TestResult:
    """Parse go test output into structured result."""
    result = TestResult(framework="go", raw_output=output)

    # Count passed/failed
    result.passed = len(re.findall(r"---\s+PASS:", output))
    result.failed = len(re.findall(r"---\s+FAIL:", output))
    result.skipped = len(re.findall(r"---\s+SKIP:", output))
    result.total = result.passed + result.failed + result.skipped
    result.success = result.failed == 0

    # Parse failures
    failure_matches = re.findall(
        r"---\s+FAIL:\s+(\w+)\s+\(([\d.]+)s\)\n(.*?)(?=---\s+(?:PASS|FAIL|SKIP):|FAIL\s+[\w/]+|ok\s+[\w/]+|\Z)",
        output,
        re.DOTALL
    )

    for test_name, _duration, body in failure_matches:
        failure = TestFailure(test_name=test_name)

        # Extract file location
        loc_match = re.search(r"([\w/]+\.go):(\d+):", body)
        if loc_match:
            failure.file_path = loc_match.group(1)
            failure.line_number = int(loc_match.group(2))

        # Extract error message
        error_match = re.search(r"Error.*?:\s*(.+)", body)
        if error_match:
            failure.error_message = error_match.group(1).strip()

        failure.stack_trace = body.strip()[:2000]
        result.failures.append(failure)

    return result


def parse_jest_output(output: str) -> TestResult:
    """Parse jest/vitest output into structured result."""
    result = TestResult(framework="jest", raw_output=output)

    # Parse summary: "Tests: X failed, Y passed, Z total"
    summary_match = re.search(
        r"Tests:\s+(?:(\d+)\s+failed,\s+)?(?:(\d+)\s+passed,\s+)?(\d+)\s+total",
        output
    )

    if summary_match:
        result.failed = int(summary_match.group(1) or 0)
        result.passed = int(summary_match.group(2) or 0)
        result.total = int(summary_match.group(3) or 0)
        result.success = result.failed == 0

    # Parse failures
    # Pattern: "● Test Suite › test name"
    failure_matches = re.findall(
        r"●\s+(.+?)\n\n(.*?)(?=●|\n\s*Test Suites:|\Z)",
        output,
        re.DOTALL
    )

    for test_name, body in failure_matches:
        failure = TestFailure(test_name=test_name.strip())

        # Extract error message
        error_match = re.search(r"(Error|expect\(.*?\)).*?:\s*(.+?)(?:\n\n|\Z)", body, re.DOTALL)
        if error_match:
            failure.error_type = "AssertionError"
            failure.error_message = error_match.group(2).strip()[:500]

        # Extract file location
        loc_match = re.search(r"at.*?\(([\w/.]+):(\d+):\d+\)", body)
        if loc_match:
            failure.file_path = loc_match.group(1)
            failure.line_number = int(loc_match.group(2))

        failure.stack_trace = body.strip()[:2000]
        result.failures.append(failure)

    return result


def parse_test_output(framework: str, output: str) -> TestResult:
    """Parse test output based on framework."""
    parsers = {
        "pytest": parse_pytest_output,
        "cargo": parse_cargo_output,
        "go": parse_go_output,
        "jest": parse_jest_output,
        "vitest": parse_jest_output,  # Similar format
    }

    parser = parsers.get(framework)
    if parser:
        return parser(output)

    # Generic fallback
    result = TestResult(framework=framework, raw_output=output)
    result.success = "FAIL" not in output.upper() and "ERROR" not in output.upper()
    return result


def run_tests(
    framework: Optional[str] = None,
    specific_test: Optional[str] = None,
    cwd: Optional[str] = None,
    timeout: int = 300,
) -> TestResult:
    """Run tests and return parsed results."""
    working_dir = cwd or os.getcwd()

    # Auto-detect framework if not specified
    if not framework:
        framework = detect_test_framework(working_dir)
        if not framework:
            return TestResult(
                framework="unknown",
                success=False,
                raw_output="Could not detect test framework. Supported: pytest, cargo, go, jest, vitest, swift, gradle, maven, rspec"
            )

    # Get command
    command = get_test_command(framework, specific_test)
    if not command:
        return TestResult(
            framework=framework,
            success=False,
            raw_output=f"No test command configured for framework: {framework}"
        )

    # Run tests
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = proc.stdout + "\n" + proc.stderr
        result = parse_test_output(framework, output)
        result.command = command

        # Override success based on exit code
        if proc.returncode != 0 and result.success:
            result.success = False

        return result

    except subprocess.TimeoutExpired:
        return TestResult(
            framework=framework,
            success=False,
            command=command,
            raw_output=f"Tests timed out after {timeout} seconds"
        )
    except Exception as e:
        return TestResult(
            framework=framework,
            success=False,
            command=command,
            raw_output=f"Error running tests: {str(e)}"
        )


# ============= TOOL IMPLEMENTATIONS =============


@dataclass
class TestRunTool(Tool):
    """Run the project's test suite."""

    name: str = "test.run"
    description: str = "Auto-detect and run the project's test suite (pytest, cargo, go, jest, etc.)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("framework", str, "Test framework (auto-detect if not specified)", required=False),
        ToolParam("test", str, "Specific test to run (e.g., test_auth.py::test_login)", required=False),
        ToolParam("timeout", int, "Timeout in seconds (default 300)", required=False, default=300),
    ])

    def execute(
        self,
        framework: Optional[str] = None,
        test: Optional[str] = None,
        timeout: int = 300,
    ) -> ToolResult:
        result = run_tests(
            framework=framework,
            specific_test=test,
            timeout=timeout,
        )

        return ToolResult(
            success=True,  # Tool succeeded, tests may have failed
            output={
                "test_success": result.success,
                "framework": result.framework,
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "total": result.total,
                "duration": result.duration,
                "command": result.command,
                "failures": [f.to_dict() for f in result.failures],
                "raw_output": result.raw_output[:5000] if len(result.raw_output) > 5000 else result.raw_output,
            }
        )


@dataclass
class TestFailuresTool(Tool):
    """Get detailed information about failing tests."""

    name: str = "test.failures"
    description: str = "Run tests and return only failing tests with detailed stack traces"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("framework", str, "Test framework (auto-detect if not specified)", required=False),
        ToolParam("test", str, "Specific test to run", required=False),
    ])

    def execute(
        self,
        framework: Optional[str] = None,
        test: Optional[str] = None,
    ) -> ToolResult:
        result = run_tests(framework=framework, specific_test=test)

        if result.success:
            return ToolResult(
                success=True,
                output={
                    "status": "all_passing",
                    "passed": result.passed,
                    "total": result.total,
                }
            )

        return ToolResult(
            success=True,
            output={
                "status": "failures_found",
                "failed": result.failed,
                "total": result.total,
                "failures": [f.to_dict() for f in result.failures],
            }
        )


@dataclass
class TestLastTool(Tool):
    """Re-run the last failed test."""

    name: str = "test.last"
    description: str = "Re-run only the last failed tests (uses pytest --lf or equivalent)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("framework", str, "Test framework (auto-detect if not specified)", required=False),
    ])

    def execute(self, framework: Optional[str] = None) -> ToolResult:
        cwd = os.getcwd()

        if not framework:
            framework = detect_test_framework(cwd)

        # Framework-specific "last failed" commands
        commands = {
            "pytest": "python -m pytest --lf -v",
            "cargo": "cargo test",  # Cargo doesn't have --lf
            "jest": "npx jest --onlyFailures",
            "vitest": "npx vitest run --changed",
        }

        if not framework:
            return ToolResult(
                success=False,
                output=None,
                error="Could not detect test framework"
            )

        command = commands.get(framework, "")
        if not command:
            return ToolResult(
                success=False,
                output=None,
                error=f"Last-failed not supported for framework: {framework}"
            )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = proc.stdout + "\n" + proc.stderr
            result = parse_test_output(framework, output)

            return ToolResult(
                success=True,
                output={
                    "test_success": result.success,
                    "passed": result.passed,
                    "failed": result.failed,
                    "command": command,
                    "failures": [f.to_dict() for f in result.failures],
                }
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


@dataclass
class TestCoverageTool(Tool):
    """Run tests with coverage reporting."""

    name: str = "test.coverage"
    description: str = "Run tests with coverage and report uncovered lines"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("framework", str, "Test framework (auto-detect if not specified)", required=False),
        ToolParam("threshold", int, "Minimum coverage percentage to pass", required=False, default=0),
    ])

    def execute(
        self,
        framework: Optional[str] = None,
        threshold: int = 0,
    ) -> ToolResult:
        cwd = os.getcwd()

        if not framework:
            framework = detect_test_framework(cwd)

        if not framework:
            return ToolResult(
                success=False,
                output=None,
                error="Could not detect test framework"
            )

        # Coverage commands by framework
        commands = {
            "pytest": f"python -m pytest --cov=. --cov-report=term-missing --cov-fail-under={threshold}",
            "cargo": "cargo tarpaulin --out Stdout",
            "go": "go test -cover ./...",
            "jest": "npx jest --coverage",
            "vitest": "npx vitest run --coverage",
        }

        command = commands.get(framework, "")
        if not command:
            return ToolResult(
                success=False,
                output=None,
                error=f"Coverage not configured for framework: {framework}"
            )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,
            )

            output = proc.stdout + "\n" + proc.stderr

            # Parse coverage percentage
            coverage_match = re.search(r"(\d+(?:\.\d+)?)\s*%", output)
            coverage_pct = float(coverage_match.group(1)) if coverage_match else None

            return ToolResult(
                success=True,
                output={
                    "coverage_percent": coverage_pct,
                    "threshold": threshold,
                    "passed_threshold": coverage_pct >= threshold if coverage_pct else None,
                    "command": command,
                    "report": output[:10000],
                }
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


@dataclass
class TestFixTool(Tool):
    """
    THE KILLER FEATURE: Autonomous test fixing.

    Runs tests, analyzes failures, reads source files, and provides
    everything needed for the LLM to fix the failing tests.
    """

    name: str = "test.fix"
    description: str = "Run tests, analyze failures, and provide context for autonomous fixing. Returns failing tests with source code context."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("framework", str, "Test framework (auto-detect if not specified)", required=False),
        ToolParam("test", str, "Specific test to fix", required=False),
        ToolParam("max_failures", int, "Maximum failures to analyze (default 5)", required=False, default=5),
        ToolParam("context_lines", int, "Lines of context around failure (default 10)", required=False, default=10),
    ])

    def _read_file_context(self, file_path: str, line_number: int, context_lines: int = 10) -> dict:
        """Read source file with context around the failing line."""
        try:
            from pathlib import Path
            path = Path(file_path)

            # Try to resolve relative paths
            if not path.is_absolute():
                path = Path.cwd() / path

            if not path.exists():
                return {"error": f"File not found: {file_path}"}

            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = max(0, line_number - context_lines - 1)
            end = min(total_lines, line_number + context_lines)

            # Format with line numbers
            context = []
            for i, line in enumerate(lines[start:end], start=start + 1):
                marker = ">>> " if i == line_number else "    "
                context.append(f"{marker}{i:4d} | {line.rstrip()}")

            return {
                "file_path": str(path),
                "total_lines": total_lines,
                "context_start": start + 1,
                "context_end": end,
                "failing_line": line_number,
                "content": "\n".join(context),
                "full_file": "".join(lines) if total_lines < 500 else None,  # Include full file if small
            }
        except Exception as e:
            return {"error": f"Could not read file: {str(e)}"}

    def _read_test_file(self, test_name: str, file_path: Optional[str]) -> dict:
        """Read the test file to understand what's being tested."""
        if not file_path:
            return {"error": "No test file path available"}

        try:
            from pathlib import Path
            path = Path(file_path)

            if not path.is_absolute():
                path = Path.cwd() / path

            if not path.exists():
                return {"error": f"Test file not found: {file_path}"}

            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()

            return {
                "file_path": str(path),
                "content": content[:10000],  # Limit size
            }
        except Exception as e:
            return {"error": f"Could not read test file: {str(e)}"}

    def execute(
        self,
        framework: Optional[str] = None,
        test: Optional[str] = None,
        max_failures: int = 5,
        context_lines: int = 10,
    ) -> ToolResult:
        """Run tests and provide rich context for fixing failures."""

        # Run tests
        result = run_tests(
            framework=framework,
            specific_test=test,
            timeout=300,
        )

        # If all tests pass, we're done!
        if result.success:
            return ToolResult(
                success=True,
                output={
                    "status": "all_tests_passing",
                    "message": "All tests pass! No fixes needed.",
                    "passed": result.passed,
                    "total": result.total,
                    "framework": result.framework,
                }
            )

        # Analyze failures with rich context
        failures_with_context = []

        for _i, failure in enumerate(result.failures[:max_failures]):
            failure_info = {
                "test_name": failure.test_name,
                "error_type": failure.error_type,
                "error_message": failure.error_message,
                "stack_trace": failure.stack_trace[:2000] if failure.stack_trace else None,
            }

            # Read source file context if we have location info
            if failure.file_path and failure.line_number:
                failure_info["source_context"] = self._read_file_context(
                    failure.file_path,
                    failure.line_number,
                    context_lines,
                )

            # Try to read the test file
            if failure.file_path:
                failure_info["test_file"] = self._read_test_file(
                    failure.test_name,
                    failure.file_path,
                )

            failures_with_context.append(failure_info)

        # Build fix instructions
        fix_instructions = self._generate_fix_instructions(failures_with_context, result.framework)

        return ToolResult(
            success=True,
            output={
                "status": "failures_found",
                "message": f"Found {result.failed} failing test(s). Analyze the failures below and fix them.",
                "framework": result.framework,
                "passed": result.passed,
                "failed": result.failed,
                "total": result.total,
                "failures": failures_with_context,
                "fix_instructions": fix_instructions,
                "next_step": "Use fs.edit to fix the issues, then call test.fix again to verify.",
            }
        )

    def _generate_fix_instructions(self, failures: list, framework: str) -> str:
        """Generate clear instructions for fixing the failures."""
        instructions = []
        instructions.append("## How to Fix These Failures\n")

        for i, f in enumerate(failures, 1):
            instructions.append(f"### Failure {i}: {f['test_name']}")

            if f.get('error_type'):
                instructions.append(f"**Error Type**: {f['error_type']}")

            if f.get('error_message'):
                instructions.append(f"**Message**: {f['error_message']}")

            if f.get('source_context') and not f['source_context'].get('error'):
                ctx = f['source_context']
                instructions.append(f"\n**Location**: {ctx['file_path']}:{ctx['failing_line']}")
                instructions.append(f"\n```\n{ctx['content']}\n```")

            instructions.append("")

        instructions.append("## Next Steps")
        instructions.append("1. Use `fs.read` if you need more context from the files")
        instructions.append("2. Use `fs.edit` to fix each issue")
        instructions.append("3. Call `test.fix` again to verify the fixes worked")

        return "\n".join(instructions)


@dataclass
class TestWatchTool(Tool):
    """Watch for file changes and re-run tests automatically.

    This tool starts a watch process that monitors source files
    and re-runs tests when changes are detected. Uses native watch
    capabilities when available (pytest-watch, cargo watch, etc.).
    """

    name: str = "test.watch"
    description: str = "Watch for file changes and re-run tests automatically"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("framework", str, "Test framework (auto-detect if not specified)", required=False),
        ToolParam("test", str, "Specific test or test file to watch", required=False),
    ])

    def execute(
        self,
        framework: Optional[str] = None,
        test: Optional[str] = None,
    ) -> ToolResult:
        """Return the watch command to run (actual watching is interactive)."""
        cwd = os.getcwd()

        if not framework:
            framework = detect_test_framework(cwd)

        if not framework:
            return ToolResult(
                success=False,
                output=None,
                error="Could not detect test framework. Supported: pytest, cargo, go, jest, vitest"
            )

        # Watch commands by framework
        watch_commands = {
            "pytest": "ptw" if test is None else f"ptw -- {test}",
            "pytest_fallback": f"python -m pytest_watch {'-- ' + test if test else ''}",
            "cargo": "cargo watch -x test" if test is None else f"cargo watch -x 'test {test}'",
            "go": "go test -v ./..." if test is None else f"go test -v -run {test} ./...",  # No native watch, suggest nodemon
            "jest": "npx jest --watch" if test is None else f"npx jest --watch {test}",
            "vitest": "npx vitest" if test is None else f"npx vitest {test}",
        }

        command = watch_commands.get(framework)
        if not command:
            return ToolResult(
                success=False,
                output=None,
                error=f"Watch mode not configured for framework: {framework}"
            )

        # Check if watch tool is available
        install_hints = {
            "pytest": "pip install pytest-watch",
            "cargo": "cargo install cargo-watch",
            "go": "# Go doesn't have built-in watch. Use: go install github.com/cespare/reflex@latest",
            "jest": "Jest has built-in watch mode",
            "vitest": "Vitest has built-in watch mode",
        }

        return ToolResult(
            success=True,
            output={
                "framework": framework,
                "command": command,
                "install_hint": install_hints.get(framework, ""),
                "instructions": f"Run the following command in your terminal:\n\n  {command}\n\nThis will start watching for file changes and re-run tests automatically.",
            }
        )


# Create tool instances
test_run = TestRunTool()
test_failures = TestFailuresTool()
test_last = TestLastTool()
test_coverage = TestCoverageTool()
test_fix = TestFixTool()
test_watch = TestWatchTool()

# Register tools
registry.register(test_run)
registry.register(test_failures)
registry.register(test_last)
registry.register(test_coverage)
registry.register(test_fix)
registry.register(test_watch)
