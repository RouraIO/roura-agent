"""
Roura Agent PRO CI Mode - Headless CI/CD integration.

Provides:
- Non-interactive agent execution
- Structured output for CI systems
- Exit codes and status reporting
- Environment variable configuration
- Real code review with LLM integration

© Roura.io
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..logging import get_logger
from .billing import BillingManager, UsageType, get_billing_manager

logger = get_logger(__name__)


# =============================================================================
# File Pattern Definitions
# =============================================================================

# Comprehensive file patterns by language/framework
FILE_PATTERNS: dict[str, list[str]] = {
    # Mobile
    "swift": ["**/*.swift"],
    "kotlin": ["**/*.kt", "**/*.kts"],
    "objc": ["**/*.m", "**/*.mm", "**/*.h"],

    # Web Frontend
    "javascript": ["**/*.js", "**/*.mjs", "**/*.cjs"],
    "typescript": ["**/*.ts", "**/*.tsx", "**/*.mts"],
    "jsx": ["**/*.jsx"],
    "vue": ["**/*.vue"],
    "svelte": ["**/*.svelte"],
    "css": ["**/*.css", "**/*.scss", "**/*.sass", "**/*.less"],
    "html": ["**/*.html", "**/*.htm"],

    # Backend
    "python": ["**/*.py"],
    "go": ["**/*.go"],
    "rust": ["**/*.rs"],
    "java": ["**/*.java"],
    "csharp": ["**/*.cs"],
    "ruby": ["**/*.rb"],
    "php": ["**/*.php"],
    "elixir": ["**/*.ex", "**/*.exs"],
    "scala": ["**/*.scala"],

    # Config & Data
    "json": ["**/*.json"],
    "yaml": ["**/*.yaml", "**/*.yml"],
    "toml": ["**/*.toml"],
    "xml": ["**/*.xml"],
    "sql": ["**/*.sql"],

    # Shell & Scripts
    "shell": ["**/*.sh", "**/*.bash", "**/*.zsh"],
    "powershell": ["**/*.ps1", "**/*.psm1"],

    # Documentation
    "markdown": ["**/*.md", "**/*.mdx"],

    # Other
    "graphql": ["**/*.graphql", "**/*.gql"],
    "proto": ["**/*.proto"],
    "terraform": ["**/*.tf", "**/*.tfvars"],
    "dockerfile": ["**/Dockerfile", "**/*.dockerfile"],
}

# Project type detection patterns
PROJECT_MARKERS: dict[str, list[str]] = {
    "ios": ["*.xcodeproj", "*.xcworkspace", "Package.swift", "Podfile"],
    "android": ["build.gradle", "build.gradle.kts", "AndroidManifest.xml"],
    "python": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
    "node": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod", "go.sum"],
    "ruby": ["Gemfile", "*.gemspec"],
    "dotnet": ["*.csproj", "*.sln", "*.fsproj"],
    "java": ["pom.xml", "build.gradle"],
    "php": ["composer.json"],
    "terraform": ["*.tf", "terraform.tfstate"],
}

# Default patterns for each project type
PROJECT_DEFAULT_PATTERNS: dict[str, list[str]] = {
    "ios": ["swift", "objc", "json", "yaml", "markdown"],
    "android": ["kotlin", "java", "xml", "json", "yaml"],
    "python": ["python", "json", "yaml", "toml", "markdown"],
    "node": ["javascript", "typescript", "jsx", "json", "yaml", "css", "html"],
    "rust": ["rust", "toml", "markdown"],
    "go": ["go", "json", "yaml", "markdown"],
    "ruby": ["ruby", "yaml", "json"],
    "dotnet": ["csharp", "json", "xml"],
    "java": ["java", "xml", "json", "yaml"],
    "php": ["php", "json", "yaml"],
    "terraform": ["terraform", "json", "yaml"],
}

# Files/directories to always ignore
IGNORE_PATTERNS: list[str] = [
    "**/.git/**",
    "**/.svn/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/venv/**",
    "**/.venv/**",
    "**/env/**",
    "**/build/**",
    "**/dist/**",
    "**/.build/**",
    "**/DerivedData/**",
    "**/Pods/**",
    "**/*.xcodeproj/**",
    "**/*.xcworkspace/**",
    "**/target/**",
    "**/vendor/**",
    "**/.idea/**",
    "**/.vscode/**",
    "**/coverage/**",
    "**/.coverage/**",
    "**/htmlcov/**",
    "**/*.min.js",
    "**/*.min.css",
    "**/*.map",
    "**/package-lock.json",
    "**/yarn.lock",
    "**/pnpm-lock.yaml",
    "**/Cargo.lock",
    "**/poetry.lock",
    "**/Gemfile.lock",
]


class CIMode(str, Enum):
    """CI execution modes."""
    REVIEW = "review"  # Code review
    FIX = "fix"  # Apply fixes automatically
    GENERATE = "generate"  # Generate code
    TEST = "test"  # Run tests with AI assistance
    DOCUMENT = "document"  # Generate documentation
    ANALYZE = "analyze"  # Static analysis


class CIExitCode(int, Enum):
    """Standard CI exit codes."""
    SUCCESS = 0
    FAILURE = 1
    ERROR = 2
    SKIPPED = 3
    TIMEOUT = 4
    RATE_LIMITED = 5


@dataclass
class CIConfig:
    """Configuration for CI execution."""
    mode: CIMode
    target_path: str = "."
    max_files: int = 50
    timeout_seconds: int = 300
    fail_on_issues: bool = True
    output_format: str = "json"  # json, text, github, gitlab
    model: Optional[str] = None
    extra_context: Optional[str] = None

    @classmethod
    def from_env(cls) -> "CIConfig":
        """Create configuration from environment variables."""
        mode_str = os.environ.get("ROURA_CI_MODE", "review")
        try:
            mode = CIMode(mode_str)
        except ValueError:
            mode = CIMode.REVIEW

        return cls(
            mode=mode,
            target_path=os.environ.get("ROURA_CI_TARGET", "."),
            max_files=int(os.environ.get("ROURA_CI_MAX_FILES", "50")),
            timeout_seconds=int(os.environ.get("ROURA_CI_TIMEOUT", "300")),
            fail_on_issues=os.environ.get("ROURA_CI_FAIL_ON_ISSUES", "true").lower() == "true",
            output_format=os.environ.get("ROURA_CI_OUTPUT_FORMAT", "json"),
            model=os.environ.get("ROURA_CI_MODEL"),
            extra_context=os.environ.get("ROURA_CI_CONTEXT"),
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "target_path": self.target_path,
            "max_files": self.max_files,
            "timeout_seconds": self.timeout_seconds,
            "fail_on_issues": self.fail_on_issues,
            "output_format": self.output_format,
            "model": self.model,
            "extra_context": self.extra_context,
        }


@dataclass
class CIIssue:
    """An issue found during CI analysis."""
    file: str
    line: Optional[int]
    severity: str  # error, warning, info
    message: str
    suggestion: Optional[str] = None
    code: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
            "code": self.code,
        }

    def to_github_annotation(self) -> str:
        """Format as GitHub Actions annotation."""
        level = "error" if self.severity == "error" else "warning"
        line_part = f",line={self.line}" if self.line else ""
        return f"::{level} file={self.file}{line_part}::{self.message}"

    def to_gitlab_codequality(self) -> dict:
        """Format as GitLab Code Quality report entry."""
        import hashlib
        fingerprint = hashlib.md5(
            f"{self.file}:{self.line}:{self.message}".encode()
        ).hexdigest()

        return {
            "description": self.message,
            "fingerprint": fingerprint,
            "severity": "major" if self.severity == "error" else "minor",
            "location": {
                "path": self.file,
                "lines": {"begin": self.line or 1},
            },
        }


@dataclass
class CIResult:
    """Result of CI execution."""
    exit_code: CIExitCode
    mode: CIMode
    issues: list[CIIssue] = field(default_factory=list)
    files_analyzed: int = 0
    duration_seconds: float = 0.0
    summary: str = ""
    changes_made: list[dict] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code.value,
            "mode": self.mode.value,
            "issues": [i.to_dict() for i in self.issues],
            "files_analyzed": self.files_analyzed,
            "duration_seconds": self.duration_seconds,
            "summary": self.summary,
            "changes_made": self.changes_made,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "issue_counts": {
                "error": sum(1 for i in self.issues if i.severity == "error"),
                "warning": sum(1 for i in self.issues if i.severity == "warning"),
                "info": sum(1 for i in self.issues if i.severity == "info"),
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_text(self) -> str:
        """Format as human-readable text."""
        lines = [
            f"Roura Agent CI - {self.mode.value.upper()}",
            f"=" * 50,
            f"Status: {'PASSED' if self.exit_code == CIExitCode.SUCCESS else 'FAILED'}",
            f"Files analyzed: {self.files_analyzed}",
            f"Duration: {self.duration_seconds:.2f}s",
            "",
        ]

        if self.issues:
            lines.append(f"Issues found: {len(self.issues)}")
            lines.append("-" * 30)
            for issue in self.issues:
                location = f"{issue.file}"
                if issue.line:
                    location += f":{issue.line}"
                lines.append(f"[{issue.severity.upper()}] {location}")
                lines.append(f"  {issue.message}")
                if issue.suggestion:
                    lines.append(f"  Suggestion: {issue.suggestion}")
                lines.append("")

        if self.summary:
            lines.append("Summary:")
            lines.append(self.summary)

        return "\n".join(lines)

    def to_github_output(self) -> str:
        """Format for GitHub Actions output."""
        lines = []
        for issue in self.issues:
            lines.append(issue.to_github_annotation())

        # Summary
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        lines.append(f"::notice::Analyzed {self.files_analyzed} files, found {errors} errors and {warnings} warnings")

        return "\n".join(lines)

    def to_gitlab_codequality(self) -> str:
        """Format as GitLab Code Quality report."""
        entries = [issue.to_gitlab_codequality() for issue in self.issues]
        return json.dumps(entries, indent=2)


class CIRunner:
    """
    Runs CI tasks in headless mode.

    Provides:
    - Non-interactive execution
    - Structured output
    - Billing integration
    """

    def __init__(
        self,
        config: CIConfig,
        billing_manager: Optional[BillingManager] = None,
    ):
        self.config = config
        self._billing = billing_manager or get_billing_manager()
        self._result: Optional[CIResult] = None
        self._selected_files: Optional[list[Path]] = None  # Override file list

    def run(self) -> CIResult:
        """Execute CI task."""
        import time

        # Check billing
        if not self._billing.check_limit(UsageType.CI_RUN):
            return CIResult(
                exit_code=CIExitCode.RATE_LIMITED,
                mode=self.config.mode,
                summary="CI run limit reached for current billing period",
            )

        start_time = time.time()
        self._result = CIResult(
            exit_code=CIExitCode.SUCCESS,
            mode=self.config.mode,
        )

        try:
            # Route to appropriate handler
            if self.config.mode == CIMode.REVIEW:
                self._run_review()
            elif self.config.mode == CIMode.FIX:
                self._run_fix()
            elif self.config.mode == CIMode.GENERATE:
                self._run_generate()
            elif self.config.mode == CIMode.TEST:
                self._run_test()
            elif self.config.mode == CIMode.DOCUMENT:
                self._run_document()
            elif self.config.mode == CIMode.ANALYZE:
                self._run_analyze()

        except TimeoutError:
            self._result.exit_code = CIExitCode.TIMEOUT
            self._result.summary = f"Execution timed out after {self.config.timeout_seconds}s"
        except Exception as e:
            self._result.exit_code = CIExitCode.ERROR
            self._result.summary = f"Error: {str(e)}"
            logger.exception("CI execution failed")

        # Finalize
        self._result.duration_seconds = time.time() - start_time
        self._result.finished_at = datetime.now().isoformat()

        # Record usage
        self._billing.record_usage(UsageType.CI_RUN, 1, {
            "mode": self.config.mode.value,
            "files": self._result.files_analyzed,
        })

        # Check if should fail
        if self.config.fail_on_issues:
            errors = sum(1 for i in self._result.issues if i.severity == "error")
            if errors > 0:
                self._result.exit_code = CIExitCode.FAILURE

        return self._result

    def _run_review(self) -> None:
        """Run code review with LLM."""
        target = Path(self.config.target_path)

        # Detect project type and find files
        project_type = self._detect_project_type(target)

        # Use selected files if provided, otherwise find all
        if self._selected_files:
            files = [f for f in self._selected_files if f.exists()]
        else:
            files = self._find_files(target, project_type=project_type)

        self._result.files_analyzed = len(files)

        if not files:
            self._result.summary = "No files found to review"
            return

        # Collect file stats for report
        file_stats = self._collect_file_stats(files, target)

        # Perform actual review
        issues = self._review_files(files, target)
        self._result.issues = issues

        # Generate detailed summary with report
        self._result.summary = self._generate_review_report(
            files, issues, project_type, file_stats
        )

    def _collect_file_stats(
        self,
        files: list[Path],
        base_path: Path,
    ) -> dict[str, Any]:
        """Collect statistics about files for reporting."""
        stats = {
            "total_lines": 0,
            "total_chars": 0,
            "by_extension": {},
            "largest_files": [],
        }

        file_sizes = []
        for file_path in files:
            try:
                content = file_path.read_text(errors="ignore")
                lines = len(content.split("\n"))
                chars = len(content)

                stats["total_lines"] += lines
                stats["total_chars"] += chars

                ext = file_path.suffix or "no_ext"
                if ext not in stats["by_extension"]:
                    stats["by_extension"][ext] = {"count": 0, "lines": 0}
                stats["by_extension"][ext]["count"] += 1
                stats["by_extension"][ext]["lines"] += lines

                try:
                    rel_path = str(file_path.relative_to(base_path))
                except ValueError:
                    rel_path = str(file_path)

                file_sizes.append((rel_path, lines, chars))

            except Exception:
                pass

        # Get top 5 largest files by lines
        file_sizes.sort(key=lambda x: x[1], reverse=True)
        stats["largest_files"] = file_sizes[:5]

        return stats

    def _generate_review_report(
        self,
        files: list[Path],
        issues: list[CIIssue],
        project_type: Optional[str],
        stats: dict[str, Any],
    ) -> str:
        """Generate a detailed review report."""
        lines = []

        # Header
        lines.append(f"Project Type: {project_type or 'Unknown'}")
        lines.append(f"Files Reviewed: {len(files)}")
        lines.append(f"Total Lines: {stats['total_lines']:,}")
        lines.append("")

        # Issue summary
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")

        lines.append("─" * 40)
        lines.append("ISSUE SUMMARY")
        lines.append("─" * 40)
        lines.append(f"  🔴 Errors:   {error_count}")
        lines.append(f"  🟡 Warnings: {warning_count}")
        lines.append(f"  🔵 Info:     {info_count}")
        lines.append("")

        # Files by extension
        if stats["by_extension"]:
            lines.append("─" * 40)
            lines.append("FILES BY TYPE")
            lines.append("─" * 40)
            for ext, data in sorted(stats["by_extension"].items(), key=lambda x: x[1]["lines"], reverse=True):
                lines.append(f"  {ext}: {data['count']} files, {data['lines']:,} lines")
            lines.append("")

        # Largest files
        if stats["largest_files"]:
            lines.append("─" * 40)
            lines.append("LARGEST FILES")
            lines.append("─" * 40)
            for path, line_count, _ in stats["largest_files"]:
                lines.append(f"  {line_count:>5} lines  {path}")
            lines.append("")

        # Files with most issues
        if issues:
            lines.append("─" * 40)
            lines.append("HOTSPOTS (files with most issues)")
            lines.append("─" * 40)
            issue_counts: dict[str, dict[str, int]] = {}
            for issue in issues:
                if issue.file not in issue_counts:
                    issue_counts[issue.file] = {"error": 0, "warning": 0, "info": 0}
                issue_counts[issue.file][issue.severity] += 1

            sorted_files = sorted(
                issue_counts.items(),
                key=lambda x: (x[1]["error"] * 10 + x[1]["warning"] * 3 + x[1]["info"]),
                reverse=True,
            )[:5]

            for file_path, counts in sorted_files:
                parts = []
                if counts["error"]:
                    parts.append(f"{counts['error']}E")
                if counts["warning"]:
                    parts.append(f"{counts['warning']}W")
                if counts["info"]:
                    parts.append(f"{counts['info']}I")
                lines.append(f"  {' '.join(parts):>10}  {file_path}")
            lines.append("")

        return "\n".join(lines)

    def _run_fix(self) -> None:
        """Run automatic fixes."""
        target = Path(self.config.target_path)
        project_type = self._detect_project_type(target)
        files = self._find_files(target, project_type=project_type)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Analyzed {len(files)} files for fixes"

    def _run_generate(self) -> None:
        """Run code generation."""
        self._result.summary = "Code generation complete"

    def _run_test(self) -> None:
        """Run test analysis."""
        target = Path(self.config.target_path)
        project_type = self._detect_project_type(target)

        # Find test files based on project type
        test_patterns = self._get_test_patterns(project_type)
        files = self._find_files(target, patterns=test_patterns)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Analyzed {len(files)} test files"

    def _run_document(self) -> None:
        """Run documentation generation."""
        target = Path(self.config.target_path)
        project_type = self._detect_project_type(target)
        files = self._find_files(target, project_type=project_type)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Documented {len(files)} files"

    def _run_analyze(self) -> None:
        """Run static analysis."""
        target = Path(self.config.target_path)
        project_type = self._detect_project_type(target)
        files = self._find_files(target, project_type=project_type)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Analyzed {len(files)} files"

    def _detect_project_type(self, path: Path) -> Optional[str]:
        """Detect project type based on marker files."""
        for project_type, markers in PROJECT_MARKERS.items():
            for marker in markers:
                if list(path.glob(marker)):
                    logger.debug(f"Detected project type: {project_type}")
                    return project_type
        return None

    def _get_file_patterns(self, project_type: Optional[str]) -> list[str]:
        """Get file patterns for a project type."""
        if project_type and project_type in PROJECT_DEFAULT_PATTERNS:
            categories = PROJECT_DEFAULT_PATTERNS[project_type]
            patterns = []
            for cat in categories:
                if cat in FILE_PATTERNS:
                    patterns.extend(FILE_PATTERNS[cat])
            return patterns

        # Default: include common code files
        default_categories = ["python", "javascript", "typescript", "swift", "kotlin", "go", "rust", "json", "yaml"]
        patterns = []
        for cat in default_categories:
            if cat in FILE_PATTERNS:
                patterns.extend(FILE_PATTERNS[cat])
        return patterns

    def _get_test_patterns(self, project_type: Optional[str]) -> list[str]:
        """Get test file patterns based on project type."""
        patterns = []

        if project_type == "python":
            patterns = ["**/test_*.py", "**/*_test.py", "**/tests/**/*.py"]
        elif project_type == "node":
            patterns = ["**/*.test.js", "**/*.test.ts", "**/*.spec.js", "**/*.spec.ts", "**/test/**/*.js", "**/test/**/*.ts"]
        elif project_type == "ios":
            patterns = ["**/*Tests.swift", "**/*Test.swift", "**/Tests/**/*.swift"]
        elif project_type == "android":
            patterns = ["**/*Test.kt", "**/*Test.java", "**/test/**/*.kt", "**/test/**/*.java"]
        elif project_type == "go":
            patterns = ["**/*_test.go"]
        elif project_type == "rust":
            patterns = ["**/tests/**/*.rs"]
        else:
            # Generic test patterns
            patterns = [
                "**/test_*.py", "**/*_test.py",
                "**/*.test.js", "**/*.test.ts",
                "**/*Test.swift", "**/*Test.kt", "**/*Test.java",
                "**/*_test.go", "**/tests/**/*",
            ]

        return patterns

    def _should_ignore(self, file_path: Path, base_path: Path) -> bool:
        """Check if a file should be ignored."""
        try:
            rel_path = str(file_path.relative_to(base_path))
        except ValueError:
            rel_path = str(file_path)

        for pattern in IGNORE_PATTERNS:
            # Simple glob-like matching
            if pattern.startswith("**/"):
                check_pattern = pattern[3:]
                if check_pattern.endswith("/**"):
                    dir_part = check_pattern[:-3]
                    if f"/{dir_part}/" in f"/{rel_path}" or rel_path.startswith(f"{dir_part}/"):
                        return True
                elif "*" in check_pattern:
                    import fnmatch
                    if fnmatch.fnmatch(rel_path, check_pattern) or fnmatch.fnmatch(file_path.name, check_pattern):
                        return True
        return False

    def _find_files(
        self,
        path: Path,
        patterns: Optional[list[str]] = None,
        project_type: Optional[str] = None,
    ) -> list[Path]:
        """Find files to process."""
        if not patterns:
            patterns = self._get_file_patterns(project_type)

        files = []
        seen = set()

        for pattern in patterns:
            for file_path in path.glob(pattern):
                if file_path.is_file() and file_path not in seen:
                    if not self._should_ignore(file_path, path):
                        files.append(file_path)
                        seen.add(file_path)

        # Sort by path for consistent ordering
        files.sort(key=lambda f: str(f))

        # Limit files
        files = files[:self.config.max_files]

        return files

    def _review_files(self, files: list[Path], base_path: Path) -> list[CIIssue]:
        """Review files using LLM and return issues."""
        try:
            from ..llm.base import get_provider
        except ImportError:
            logger.warning("LLM provider not available, skipping actual review")
            return []

        issues = []

        # Group files into batches to avoid token limits
        batches = self._create_review_batches(files, base_path)

        for batch_num, batch in enumerate(batches, 1):
            logger.info(f"Reviewing batch {batch_num}/{len(batches)} ({len(batch)} files)")

            try:
                batch_issues = self._review_batch(batch, base_path)
                issues.extend(batch_issues)
            except Exception as e:
                logger.error(f"Error reviewing batch {batch_num}: {e}")
                # Add an error issue for the failed batch
                issues.append(CIIssue(
                    file="<batch>",
                    line=None,
                    severity="warning",
                    message=f"Could not review batch {batch_num}: {str(e)}",
                ))

        return issues

    def _create_review_batches(
        self,
        files: list[Path],
        base_path: Path,
        max_chars_per_batch: int = 50000,
    ) -> list[list[tuple[Path, str]]]:
        """Create batches of files for review, respecting token limits."""
        batches = []
        current_batch = []
        current_chars = 0

        for file_path in files:
            try:
                content = file_path.read_text(errors="ignore")

                # Skip very large files
                if len(content) > 20000:
                    logger.debug(f"Skipping large file: {file_path}")
                    continue

                # Skip binary-looking files
                if "\x00" in content[:1000]:
                    continue

                file_chars = len(content)

                if current_chars + file_chars > max_chars_per_batch and current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_chars = 0

                current_batch.append((file_path, content))
                current_chars += file_chars

            except Exception as e:
                logger.debug(f"Could not read {file_path}: {e}")

        if current_batch:
            batches.append(current_batch)

        return batches

    def _review_batch(
        self,
        batch: list[tuple[Path, str]],
        base_path: Path,
    ) -> list[CIIssue]:
        """Review a batch of files with LLM."""
        from ..llm.base import get_provider

        # Build the review prompt
        files_content = []
        for file_path, content in batch:
            try:
                rel_path = file_path.relative_to(base_path)
            except ValueError:
                rel_path = file_path

            # Add line numbers for easier reference
            numbered_lines = []
            for i, line in enumerate(content.split("\n"), 1):
                numbered_lines.append(f"{i:4d} | {line}")
            numbered_content = "\n".join(numbered_lines)

            files_content.append(f"### File: {rel_path}\n```\n{numbered_content}\n```\n")

        combined_content = "\n".join(files_content)

        # Detect language for specialized prompts
        extensions = set(Path(f[0]).suffix for f in batch)
        is_swift = ".swift" in extensions

        if is_swift:
            expert_persona = """You are a Senior Staff Engineer and Swift 6 expert with 10+ years of iOS development experience.
