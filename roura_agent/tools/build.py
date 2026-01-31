"""
Roura Agent Build Tools - Auto-detect and run builds with error parsing.

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
class BuildError:
    """A single build/compile error with parsed details."""
    file_path: str
    line_number: Optional[int] = None
    column: Optional[int] = None
    error_type: str = "error"  # error, warning, note
    error_code: Optional[str] = None
    message: str = ""
    context: str = ""  # surrounding code

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
        }


@dataclass
class BuildResult:
    """Result of running a build."""
    build_system: str
    success: bool = True
    errors: list[BuildError] = field(default_factory=list)
    warnings: list[BuildError] = field(default_factory=list)
    raw_output: str = ""
    command: str = ""
    duration: float = 0.0

    def to_dict(self) -> dict:
        return {
            "build_system": self.build_system,
            "success": self.success,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "command": self.command,
            "duration": self.duration,
        }


# Build system detection
BUILD_MARKERS = {
    "cargo": ["Cargo.toml"],
    "go": ["go.mod"],
    "npm": ["package.json"],
    "swift": ["Package.swift"],
    "gradle": ["build.gradle", "build.gradle.kts"],
    "maven": ["pom.xml"],
    "make": ["Makefile", "makefile"],
    "cmake": ["CMakeLists.txt"],
    "python": ["pyproject.toml", "setup.py"],
    "dotnet": ["*.csproj", "*.sln"],
}

BUILD_COMMANDS = {
    "cargo": "cargo build",
    "go": "go build ./...",
    "npm": "npm run build",
    "swift": "swift build",
    "gradle": "./gradlew build",
    "maven": "mvn compile",
    "make": "make",
    "cmake": "cmake --build .",
    "python": "python -m py_compile",
    "dotnet": "dotnet build",
}

CLEAN_COMMANDS = {
    "cargo": "cargo clean",
    "go": "go clean",
    "npm": "rm -rf node_modules dist build",
    "swift": "swift package clean",
    "gradle": "./gradlew clean",
    "maven": "mvn clean",
    "make": "make clean",
    "cmake": "cmake --build . --target clean",
    "dotnet": "dotnet clean",
}


def detect_build_system(cwd: Optional[str] = None) -> Optional[str]:
    """Auto-detect the build system based on project files."""
    root = Path(cwd) if cwd else Path.cwd()

    for system, markers in BUILD_MARKERS.items():
        for marker in markers:
            if marker.startswith("*"):
                if list(root.glob(marker)):
                    return system
            elif (root / marker).exists():
                # Special handling for package.json
                if marker == "package.json":
                    try:
                        pkg = json.loads((root / marker).read_text())
                        if "build" in pkg.get("scripts", {}):
                            return "npm"
                    except Exception:
                        pass
                else:
                    return system

    return None


def parse_rust_errors(output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse Rust compiler errors."""
    errors = []
    warnings = []

    # Pattern: error[E0308]: expected `X`, found `Y`
    #          --> src/main.rs:10:5
    pattern = r"(error|warning)(?:\[(\w+)\])?: (.+?)\n\s*-->\s*([\w/.]+):(\d+):(\d+)"

    for match in re.finditer(pattern, output, re.MULTILINE):
        error_type = match.group(1)
        error_code = match.group(2)
        message = match.group(3).strip()
        file_path = match.group(4)
        line = int(match.group(5))
        col = int(match.group(6))

        error = BuildError(
            file_path=file_path,
            line_number=line,
            column=col,
            error_type=error_type,
            error_code=error_code,
            message=message,
        )

        if error_type == "error":
            errors.append(error)
        else:
            warnings.append(error)

    return errors, warnings


