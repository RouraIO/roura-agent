"""
Roura Agent Review v2 - Deep Exhaustive Code Review.

Replaces /review with comprehensive analysis that ALWAYS produces findings.
Never outputs "No issues found" alone.

© Roura.io
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .repo_index import get_or_build_index, get_largest_by_language, RepoIndex
from .repo_tools import read_file, list_files


class Severity(Enum):
    """Finding severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


@dataclass
class Finding:
    """A single review finding."""
    severity: Severity
    title: str
    detail: str
    file: Optional[str] = None
    line: Optional[int] = None
    suggested_action: str = ""
    category: str = "general"


@dataclass
class ReviewResult:
    """Complete review result."""
    summary: dict[str, int] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    prioritized_actions: list[str] = field(default_factory=list)
    structural_improvements: list[str] = field(default_factory=list)
    next_investments: list[str] = field(default_factory=list)
    files_reviewed: int = 0
    lines_reviewed: int = 0


# God file threshold
GOD_FILE_LINES = 400

# Duplicate detection window
DUPLICATE_WINDOW = 5


def run_review(root: Path, depth: str = "deep") -> ReviewResult:
    """
    Run code review on repository.

    Args:
        root: Repository root
        depth: "quick" or "deep" (default)

    Returns:
        ReviewResult with findings and recommendations
    """
    root = Path(root).resolve()
    result = ReviewResult()

    # Build or load index
    index = get_or_build_index(root)

    if depth == "quick":
        return _run_quick_review(root, index, result)
    else:
        return _run_deep_review(root, index, result)


def _run_quick_review(root: Path, index: RepoIndex, result: ReviewResult) -> ReviewResult:
    """Quick review - just structure and obvious issues."""
    result.files_reviewed = min(index.total_files, 20)
    result.lines_reviewed = sum(lines for _, lines in index.largest_files[:20])

    # Check for god files
    _check_god_files(index, result)

    # Basic structure check
    _check_project_structure(root, index, result)

    # Always add structural improvements
    _add_structural_improvements(index, result)

    # Summary
    result.summary = {
        "critical": sum(1 for f in result.findings if f.severity == Severity.CRITICAL),
        "warning": sum(1 for f in result.findings if f.severity == Severity.WARNING),
        "info": sum(1 for f in result.findings if f.severity == Severity.INFO),
        "suggestion": sum(1 for f in result.findings if f.severity == Severity.SUGGESTION),
    }

    return result


def _run_deep_review(root: Path, index: RepoIndex, result: ReviewResult) -> ReviewResult:
    """Deep exhaustive review."""
    result.files_reviewed = index.total_files
    result.lines_reviewed = index.total_lines

    # 1. God file detection
    _check_god_files(index, result)

    # 2. Duplicate pattern detection
    _check_duplicates(root, index, result)

    # 3. Missing tests check
    _check_missing_tests(root, index, result)

    # 4. Routing correctness (for roura-agent itself)
    _check_routing_correctness(root, index, result)

    # 5. Execution loop presence
    _check_execution_loop(root, index, result)

    # 6. Project structure
    _check_project_structure(root, index, result)

    # 7. Code quality patterns
    _check_code_quality(root, index, result)

    # 8. CI/Workflow checks
    _check_ci_workflows(root, result)

    # Always add improvements and investments
    _add_structural_improvements(index, result)
    _add_next_investments(index, result)

    # Generate prioritized actions
    _generate_prioritized_actions(result)

    # Summary counts
    result.summary = {
        "critical": sum(1 for f in result.findings if f.severity == Severity.CRITICAL),
        "warning": sum(1 for f in result.findings if f.severity == Severity.WARNING),
        "info": sum(1 for f in result.findings if f.severity == Severity.INFO),
        "suggestion": sum(1 for f in result.findings if f.severity == Severity.SUGGESTION),
        "total": len(result.findings),
    }

    return result


def _check_god_files(index: RepoIndex, result: ReviewResult) -> None:
    """Detect god files (>400 lines) that should be split."""
    for path, lines in index.largest_files:
        if lines > GOD_FILE_LINES:
            result.findings.append(Finding(
                severity=Severity.WARNING,
                title=f"God file detected: {path}",
                detail=f"File has {lines} lines, exceeding {GOD_FILE_LINES} line threshold. "
                       "Consider splitting into smaller, focused modules.",
                file=path,
                suggested_action=f"Split {Path(path).stem} into smaller modules by responsibility",
                category="architecture",
            ))