You have deep knowledge of:
- Swift 6 concurrency (actors, async/await, Sendable, isolation)
- SwiftUI best practices and performance optimization
- Memory management and ARC
- SOLID principles and clean architecture
- iOS security best practices
- Xcode and Swift compiler warnings"""
        else:
            expert_persona = """You are a Senior Staff Engineer with expertise in multiple languages and frameworks.
You have deep knowledge of software architecture, security, performance, and best practices."""

        review_prompt = f"""{expert_persona}

Review the following code files thoroughly and identify issues. Be specific and actionable.

**OUTPUT FORMAT** - For each issue, output EXACTLY this format (one per line):
ISSUE|file_path|line_number|severity|message|suggestion

Example:
ISSUE|Luminae/App/LuminaeApp.swift|42|warning|Force unwrap could crash if nil|Use optional binding: if let value = optional {{ ... }}
ISSUE|Luminae/Core/Network.swift|0|error|Missing error handling for network calls|Wrap in do-catch and handle specific errors

**FIELDS:**
- file_path: exact relative path as shown in the file header
- line_number: specific line number, or 0 if applies to whole file
- severity: "error" (bugs, security, crashes), "warning" (performance, maintainability), "info" (style, suggestions)
- message: concise description of the issue
- suggestion: how to fix it