def parse_go_errors(output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse Go compiler errors."""
    errors = []
    warnings = []

    # Pattern: ./main.go:10:5: error message
    pattern = r"\./([\w/.]+):(\d+):(\d+): (.+)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        message = match.group(4).strip()

        errors.append(BuildError(
            file_path=file_path,
            line_number=line,
            column=col,
            error_type="error",
            message=message,
        ))

    return errors, warnings


def parse_typescript_errors(output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse TypeScript compiler errors."""
    errors = []
    warnings = []

    # Pattern: src/index.ts(10,5): error TS2322: Type 'X' is not assignable to type 'Y'
    pattern = r"([\w/.]+)\((\d+),(\d+)\): (error|warning) (TS\d+): (.+)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        error_type = match.group(4)
        error_code = match.group(5)
        message = match.group(6).strip()

        error = BuildError(
            file_path=file_path,
            line_number=line,
            column=col,
            error_type=error_type,
            error_code=error_code,
            message=message,
        )

        if error_type == "error":
            errors.append(error)
        else:
            warnings.append(error)

    return errors, warnings


def parse_swift_errors(output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse Swift compiler errors."""
    errors = []
    warnings = []

    # Pattern: /path/to/file.swift:10:5: error: message
    pattern = r"([\w/.]+\.swift):(\d+):(\d+): (error|warning|note): (.+)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        error_type = match.group(4)
        message = match.group(5).strip()

        error = BuildError(
            file_path=file_path,
            line_number=line,
            column=col,
            error_type=error_type,
            message=message,
        )

        if error_type == "error":
            errors.append(error)
        elif error_type == "warning":
            warnings.append(error)

    return errors, warnings


def parse_gcc_clang_errors(output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse GCC/Clang compiler errors."""
    errors = []
    warnings = []

    # Pattern: file.c:10:5: error: message
    pattern = r"([\w/.]+\.[ch](?:pp)?):(\d+):(\d+): (error|warning): (.+)"

    for match in re.finditer(pattern, output):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3))
        error_type = match.group(4)
        message = match.group(5).strip()

        error = BuildError(
            file_path=file_path,
            line_number=line,
            column=col,
            error_type=error_type,
            message=message,
        )

        if error_type == "error":
            errors.append(error)
        else:
            warnings.append(error)

    return errors, warnings


def parse_python_errors(output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse Python syntax/import errors."""
    errors = []
    warnings = []

    # Pattern: File "path/to/file.py", line 10
    #            SyntaxError: invalid syntax
    file_pattern = r'File "([^"]+)", line (\d+)'
    error_pattern = r"(SyntaxError|IndentationError|ImportError|ModuleNotFoundError): (.+)"

    file_matches = list(re.finditer(file_pattern, output))
    error_matches = list(re.finditer(error_pattern, output))

    for i, file_match in enumerate(file_matches):
        file_path = file_match.group(1)
        line = int(file_match.group(2))

        message = ""
        error_type_name = "SyntaxError"
        if i < len(error_matches):
            error_type_name = error_matches[i].group(1)
            message = error_matches[i].group(2)

        errors.append(BuildError(
            file_path=file_path,
            line_number=line,
            error_type="error",
            error_code=error_type_name,
            message=message,
        ))

    return errors, warnings


def parse_build_output(build_system: str, output: str) -> tuple[list[BuildError], list[BuildError]]:
    """Parse build output based on build system."""
    parsers = {
        "cargo": parse_rust_errors,
        "go": parse_go_errors,
        "npm": parse_typescript_errors,
        "swift": parse_swift_errors,
        "make": parse_gcc_clang_errors,
        "cmake": parse_gcc_clang_errors,
        "python": parse_python_errors,
    }

    parser = parsers.get(build_system)
    if parser:
        return parser(output)

    return [], []


def run_build(
    build_system: Optional[str] = None,
    release: bool = False,
    cwd: Optional[str] = None,
    timeout: int = 600,
) -> BuildResult:
    """Run build and return parsed results."""
    import time

    working_dir = cwd or os.getcwd()

    if not build_system:
        build_system = detect_build_system(working_dir)
        if not build_system:
            return BuildResult(
                build_system="unknown",
                success=False,
                raw_output="Could not detect build system. Supported: cargo, go, npm, swift, gradle, maven, make, cmake"
            )

    command = BUILD_COMMANDS.get(build_system, "")
    if not command:
        return BuildResult(
            build_system=build_system,
            success=False,
            raw_output=f"No build command configured for: {build_system}"
        )

    # Add release flag if applicable
    if release:
        if build_system == "cargo":
            command = "cargo build --release"
        elif build_system == "go":
            command = "go build -ldflags='-s -w' ./..."

    start_time = time.time()

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        duration = time.time() - start_time
        output = proc.stdout + "\n" + proc.stderr

        errors, warnings = parse_build_output(build_system, output)

        return BuildResult(
            build_system=build_system,
            success=proc.returncode == 0,
            errors=errors,
            warnings=warnings,
            raw_output=output,
            command=command,
            duration=duration,
        )

    except subprocess.TimeoutExpired:
        return BuildResult(
            build_system=build_system,
            success=False,
            command=command,
            raw_output=f"Build timed out after {timeout} seconds"
        )
    except Exception as e:
        return BuildResult(
            build_system=build_system,
            success=False,
            command=command,
            raw_output=f"Error running build: {str(e)}"
        )


# ============= TOOL IMPLEMENTATIONS =============


@dataclass
class BuildRunTool(Tool):
    """Run the project's build."""

    name: str = "build.run"
    description: str = "Auto-detect and run the project build (cargo, go, npm, swift, gradle, etc.)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("build_system", str, "Build system (auto-detect if not specified)", required=False),
        ToolParam("release", bool, "Build in release mode", required=False, default=False),
        ToolParam("timeout", int, "Timeout in seconds (default 600)", required=False, default=600),
    ])

    def execute(
        self,
        build_system: Optional[str] = None,
        release: bool = False,
        timeout: int = 600,
    ) -> ToolResult:
        result = run_build(
            build_system=build_system,
            release=release,
            timeout=timeout,
        )

        return ToolResult(
            success=True,
            output={
                "build_success": result.success,
                "build_system": result.build_system,
                "error_count": len(result.errors),
                "warning_count": len(result.warnings),
                "errors": [e.to_dict() for e in result.errors],
                "warnings": [w.to_dict() for w in result.warnings[:10]],  # Limit warnings
                "command": result.command,
                "duration": round(result.duration, 2),
                "raw_output": result.raw_output[:5000] if len(result.raw_output) > 5000 else result.raw_output,
            }
        )


