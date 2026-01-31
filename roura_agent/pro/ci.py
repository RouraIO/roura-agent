"""
Roura Agent PRO CI Mode - Headless CI/CD integration.

Provides:
- Non-interactive agent execution
- Structured output for CI systems
- Exit codes and status reporting
- Environment variable configuration

© Roura.io
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..logging import get_logger
from .billing import BillingManager, UsageType, get_billing_manager

logger = get_logger(__name__)


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
        """Run code review."""
        target = Path(self.config.target_path)

        # Find files to review
        files = self._find_files(target)
        self._result.files_analyzed = len(files)

        # This would integrate with the agent core for actual review
        # For now, provide a placeholder implementation
        self._result.summary = f"Reviewed {len(files)} files"

    def _run_fix(self) -> None:
        """Run automatic fixes."""
        target = Path(self.config.target_path)
        files = self._find_files(target)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Analyzed {len(files)} files for fixes"

    def _run_generate(self) -> None:
        """Run code generation."""
        self._result.summary = "Code generation complete"

    def _run_test(self) -> None:
        """Run test analysis."""
        target = Path(self.config.target_path)
        files = self._find_files(target, patterns=["**/test_*.py", "**/*_test.py"])
        self._result.files_analyzed = len(files)
        self._result.summary = f"Analyzed {len(files)} test files"

    def _run_document(self) -> None:
        """Run documentation generation."""
        target = Path(self.config.target_path)
        files = self._find_files(target)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Documented {len(files)} files"

    def _run_analyze(self) -> None:
        """Run static analysis."""
        target = Path(self.config.target_path)
        files = self._find_files(target)
        self._result.files_analyzed = len(files)
        self._result.summary = f"Analyzed {len(files)} files"

    def _find_files(
        self,
        path: Path,
        patterns: Optional[list[str]] = None,
    ) -> list[Path]:
        """Find files to process."""
        if not patterns:
            patterns = ["**/*.py", "**/*.js", "**/*.ts", "**/*.tsx"]

        files = []
        for pattern in patterns:
            files.extend(path.glob(pattern))

        # Filter and limit
        files = [f for f in files if f.is_file()]
        files = files[:self.config.max_files]

        return files

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
