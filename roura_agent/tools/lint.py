"""
Roura Agent Lint & Format Tools - Auto-detect and run linters/formatters.

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

from .base import Tool, RiskLevel, ToolResult, ToolParam, registry


@dataclass
class LintIssue:
    """A single lint issue."""
    file_path: str
    line_number: Optional[int] = None
    column: Optional[int] = None
    rule: Optional[str] = None
    severity: str = "warning"  # error, warning, info
    message: str = ""
    fixable: bool = False

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "fixable": self.fixable,
        }


@dataclass
class LintResult:
    """Result of running a linter."""
    linter: str
    success: bool = True
    issues: list[LintIssue] = field(default_factory=list)
    fixed_count: int = 0
    raw_output: str = ""
    command: str = ""

    def to_dict(self) -> dict:
        return {
            "linter": self.linter,
            "success": self.success,
            "issue_count": len(self.issues),
            "error_count": len([i for i in self.issues if i.severity == "error"]),
            "warning_count": len([i for i in self.issues if i.severity == "warning"]),
            "fixable_count": len([i for i in self.issues if i.fixable]),
            "fixed_count": self.fixed_count,
            "issues": [i.to_dict() for i in self.issues],
            "command": self.command,
        }


# Linter detection and commands
LINTER_MARKERS = {
    "ruff": ["ruff.toml", "pyproject.toml"],  # Check for [tool.ruff]
    "eslint": [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml"],
    "prettier": [".prettierrc", ".prettierrc.js", ".prettierrc.json", "prettier.config.js"],
    "clippy": ["Cargo.toml"],
    "swiftlint": [".swiftlint.yml", ".swiftlint.yaml", "Package.swift"],
    "golangci-lint": [".golangci.yml", ".golangci.yaml", "go.mod"],
    "mypy": ["mypy.ini", "pyproject.toml"],
    "black": ["pyproject.toml"],
    "rustfmt": ["rustfmt.toml", ".rustfmt.toml", "Cargo.toml"],
}

LINT_COMMANDS = {
    "ruff": "ruff check .",
    "eslint": "npx eslint .",
    "clippy": "cargo clippy -- -D warnings",
    "swiftlint": "swiftlint lint",
    "golangci-lint": "golangci-lint run",
    "mypy": "mypy .",
}

LINT_FIX_COMMANDS = {
    "ruff": "ruff check --fix .",
    "eslint": "npx eslint --fix .",
    "clippy": "cargo clippy --fix --allow-dirty",
    "swiftlint": "swiftlint lint --fix",
    "golangci-lint": "golangci-lint run --fix",
}

FORMAT_COMMANDS = {
    "black": "black .",
    "prettier": "npx prettier --write .",
    "rustfmt": "cargo fmt",
    "gofmt": "gofmt -w .",
    "swift-format": "swift-format -i -r .",
    "ruff": "ruff format .",
}

FORMAT_CHECK_COMMANDS = {
    "black": "black --check .",
    "prettier": "npx prettier --check .",
    "rustfmt": "cargo fmt --check",
    "gofmt": "gofmt -l .",
    "swift-format": "swift-format -r . 2>&1",
    "ruff": "ruff format --check .",
}

TYPECHECK_COMMANDS = {
    "mypy": "mypy .",
    "pyright": "pyright",
    "tsc": "npx tsc --noEmit",
}


def detect_linter(cwd: Optional[str] = None) -> Optional[str]:
    """Auto-detect the linter based on project files."""
    root = Path(cwd) if cwd else Path.cwd()

    # Check for config files
    for linter, markers in LINTER_MARKERS.items():
        for marker in markers:
            if (root / marker).exists():
                # Special handling for pyproject.toml
                if marker == "pyproject.toml":
                    try:
                        content = (root / marker).read_text()
                        if linter == "ruff" and "[tool.ruff" in content:
                            return "ruff"
                        elif linter == "mypy" and "[tool.mypy" in content:
                            return "mypy"
                        elif linter == "black" and "[tool.black" in content:
                            return "black"
                    except Exception:
                        pass
                else:
                    return linter

    # Fallback based on project type
    if (root / "Cargo.toml").exists():
        return "clippy"
    if (root / "go.mod").exists():
        return "golangci-lint"
    if (root / "package.json").exists():
        return "eslint"
    if (root / "Package.swift").exists():
        return "swiftlint"
    if list(root.glob("*.py")) or (root / "pyproject.toml").exists():
        return "ruff"

    return None


def detect_formatter(cwd: Optional[str] = None) -> Optional[str]:
    """Auto-detect the formatter based on project files."""
    root = Path(cwd) if cwd else Path.cwd()

    # Check for config files
    if (root / ".prettierrc").exists() or (root / "prettier.config.js").exists():
        return "prettier"

    if (root / "pyproject.toml").exists():
        try:
            content = (root / "pyproject.toml").read_text()
            if "[tool.ruff.format" in content or "[tool.ruff]" in content:
                return "ruff"
            if "[tool.black" in content:
                return "black"
        except Exception:
            pass

    # Fallback based on project type
    if (root / "Cargo.toml").exists():
        return "rustfmt"
    if (root / "go.mod").exists():
        return "gofmt"
    if (root / "Package.swift").exists():
        return "swift-format"
    if list(root.glob("*.py")):
        return "ruff"
    if (root / "package.json").exists():
        return "prettier"

    return None


def detect_typechecker(cwd: Optional[str] = None) -> Optional[str]:
    """Auto-detect the type checker based on project files."""
    root = Path(cwd) if cwd else Path.cwd()

    # TypeScript
    if (root / "tsconfig.json").exists():
        return "tsc"

    # Python
    if (root / "pyrightconfig.json").exists():
        return "pyright"
    if (root / "mypy.ini").exists():
        return "mypy"
    if (root / "pyproject.toml").exists():
        try:
            content = (root / "pyproject.toml").read_text()
            if "[tool.pyright" in content:
                return "pyright"
            if "[tool.mypy" in content:
                return "mypy"
        except Exception:
            pass

    return None


def parse_ruff_output(output: str) -> list[LintIssue]:
    """Parse ruff output."""
    issues = []

    # Pattern: path/to/file.py:10:5: E501 Line too long
    pattern = r"([^\s:]+):(\d+):(\d+): (\w+) (.+)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        rule = match.group(4)
        message = match.group(5)

        # Determine severity from rule
        severity = "error" if rule.startswith("E") or rule.startswith("F") else "warning"

        issues.append(LintIssue(
            file_path=file_path,
            line_number=line,
            column=col,
            rule=rule,
            severity=severity,
            message=message,
            fixable=True,  # Most ruff issues are fixable
        ))

    return issues


def parse_eslint_output(output: str) -> list[LintIssue]:
    """Parse ESLint output."""
    issues = []

    # Pattern: /path/to/file.js
    #   10:5  error  message  rule-name
    current_file = None
    file_pattern = r"^(/[^\s]+\.[jt]sx?)$"
    issue_pattern = r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.+?)\s+(\S+)$"

    for line in output.split("\n"):
        file_match = re.match(file_pattern, line)
        if file_match:
            current_file = file_match.group(1)
            continue

        if current_file:
            issue_match = re.match(issue_pattern, line)
            if issue_match:
                issues.append(LintIssue(
                    file_path=current_file,
                    line_number=int(issue_match.group(1)),
                    column=int(issue_match.group(2)),
                    severity=issue_match.group(3),
                    message=issue_match.group(4),
                    rule=issue_match.group(5),
                    fixable=True,
                ))

    return issues


def parse_clippy_output(output: str) -> list[LintIssue]:
    """Parse Clippy output."""
    issues = []

    # Pattern: warning: message
    #    --> src/main.rs:10:5
    pattern = r"(warning|error)(?:\[(\w+)\])?: (.+?)\n\s*-->\s*([\w/.]+):(\d+):(\d+)"

    for match in re.finditer(pattern, output, re.MULTILINE):
        severity = match.group(1)
        rule = match.group(2)
        message = match.group(3).strip()
        file_path = match.group(4)
        line = int(match.group(5))
        col = int(match.group(6))

        issues.append(LintIssue(
            file_path=file_path,
            line_number=line,
            column=col,
            rule=rule,
            severity=severity,
            message=message,
            fixable="help:" in output,  # Clippy provides help for fixable issues
        ))

    return issues


def parse_golangci_output(output: str) -> list[LintIssue]:
    """Parse golangci-lint output."""
    issues = []

    # Pattern: path/to/file.go:10:5: message (linter-name)
    pattern = r"([\w/.]+\.go):(\d+):(\d+): (.+?) \((\w+)\)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        message = match.group(4)
        rule = match.group(5)

        issues.append(LintIssue(
            file_path=file_path,
            line_number=line,
            column=col,
            rule=rule,
            severity="warning",
            message=message,
        ))

    return issues


def parse_swiftlint_output(output: str) -> list[LintIssue]:
    """Parse SwiftLint output."""
    issues = []

    # Pattern: /path/to/file.swift:10:5: warning: message (rule_name)
    pattern = r"([\w/.]+\.swift):(\d+):(\d+): (warning|error): (.+?) \((\w+)\)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        severity = match.group(4)
        message = match.group(5)
        rule = match.group(6)

        issues.append(LintIssue(
            file_path=file_path,
            line_number=line,
            column=col,
            rule=rule,
            severity=severity,
            message=message,
        ))

    return issues


def parse_lint_output(linter: str, output: str) -> list[LintIssue]:
    """Parse lint output based on linter."""
    parsers = {
        "ruff": parse_ruff_output,
        "eslint": parse_eslint_output,
        "clippy": parse_clippy_output,
        "golangci-lint": parse_golangci_output,
        "swiftlint": parse_swiftlint_output,
    }

    parser = parsers.get(linter)
    if parser:
        return parser(output)

    return []


def run_lint(
    linter: Optional[str] = None,
    fix: bool = False,
    cwd: Optional[str] = None,
    timeout: int = 300,
) -> LintResult:
    """Run linter and return parsed results."""
    working_dir = cwd or os.getcwd()

    if not linter:
        linter = detect_linter(working_dir)
        if not linter:
            return LintResult(
                linter="unknown",
                success=False,
                raw_output="Could not detect linter. Supported: ruff, eslint, clippy, swiftlint, golangci-lint"
            )

    commands = LINT_FIX_COMMANDS if fix else LINT_COMMANDS
    command = commands.get(linter, "")

    if not command:
        return LintResult(
            linter=linter,
            success=False,
            raw_output=f"No lint command configured for: {linter}"
        )

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
        issues = parse_lint_output(linter, output)

        # Count fixed issues if fix mode
        fixed_count = 0
        if fix:
            fixed_match = re.search(r"(\d+)\s+(?:fix|fixed)", output, re.IGNORECASE)
            if fixed_match:
                fixed_count = int(fixed_match.group(1))

        return LintResult(
            linter=linter,
            success=proc.returncode == 0 or len(issues) == 0,
            issues=issues,
            fixed_count=fixed_count,
            raw_output=output,
            command=command,
        )

    except subprocess.TimeoutExpired:
        return LintResult(
            linter=linter,
            success=False,
            command=command,
            raw_output=f"Linter timed out after {timeout} seconds"
        )
    except Exception as e:
        return LintResult(
            linter=linter,
            success=False,
            command=command,
            raw_output=f"Error running linter: {str(e)}"
        )


# ============= TOOL IMPLEMENTATIONS =============


@dataclass
class LintRunTool(Tool):
    """Run the project's linter."""

    name: str = "lint.run"
    description: str = "Auto-detect and run the project linter (ruff, eslint, clippy, swiftlint, golangci-lint)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("linter", str, "Linter to use (auto-detect if not specified)", required=False),
        ToolParam("timeout", int, "Timeout in seconds (default 300)", required=False, default=300),
    ])

    def execute(
        self,
        linter: Optional[str] = None,
        timeout: int = 300,
    ) -> ToolResult:
        result = run_lint(linter=linter, fix=False, timeout=timeout)

        return ToolResult(
            success=True,
            output=result.to_dict(),
        )