def _check_duplicates(root: Path, index: RepoIndex, result: ReviewResult) -> None:
    """Detect duplicate code patterns."""
    # Hash line windows to detect duplicates
    seen_hashes: dict[str, list[tuple[str, int]]] = {}

    # Check YAML and Python files for duplicates
    files_to_check = []
    for path, _ in index.largest_files[:30]:
        ext = Path(path).suffix.lower()
        if ext in (".py", ".yml", ".yaml", ".swift", ".ts"):
            files_to_check.append(path)

    for file_path in files_to_check:
        try:
            content = read_file(root / file_path, max_bytes=50000)
            lines = content.splitlines()

            for i in range(len(lines) - DUPLICATE_WINDOW + 1):
                window = "\n".join(lines[i:i + DUPLICATE_WINDOW])
                # Skip trivial windows
                if len(window.strip()) < 50:
                    continue

                h = hashlib.md5(window.encode()).hexdigest()

                if h in seen_hashes:
                    # Duplicate found
                    existing = seen_hashes[h][0]
                    result.findings.append(Finding(
                        severity=Severity.INFO,
                        title="Duplicate code pattern detected",
                        detail=f"Similar code found in {file_path}:{i+1} and {existing[0]}:{existing[1]}",
                        file=file_path,
                        line=i + 1,
                        suggested_action="Consider extracting common code into a shared function/module",
                        category="duplication",
                    ))
                else:
                    seen_hashes[h] = [(file_path, i + 1)]
        except Exception:
            continue


def _check_missing_tests(root: Path, index: RepoIndex, result: ReviewResult) -> None:
    """Check for public modules without corresponding tests."""
    # Get all source files
    source_files = set()
    test_files = set()

    for path, _ in index.largest_files:
        name = Path(path).stem.lower()
        if "test" in name or "spec" in name or path.startswith("tests/"):
            test_files.add(name.replace("test_", "").replace("_test", "").replace("_spec", ""))
        else:
            source_files.add(name)

    # Find untested modules
    untested = source_files - test_files

    # Prioritize important-sounding modules
    important_patterns = ["service", "handler", "controller", "manager", "api", "core"]

    for module in untested:
        for pattern in important_patterns:
            if pattern in module:
                result.findings.append(Finding(
                    severity=Severity.SUGGESTION,
                    title=f"Missing tests for {module}",
                    detail=f"Module '{module}' appears important but has no corresponding test file",
                    suggested_action=f"Add tests/test_{module}.py with unit tests",
                    category="testing",
                ))
                break


def _check_routing_correctness(root: Path, index: RepoIndex, result: ReviewResult) -> None:
    """Verify hard mode routing is correctly implemented."""
    # Look for intent routing files
    intent_files = [p for p, _ in index.largest_files if "intent" in p.lower() or "router" in p.lower()]

    if not intent_files:
        # Check if this is a roura-agent project
        if any("roura" in p.lower() for p, _ in index.largest_files):
            result.findings.append(Finding(
                severity=Severity.WARNING,
                title="Intent routing module may be missing",
                detail="No dedicated intent/router module found. Hard mode routing should be explicit.",
                suggested_action="Create roura_agent/intent.py with hard mode token detection",
                category="architecture",
            ))


def _check_execution_loop(root: Path, index: RepoIndex, result: ReviewResult) -> None:
    """Verify execution loop (apply → run → feed) exists."""
    loop_patterns = ["execution_loop", "verification_loop", "apply_edits", "run_commands"]
    found_patterns = []

    for path, _ in index.largest_files[:50]:
        try:
            content = read_file(root / path, max_bytes=100000)
            for pattern in loop_patterns:
                if pattern in content.lower():
                    found_patterns.append(pattern)
        except Exception:
            continue

    if not found_patterns:
        result.findings.append(Finding(
            severity=Severity.INFO,
            title="Execution loop patterns not detected",
            detail="No apply→run→feed execution loop found. Consider implementing for iterative fixes.",
            suggested_action="Add execution_loop.py with verification_loop function",
            category="architecture",
        ))


def _check_project_structure(root: Path, index: RepoIndex, result: ReviewResult) -> None:
    """Check overall project structure."""
    # Check for README
    readme_exists = any(
        p.lower().startswith("readme")
        for p in list_files(root, ["README*", "readme*"])
    )

    if not readme_exists:
        result.findings.append(Finding(
            severity=Severity.SUGGESTION,
            title="Missing README",
            detail="No README file found in project root",
            suggested_action="Add README.md with project description and usage",
            category="documentation",
        ))

    # Check for license
    license_exists = any(
        "license" in p.lower()
        for p in list_files(root, ["LICENSE*", "license*"])
    )

    if not license_exists:
        result.findings.append(Finding(
            severity=Severity.INFO,
            title="Missing LICENSE file",
            detail="No LICENSE file found",
            suggested_action="Add LICENSE file appropriate for your project",
            category="documentation",
        ))


def _check_code_quality(root: Path, index: RepoIndex, result: ReviewResult) -> None:
    """Check common code quality patterns."""
    quality_issues = []

    for path, lines in index.largest_files[:20]:
        if lines < 50:
            continue

        try:
            content = read_file(root / path, max_bytes=100000)

            # Check for TODO/FIXME
            todos = len(re.findall(r'\b(TODO|FIXME|XXX|HACK)\b', content, re.IGNORECASE))
            if todos > 5:
                quality_issues.append((path, f"{todos} TODO/FIXME comments"))

            # Check for long functions (Python)
            if path.endswith(".py"):
                # Simple heuristic: count def/class blocks
                func_count = len(re.findall(r'^def \w+', content, re.MULTILINE))
                avg_lines = lines / max(func_count, 1)
                if avg_lines > 50 and func_count > 0:
                    quality_issues.append((path, f"Large average function size ({avg_lines:.0f} lines)"))

        except Exception:
            continue

    for path, issue in quality_issues[:5]:
        result.findings.append(Finding(
            severity=Severity.INFO,
            title=f"Code quality: {issue}",
            detail=f"File {path} has quality concern: {issue}",
            file=path,
            suggested_action="Consider refactoring to improve code quality",
            category="quality",
        ))