@dataclass
class BuildErrorsTool(Tool):
    """Get detailed build errors."""

    name: str = "build.errors"
    description: str = "Run build and return only errors with file locations and messages"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("build_system", str, "Build system (auto-detect if not specified)", required=False),
    ])

    def execute(self, build_system: Optional[str] = None) -> ToolResult:
        result = run_build(build_system=build_system)

        if result.success:
            return ToolResult(
                success=True,
                output={
                    "status": "build_success",
                    "warning_count": len(result.warnings),
                }
            )

        return ToolResult(
            success=True,
            output={
                "status": "build_failed",
                "error_count": len(result.errors),
                "errors": [e.to_dict() for e in result.errors],
            }
        )


@dataclass
class BuildCleanTool(Tool):
    """Clean build artifacts."""

    name: str = "build.clean"
    description: str = "Clean build artifacts for the detected build system"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("build_system", str, "Build system (auto-detect if not specified)", required=False),
    ])

    def execute(self, build_system: Optional[str] = None) -> ToolResult:
        cwd = os.getcwd()

        if not build_system:
            build_system = detect_build_system(cwd)

        if not build_system:
            return ToolResult(success=False, error="Could not detect build system")

        command = CLEAN_COMMANDS.get(build_system)
        if not command:
            return ToolResult(success=False, error=f"No clean command for: {build_system}")

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            return ToolResult(
                success=proc.returncode == 0,
                output={
                    "command": command,
                    "output": proc.stdout + proc.stderr,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def preview(self, build_system: Optional[str] = None) -> dict:
        cwd = os.getcwd()
        if not build_system:
            build_system = detect_build_system(cwd)

        command = CLEAN_COMMANDS.get(build_system, "unknown")
        return {
            "command": command,
            "build_system": build_system,
        }


@dataclass
class BuildFixTool(Tool):
    """
    Autonomous build error fixing.

    Runs build, analyzes errors, reads source files, and provides
    everything needed for the LLM to fix compilation errors.
    """

    name: str = "build.fix"
    description: str = "Run build, analyze errors, and provide context for autonomous fixing. Returns build errors with source code context."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("build_system", str, "Build system (auto-detect if not specified)", required=False),
        ToolParam("max_errors", int, "Maximum errors to analyze (default 10)", required=False, default=10),
        ToolParam("context_lines", int, "Lines of context around error (default 10)", required=False, default=10),
    ])

    def _read_file_context(self, file_path: str, line_number: int, context_lines: int = 10) -> dict:
        """Read source file with context around the error line."""
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
                "error_line": line_number,
                "content": "\n".join(context),
                "full_file": "".join(lines) if total_lines < 500 else None,
            }
        except Exception as e:
            return {"error": f"Could not read file: {str(e)}"}

    def execute(
        self,
        build_system: Optional[str] = None,
        max_errors: int = 10,
        context_lines: int = 10,
    ) -> ToolResult:
        """Run build and provide rich context for fixing errors."""

        # Run build
        result = run_build(
            build_system=build_system,
            timeout=600,
        )

        # If build succeeds, we're done!
        if result.success:
            return ToolResult(
                success=True,
                output={
                    "status": "build_successful",
                    "message": "Build succeeded! No fixes needed.",
                    "build_system": result.build_system,
                    "warning_count": len(result.warnings),
                    "duration": round(result.duration, 2),
                }
            )

        # Analyze errors with rich context
        errors_with_context = []

        for _i, error in enumerate(result.errors[:max_errors]):
            error_info = {
                "file_path": error.file_path,
                "line_number": error.line_number,
                "column": error.column,
                "error_type": error.error_type,
                "error_code": error.error_code,
                "message": error.message,
            }

            # Read source file context if we have location info
            if error.file_path and error.line_number:
                error_info["source_context"] = self._read_file_context(
                    error.file_path,
                    error.line_number,
                    context_lines,
                )

            errors_with_context.append(error_info)

        # Build fix instructions
        fix_instructions = self._generate_fix_instructions(errors_with_context, result.build_system)

        return ToolResult(
            success=True,
            output={
                "status": "build_failed",
                "message": f"Build failed with {len(result.errors)} error(s). Analyze the errors below and fix them.",
                "build_system": result.build_system,
                "error_count": len(result.errors),
                "warning_count": len(result.warnings),
                "errors": errors_with_context,
                "fix_instructions": fix_instructions,
                "next_step": "Use fs.edit to fix the issues, then call build.fix again to verify.",
            }
        )

    def _generate_fix_instructions(self, errors: list, build_system: str) -> str:
        """Generate clear instructions for fixing the errors."""
        instructions = []
        instructions.append(f"## How to Fix These {build_system.title()} Build Errors\n")

        for i, e in enumerate(errors, 1):
            instructions.append(f"### Error {i}: {e['file_path']}:{e.get('line_number', '?')}")

            if e.get('error_code'):
                instructions.append(f"**Error Code**: {e['error_code']}")

            if e.get('message'):
                instructions.append(f"**Message**: {e['message']}")

            if e.get('source_context') and not e['source_context'].get('error'):
                ctx = e['source_context']
                instructions.append(f"\n```\n{ctx['content']}\n```")

            instructions.append("")

        instructions.append("## Next Steps")
        instructions.append("1. Use `fs.read` if you need more context from the files")
        instructions.append("2. Use `fs.edit` to fix each error")
        instructions.append("3. Call `build.fix` again to verify the fixes worked")

        return "\n".join(instructions)