@dataclass
class LintFixTool(Tool):
    """Run linter with auto-fix."""

    name: str = "lint.fix"
    description: str = "Run linter with auto-fix enabled"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("linter", str, "Linter to use (auto-detect if not specified)", required=False),
    ])

    def execute(self, linter: Optional[str] = None) -> ToolResult:
        result = run_lint(linter=linter, fix=True)

        return ToolResult(
            success=True,
            output=result.to_dict(),
        )

    def preview(self, linter: Optional[str] = None) -> dict:
        if not linter:
            linter = detect_linter()

        command = LINT_FIX_COMMANDS.get(linter, "unknown")
        return {
            "linter": linter,
            "command": command,
        }


@dataclass
class FormatRunTool(Tool):
    """Run code formatter."""

    name: str = "format.run"
    description: str = "Auto-detect and run code formatter (black, prettier, rustfmt, gofmt, swift-format, ruff)"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("formatter", str, "Formatter to use (auto-detect if not specified)", required=False),
    ])

    def execute(self, formatter: Optional[str] = None) -> ToolResult:
        cwd = os.getcwd()

        if not formatter:
            formatter = detect_formatter(cwd)

        if not formatter:
            return ToolResult(
                success=False,
                error="Could not detect formatter. Supported: black, prettier, rustfmt, gofmt, swift-format, ruff"
            )

        command = FORMAT_COMMANDS.get(formatter)
        if not command:
            return ToolResult(success=False, error=f"No format command for: {formatter}")

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = proc.stdout + "\n" + proc.stderr

            # Count files formatted
            files_formatted = 0
            if formatter in ("black", "ruff"):
                match = re.search(r"(\d+) files? (reformatted|would be reformatted)", output)
                if match:
                    files_formatted = int(match.group(1))
            elif formatter == "prettier":
                files_formatted = output.count("\n")

            return ToolResult(
                success=proc.returncode == 0,
                output={
                    "formatter": formatter,
                    "command": command,
                    "files_formatted": files_formatted,
                    "output": output[:2000],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def preview(self, formatter: Optional[str] = None) -> dict:
        if not formatter:
            formatter = detect_formatter()

        command = FORMAT_COMMANDS.get(formatter, "unknown")
        return {
            "formatter": formatter,
            "command": command,
        }


@dataclass
class FormatCheckTool(Tool):
    """Check code formatting without modifying files."""

    name: str = "format.check"
    description: str = "Check if code is formatted correctly without making changes"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("formatter", str, "Formatter to use (auto-detect if not specified)", required=False),
    ])

    def execute(self, formatter: Optional[str] = None) -> ToolResult:
        cwd = os.getcwd()

        if not formatter:
            formatter = detect_formatter(cwd)

        if not formatter:
            return ToolResult(
                success=False,
                error="Could not detect formatter"
            )

        command = FORMAT_CHECK_COMMANDS.get(formatter)
        if not command:
            return ToolResult(success=False, error=f"No check command for: {formatter}")

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = proc.stdout + "\n" + proc.stderr

            return ToolResult(
                success=True,
                output={
                    "formatter": formatter,
                    "formatted": proc.returncode == 0,
                    "command": command,
                    "output": output[:2000],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@dataclass
class TypecheckRunTool(Tool):
    """Run type checker."""

    name: str = "typecheck.run"
    description: str = "Auto-detect and run type checker (mypy, pyright, tsc)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("typechecker", str, "Type checker to use (auto-detect if not specified)", required=False),
    ])

    def execute(self, typechecker: Optional[str] = None) -> ToolResult:
        cwd = os.getcwd()

        if not typechecker:
            typechecker = detect_typechecker(cwd)

        if not typechecker:
            return ToolResult(
                success=False,
                error="Could not detect type checker. Supported: mypy, pyright, tsc"
            )

        command = TYPECHECK_COMMANDS.get(typechecker)
        if not command:
            return ToolResult(success=False, error=f"No typecheck command for: {typechecker}")

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

            # Count errors
            error_count = 0
            if typechecker in ("mypy", "pyright"):
                error_match = re.search(r"(\d+) errors?", output)
                if error_match:
                    error_count = int(error_match.group(1))
            elif typechecker == "tsc":
                error_count = output.count("error TS")

            return ToolResult(
                success=True,
                output={
                    "typechecker": typechecker,
                    "success": proc.returncode == 0,
                    "error_count": error_count,
                    "command": command,
                    "output": output[:5000],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


@dataclass
class TypeError:
    """Parsed type error."""
    file_path: str
    line_number: int
    column: Optional[int] = None
    error_code: Optional[str] = None
    message: str = ""
    severity: str = "error"

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "error_code": self.error_code,
            "message": self.message,
            "severity": self.severity,
        }


def parse_mypy_errors(output: str) -> list[TypeError]:
    """Parse mypy output into structured errors."""
    errors = []

    # Pattern: path/to/file.py:10:5: error: message [error-code]
    pattern = r"([^\s:]+):(\d+)(?::(\d+))?: (error|warning|note): (.+?)(?:\s+\[(\w+(?:-\w+)*)\])?$"

    for line in output.split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            errors.append(TypeError(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                column=int(match.group(3)) if match.group(3) else None,
                severity=match.group(4),
                message=match.group(5),
                error_code=match.group(6),
            ))

    return errors


def parse_pyright_errors(output: str) -> list[TypeError]:
    """Parse pyright output into structured errors."""
    errors = []

    # Pattern: path/to/file.py:10:5 - error: message
    pattern = r"([^\s:]+):(\d+):(\d+)\s+-\s+(error|warning|information):\s+(.+)"

    for line in output.split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            errors.append(TypeError(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                column=int(match.group(3)),
                severity=match.group(4),
                message=match.group(5),
            ))

    return errors


def parse_tsc_errors(output: str) -> list[TypeError]:
    """Parse TypeScript tsc output into structured errors."""
    errors = []

    # Pattern: path/to/file.ts(10,5): error TS2345: message
    pattern = r"([^\s(]+)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)"

    for line in output.split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            errors.append(TypeError(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                column=int(match.group(3)),
                severity=match.group(4),
                error_code=match.group(5),
                message=match.group(6),
            ))

    return errors


def parse_typecheck_errors(typechecker: str, output: str) -> list[TypeError]:
    """Parse typecheck output based on typechecker."""
    parsers = {
        "mypy": parse_mypy_errors,
        "pyright": parse_pyright_errors,
        "tsc": parse_tsc_errors,
    }

    parser = parsers.get(typechecker)
    if parser:
        return parser(output)

    return []


@dataclass
class TypecheckFixTool(Tool):
    """THE KILLER FEATURE: Autonomous type error fixing.

    This tool runs the type checker, parses errors, reads source context,
    and returns everything needed for autonomous fixing.
    """

    name: str = "typecheck.fix"
    description: str = "Run type checker, analyze errors, and provide context for autonomous fixing."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("typechecker", str, "Type checker to use (auto-detect if not specified)", required=False),
        ToolParam("max_errors", int, "Maximum errors to analyze (default 10)", required=False, default=10),
        ToolParam("context_lines", int, "Lines of context around error (default 5)", required=False, default=5),
    ])

    def _read_file_context(self, file_path: str, line_number: int, context_lines: int = 5) -> dict:
        """Read source file with context around error line."""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"error": f"File not found: {file_path}"}

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)
            start = max(0, line_number - context_lines - 1)
            end = min(total_lines, line_number + context_lines)

            context = []
            for i, line in enumerate(all_lines[start:end], start=start + 1):
                marker = ">>> " if i == line_number else "    "
                context.append(f"{marker}{i:4d}| {line.rstrip()}")

            return {
                "file_path": str(path.resolve()),
                "total_lines": total_lines,
                "start_line": start + 1,
                "end_line": end,
                "error_line": line_number,
                "context": "\n".join(context),
            }
        except Exception as e:
            return {"error": str(e)}

    def execute(
        self,
        typechecker: Optional[str] = None,
        max_errors: int = 10,
        context_lines: int = 5,
    ) -> ToolResult:
        """Run type checker and provide fix context."""
        cwd = os.getcwd()

        if not typechecker:
            typechecker = detect_typechecker(cwd)

        if not typechecker:
            return ToolResult(
                success=False,
                error="Could not detect type checker. Supported: mypy, pyright, tsc"
            )

        command = TYPECHECK_COMMANDS.get(typechecker)
        if not command:
            return ToolResult(success=False, error=f"No typecheck command for: {typechecker}")

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

            # Parse errors
            errors = parse_typecheck_errors(typechecker, output)

            if not errors:
                return ToolResult(
                    success=True,
                    output={
                        "typechecker": typechecker,
                        "command": command,
                        "status": "passing",
                        "error_count": 0,
                        "errors": [],
                        "fix_instructions": "No type errors found. All checks pass!",
                    }
                )

            # Limit errors to analyze
            errors_to_fix = errors[:max_errors]

            # Build fix context for each error
            errors_with_context = []
            for error in errors_to_fix:
                context = self._read_file_context(
                    error.file_path,
                    error.line_number,
                    context_lines,
                )

                errors_with_context.append({
                    **error.to_dict(),
                    "source_context": context,
                })

            # Generate fix instructions
            instructions = self._generate_fix_instructions(typechecker, errors_with_context)

            return ToolResult(
                success=True,
                output={
                    "typechecker": typechecker,
                    "command": command,
                    "status": "failing",
                    "total_errors": len(errors),
                    "errors_analyzed": len(errors_to_fix),
                    "errors": errors_with_context,
                    "fix_instructions": instructions,
                }
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Type checker timed out after 300 seconds"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Error running type checker: {str(e)}"
            )

    def _generate_fix_instructions(self, typechecker: str, errors: list[dict]) -> str:
        """Generate instructions for fixing type errors."""
        instructions = [
            f"## Type Errors Found ({len(errors)} errors)",
            "",
            "To fix these errors, use the fs.edit tool to make the following corrections:",
            "",
        ]

        for i, error in enumerate(errors, 1):
            file_path = error["file_path"]
            line = error["line_number"]
            message = error["message"]
            error_code = error.get("error_code", "")

            instructions.append(f"### Error {i}: {file_path}:{line}")
            if error_code:
                instructions.append(f"**Code**: {error_code}")
            instructions.append(f"**Message**: {message}")
            instructions.append("")

            context = error.get("source_context", {})
            if "context" in context:
                instructions.append("**Source context**:")
                instructions.append("```")
                instructions.append(context["context"])
                instructions.append("```")
                instructions.append("")

            # Add type-specific hints
            if typechecker == "mypy":
                if "Incompatible types" in message:
                    instructions.append("*Hint*: Check if you need a type cast or if the function signature is wrong.")
                elif "has no attribute" in message:
                    instructions.append("*Hint*: The attribute might be missing from the class or you might need to import it.")
                elif "Missing return statement" in message:
                    instructions.append("*Hint*: Add a return statement to the function.")
                elif "Argument" in message and "expected" in message:
                    instructions.append("*Hint*: Check the function signature and ensure the correct type is passed.")

            elif typechecker == "tsc":
                if "is not assignable" in message:
                    instructions.append("*Hint*: The types don't match. Check if you need a type assertion or if the variable has the wrong type.")
                elif "does not exist" in message:
                    instructions.append("*Hint*: The property/method doesn't exist on the type. Check for typos or add it to the interface.")

            instructions.append("")

        instructions.append("After making fixes, run `typecheck.run` to verify the errors are resolved.")

        return "\n".join(instructions)


# Create tool instances
lint_run = LintRunTool()
lint_fix = LintFixTool()
format_run = FormatRunTool()
format_check = FormatCheckTool()
typecheck_run = TypecheckRunTool()
typecheck_fix = TypecheckFixTool()

# Register tools
registry.register(lint_run)
registry.register(lint_fix)
registry.register(format_run)
registry.register(format_check)
registry.register(typecheck_run)
registry.register(typecheck_fix)