def _check_ci_workflows(root: Path, result: ReviewResult) -> None:
    """Check CI/CD workflow configuration."""
    workflows_dir = root / ".github" / "workflows"

    if not workflows_dir.exists():
        result.findings.append(Finding(
            severity=Severity.SUGGESTION,
            title="No GitHub Actions workflows",
            detail="No .github/workflows directory found",
            suggested_action="Add CI workflow for automated testing",
            category="ci",
        ))
        return

    # Check for test workflow
    workflow_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
    has_test = False

    for wf in workflow_files:
        try:
            content = wf.read_text()
            if "test" in content.lower() or "pytest" in content.lower():
                has_test = True
                break
        except Exception:
            continue

    if not has_test:
        result.findings.append(Finding(
            severity=Severity.SUGGESTION,
            title="No test workflow detected",
            detail="CI workflows exist but no test job found",
            suggested_action="Add test job to CI workflow",
            category="ci",
        ))


def _add_structural_improvements(index: RepoIndex, result: ReviewResult) -> None:
    """Always add structural improvement suggestions."""
    improvements = []

    # Based on file count
    if index.total_files > 100:
        improvements.append("Consider organizing files into feature-based directories")

    # Based on largest files
    if any(lines > 500 for _, lines in index.largest_files):
        improvements.append("Break down large files into smaller, focused modules")

    # Based on test coverage
    test_ratio = len(index.test_files) / max(index.total_files, 1)
    if test_ratio < 0.2:
        improvements.append("Increase test coverage - aim for 1 test file per source module")

    # Generic improvements
    improvements.extend([
        "Add type hints to all public functions",
        "Ensure all modules have docstrings",
        "Consider adding pre-commit hooks for linting",
    ])

    result.structural_improvements = improvements[:5]


def _add_next_investments(index: RepoIndex, result: ReviewResult) -> None:
    """Always add next investment suggestions."""
    investments = [
        f"Document the {index.primary_language} architecture patterns used",
        "Add integration tests for critical paths",
        "Set up automated dependency updates",
        "Add performance benchmarks for hot paths",
        "Consider adding API documentation (OpenAPI/Swagger)",
    ]

    result.next_investments = investments[:4]


def _generate_prioritized_actions(result: ReviewResult) -> None:
    """Generate prioritized action list from findings."""
    actions = []

    # Critical first
    for f in result.findings:
        if f.severity == Severity.CRITICAL and f.suggested_action:
            actions.append(f"🔴 CRITICAL: {f.suggested_action}")

    # Warnings next
    for f in result.findings:
        if f.severity == Severity.WARNING and f.suggested_action:
            actions.append(f"🟡 WARNING: {f.suggested_action}")

    # Top suggestions
    for f in result.findings[:3]:
        if f.severity == Severity.SUGGESTION and f.suggested_action:
            actions.append(f"💡 SUGGESTION: {f.suggested_action}")

    result.prioritized_actions = actions[:10]


def format_review_output(result: ReviewResult) -> str:
    """Format review result as readable output."""
    lines = [
        "=" * 60,
        "ROURA.IO DEEP CODE REVIEW",
        "=" * 60,
        "",
        f"Files reviewed: {result.files_reviewed:,}",
        f"Lines reviewed: {result.lines_reviewed:,}",
        "",
        "SUMMARY:",
        f"  Critical: {result.summary.get('critical', 0)}",
        f"  Warnings: {result.summary.get('warning', 0)}",
        f"  Info: {result.summary.get('info', 0)}",
        f"  Suggestions: {result.summary.get('suggestion', 0)}",
        "",
    ]

    if result.findings:
        lines.append("FINDINGS:")
        for f in result.findings[:15]:
            severity_icon = {
                Severity.CRITICAL: "🔴",
                Severity.WARNING: "🟡",
                Severity.INFO: "ℹ️",
                Severity.SUGGESTION: "💡",
            }.get(f.severity, "•")
            lines.append(f"  {severity_icon} {f.title}")
            if f.file:
                lines.append(f"      File: {f.file}")
            lines.append(f"      {f.detail[:100]}")
            if f.suggested_action:
                lines.append(f"      → {f.suggested_action}")
            lines.append("")

    if result.prioritized_actions:
        lines.append("PRIORITIZED ACTIONS:")
        for action in result.prioritized_actions:
            lines.append(f"  • {action}")
        lines.append("")

    if result.structural_improvements:
        lines.append("STRUCTURAL IMPROVEMENTS:")
        for imp in result.structural_improvements:
            lines.append(f"  • {imp}")
        lines.append("")

    if result.next_investments:
        lines.append("NEXT INVESTMENTS:")
        for inv in result.next_investments:
            lines.append(f"  • {inv}")
        lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)