@dataclass
class BuildWatchTool(Tool):
    """Watch for file changes and re-build automatically.

    This tool provides commands to start a watch process that monitors
    source files and triggers builds when changes are detected. Uses
    native watch capabilities when available (cargo watch, nodemon, etc.).
    """

    name: str = "build.watch"
    description: str = "Watch for file changes and re-build automatically"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("build_system", str, "Build system (auto-detect if not specified)", required=False),
    ])

    def execute(self, build_system: Optional[str] = None) -> ToolResult:
        """Return the watch command to run (actual watching is interactive)."""
        cwd = os.getcwd()

        if not build_system:
            build_system = detect_build_system(cwd)

        if not build_system:
            return ToolResult(
                success=False,
                output=None,
                error="Could not detect build system. Supported: cargo, go, npm, swift, gradle, maven, make, cmake"
            )

        # Watch commands by build system
        watch_commands = {
            "cargo": "cargo watch -x build",
            "go": "reflex -r '\\.go$' -- go build ./...",  # Requires reflex
            "npm": "npm run watch",  # Assumes watch script exists
            "swift": "swift build",  # No native watch, suggest fswatch
            "gradle": "./gradlew build --continuous",
            "maven": "mvn fizzed-watcher:run",  # Requires watcher plugin
            "make": "fswatch -o . | xargs -n1 make",  # Requires fswatch
            "cmake": "cmake --build . --target all",  # No native watch
        }

        command = watch_commands.get(build_system)
        if not command:
            return ToolResult(
                success=False,
                output=None,
                error=f"Watch mode not configured for build system: {build_system}"
            )

        # Installation hints for watch tools
        install_hints = {
            "cargo": "cargo install cargo-watch",
            "go": "go install github.com/cespare/reflex@latest",
            "npm": "Ensure 'watch' script is defined in package.json, or use: npm install -g nodemon",
            "swift": "brew install fswatch",
            "gradle": "Built-in with --continuous flag",
            "maven": "Add fizzed-watcher-maven-plugin to pom.xml",
            "make": "brew install fswatch",
            "cmake": "Consider using cmake --build with fswatch",
        }

        return ToolResult(
            success=True,
            output={
                "build_system": build_system,
                "command": command,
                "install_hint": install_hints.get(build_system, ""),
                "instructions": f"Run the following command in your terminal:\n\n  {command}\n\nThis will start watching for file changes and re-build automatically.",
            }
        )


# Create tool instances
build_run = BuildRunTool()
build_errors = BuildErrorsTool()
build_clean = BuildCleanTool()
build_fix = BuildFixTool()
build_watch = BuildWatchTool()

# Register tools
registry.register(build_run)
registry.register(build_errors)
registry.register(build_clean)
registry.register(build_fix)
registry.register(build_watch)