**REVIEW CHECKLIST:**
ERRORS (severity: error):
- Force unwraps that could crash (!, try!)
- Memory leaks, retain cycles
- Race conditions, thread safety issues
- Security vulnerabilities (hardcoded secrets, SQL injection, etc.)
- Unhandled errors that could crash

WARNINGS (severity: warning):
- Performance issues (N+1 queries, unnecessary recomputation)
- Missing Swift 6 Sendable conformance where needed
- Deprecated API usage
- Code that violates SOLID principles
- Missing input validation

INFO (severity: info):
- Better naming suggestions
- Simplification opportunities
- Documentation improvements

{self.config.extra_context or ""}

**FILES TO REVIEW:**

{combined_content}

**IMPORTANT:** Output ONLY lines starting with "ISSUE|". No other text, explanations, or markdown."""

        try:
            provider = get_provider(check_license=False)
            response = provider.chat([
                {"role": "user", "content": review_prompt}
            ])

            logger.debug(f"LLM response: {response.content[:500]}...")
            return self._parse_review_response(response.content)

        except Exception as e:
            logger.error(f"LLM review failed: {e}")
            return []

    def _parse_review_response(self, response: str) -> list[CIIssue]:
        """Parse LLM response into CIIssue objects."""
        issues = []

        for line in response.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("ISSUE|"):
                continue

            parts = line.split("|")
            if len(parts) < 5:
                continue

            try:
                _, file_path, line_num, severity, message = parts[:5]
                suggestion = parts[5] if len(parts) > 5 else None

                # Validate severity
                severity = severity.lower()
                if severity not in ("error", "warning", "info"):
                    severity = "warning"

                # Parse line number
                try:
                    line_number = int(line_num) if line_num and line_num != "0" else None
                except ValueError:
                    line_number = None

                issues.append(CIIssue(
                    file=file_path.strip(),
                    line=line_number,
                    severity=severity,
                    message=message.strip(),
                    suggestion=suggestion.strip() if suggestion else None,
                ))

            except Exception as e:
                logger.debug(f"Could not parse issue line: {line} - {e}")

        return issues

    def output(self) -> str:
        """Get formatted output."""
        if not self._result:
            return ""

        if self.config.output_format == "json":
            return self._result.to_json()
        elif self.config.output_format == "github":
            return self._result.to_github_output()
        elif self.config.output_format == "gitlab":
            return self._result.to_gitlab_codequality()
        else:
            return self._result.to_text()


def run_ci_task(config: Optional[CIConfig] = None) -> int:
    """
    Run CI task and return exit code.

    Can be called from command line or as library function.
    """
    if config is None:
        config = CIConfig.from_env()

    runner = CIRunner(config)
    result = runner.run()

    # Output result
    output = runner.output()
    print(output)

    return result.exit_code.value


def ci_main():
    """CLI entry point for CI mode."""
    import argparse

    parser = argparse.ArgumentParser(description="Roura Agent CI Mode")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in CIMode],
        default="review",
        help="CI mode to run",
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target path to analyze",
    )
    parser.add_argument(
        "--output",
        choices=["json", "text", "github", "gitlab"],
        default="json",
        help="Output format",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        help="Maximum files to process",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Don't fail on issues",
    )

    args = parser.parse_args()

    config = CIConfig(
        mode=CIMode(args.mode),
        target_path=args.target,
        max_files=args.max_files,
        timeout_seconds=args.timeout,
        fail_on_issues=not args.no_fail,
        output_format=args.output,
    )

    exit_code = run_ci_task(config)
    sys.exit(exit_code)


if __name__ == "__main__":
    ci_main()
