"""
Roura Agent Code Review Tools - Smart code analysis and review.

Game-changing features:
- Automatic code quality scoring
- Security vulnerability detection
- Performance issue identification
- Style and best practice analysis
- Smart diff review with suggestions

© Roura.io
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry


@dataclass
class CodeIssue:
    """Represents a code issue found during review."""
    severity: str  # "critical", "warning", "info"
    category: str  # "security", "performance", "style", "bug", "complexity"
    file: str
    line: Optional[int]
    message: str
    suggestion: Optional[str] = None


@dataclass
class ReviewResult:
    """Result of a code review."""
    score: int  # 0-100
    issues: list[CodeIssue] = field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)


# Security patterns to detect
SECURITY_PATTERNS = {
    "python": [
        (r"eval\s*\(", "critical", "Use of eval() - potential code injection"),
        (r"exec\s*\(", "critical", "Use of exec() - potential code injection"),
        (r"pickle\.loads?\s*\(", "critical", "Insecure deserialization with pickle"),
        (r"subprocess\..*shell\s*=\s*True", "warning", "Shell=True in subprocess - potential injection"),
        (r"password\s*=\s*['\"][^'\"]+['\"]", "critical", "Hardcoded password detected"),
        (r"api_key\s*=\s*['\"][^'\"]+['\"]", "critical", "Hardcoded API key detected"),
        (r"secret\s*=\s*['\"][^'\"]+['\"]", "critical", "Hardcoded secret detected"),
        (r"\.execute\s*\([^)]*%", "warning", "Potential SQL injection (string formatting)"),
        (r"\.execute\s*\([^)]*\+", "warning", "Potential SQL injection (string concatenation)"),
    ],
    "javascript": [
        (r"eval\s*\(", "critical", "Use of eval() - potential code injection"),
        (r"innerHTML\s*=", "warning", "innerHTML assignment - potential XSS"),
        (r"document\.write\s*\(", "warning", "document.write - potential XSS"),
        (r"password\s*[=:]\s*['\"][^'\"]+['\"]", "critical", "Hardcoded password detected"),
        (r"apiKey\s*[=:]\s*['\"][^'\"]+['\"]", "critical", "Hardcoded API key detected"),
        (r"dangerouslySetInnerHTML", "warning", "dangerouslySetInnerHTML - potential XSS"),
    ],
    "swift": [
        (r"password\s*=\s*\"[^\"]+\"", "critical", "Hardcoded password detected"),
        (r"apiKey\s*=\s*\"[^\"]+\"", "critical", "Hardcoded API key detected"),
        (r"try!\s+", "warning", "Force try - crashes on error"),
        (r"as!\s+", "warning", "Force cast - crashes on failure"),
        (r"!\.", "info", "Force unwrap - consider safer alternatives"),
    ],
}

# Performance patterns
PERFORMANCE_PATTERNS = {
    "python": [
        (r"for\s+.*\s+in\s+range\(len\(", "info", "Use enumerate() instead of range(len())"),
        (r"\+\s*=\s*.*\s+in\s+.*loop", "info", "String concatenation in loop - use join()"),
        (r"time\.sleep\s*\(\s*0\s*\)", "warning", "sleep(0) in loop - consider alternatives"),
        (r"global\s+\w+", "info", "Global variable - consider refactoring"),
    ],
    "javascript": [
        (r"\.forEach\s*\(.*await", "warning", "await in forEach - use for...of instead"),
        (r"document\.querySelector.*in.*loop", "warning", "DOM query in loop - cache the result"),
        (r"JSON\.parse\(JSON\.stringify", "info", "Deep clone via JSON - consider structuredClone"),
    ],
}

# Complexity patterns
COMPLEXITY_PATTERNS = [
    (r"if.*if.*if.*if", "warning", "Deeply nested conditionals - consider refactoring"),
    (r"else\s*{\s*if", "info", "else-if chain - consider switch/match"),
    (r"(try|catch).*\n.*(try|catch)", "info", "Nested try-catch - consider restructuring"),
]

# Code smell patterns
SMELL_PATTERNS = {
    "python": [
        (r"except\s*:", "warning", "Bare except - catches everything including KeyboardInterrupt"),
        (r"except\s+Exception\s*:", "info", "Broad exception - consider specific exceptions"),
        (r"#\s*TODO", "info", "TODO comment found"),
        (r"#\s*FIXME", "warning", "FIXME comment found"),
        (r"#\s*HACK", "warning", "HACK comment found"),
        (r"pass\s*$", "info", "Empty pass statement - placeholder code?"),
    ],
    "javascript": [
        (r"console\.log", "info", "console.log left in code"),
        (r"debugger", "warning", "debugger statement left in code"),
        (r"//\s*TODO", "info", "TODO comment found"),
        (r"//\s*FIXME", "warning", "FIXME comment found"),
        (r"var\s+", "info", "Use let/const instead of var"),
    ],
    "swift": [
        (r"print\(", "info", "print() left in code"),
        (r"//\s*TODO", "info", "TODO comment found"),
        (r"//\s*FIXME", "warning", "FIXME comment found"),
        (r"fatalError\(", "warning", "fatalError() - crashes app"),
    ],
}


def detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "javascript",
        ".tsx": "javascript",
        ".swift": "swift",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".rb": "ruby",
        ".php": "php",
    }
    return lang_map.get(ext, "unknown")


def analyze_file(file_path: str, content: str) -> list[CodeIssue]:
    """Analyze a single file for issues."""
    issues = []
    lang = detect_language(file_path)
    lines = content.split("\n")

    # Check security patterns
    for pattern, severity, message in SECURITY_PATTERNS.get(lang, []):
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(CodeIssue(
                    severity=severity,
                    category="security",
                    file=file_path,
                    line=i,
                    message=message,
                    suggestion="Review and fix security issue",
                ))

    # Check performance patterns
    for pattern, severity, message in PERFORMANCE_PATTERNS.get(lang, []):
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(CodeIssue(
                    severity=severity,
                    category="performance",
                    file=file_path,
                    line=i,
                    message=message,
                ))

    # Check code smells
    for pattern, severity, message in SMELL_PATTERNS.get(lang, []):
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(CodeIssue(
                    severity=severity,
                    category="style",
                    file=file_path,
                    line=i,
                    message=message,
                ))

    # Check complexity (language agnostic)
    full_content = content
    for pattern, severity, message in COMPLEXITY_PATTERNS:
        if re.search(pattern, full_content, re.IGNORECASE | re.MULTILINE):
            issues.append(CodeIssue(
                severity=severity,
                category="complexity",
                file=file_path,
                line=None,
                message=message,
            ))

    return issues


def calculate_score(issues: list[CodeIssue]) -> int:
    """Calculate a quality score based on issues found."""
    score = 100

    for issue in issues:
        if issue.severity == "critical":
            score -= 15
        elif issue.severity == "warning":
            score -= 5
        elif issue.severity == "info":
            score -= 1

    return max(0, min(100, score))


def review_file(path: str) -> ToolResult:
    """
    Review a single file for code quality issues.

    Returns a detailed analysis with issues, score, and recommendations.
    """
    file_path = Path(path).resolve()

    if not file_path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")

    if not file_path.is_file():
        return ToolResult(success=False, error=f"Not a file: {path}")

    try:
        content = file_path.read_text(errors="ignore")
    except Exception as e:
        return ToolResult(success=False, error=f"Cannot read file: {e}")

    issues = analyze_file(str(file_path), content)
    score = calculate_score(issues)

    # Generate summary
    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    info_count = sum(1 for i in issues if i.severity == "info")

    if score >= 90:
        grade = "A"
        summary = "Excellent code quality!"
    elif score >= 80:
        grade = "B"
        summary = "Good code quality with minor issues."
    elif score >= 70:
        grade = "C"
        summary = "Acceptable code quality, some improvements needed."
    elif score >= 60:
        grade = "D"
        summary = "Below average, several issues to address."
    else:
        grade = "F"
        summary = "Poor code quality, needs significant work."

    # Build recommendations
    recommendations = []
    categories = defaultdict(int)
    for issue in issues:
        categories[issue.category] += 1

    if categories["security"] > 0:
        recommendations.append(f"Fix {categories['security']} security issue(s) immediately")
    if categories["performance"] > 0:
        recommendations.append(f"Address {categories['performance']} performance issue(s)")
    if categories["complexity"] > 0:
        recommendations.append("Consider refactoring complex code sections")
    if categories["style"] > 0:
        recommendations.append("Clean up code style issues")

    return ToolResult(
        success=True,
        output={
            "file": str(file_path),
            "language": detect_language(str(file_path)),
            "score": score,
            "grade": grade,
            "summary": summary,
            "issues": {
                "critical": critical_count,
                "warning": warning_count,
                "info": info_count,
                "total": len(issues),
            },
            "details": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "line": i.line,
                    "message": i.message,
                }
                for i in issues[:20]  # Limit to top 20 issues
            ],
            "recommendations": recommendations,
        }
    )


def review_diff(diff_text: str) -> ToolResult:
    """
    Review a git diff for code quality issues.

    Analyzes only the changed lines for potential problems.
    """
    if not diff_text.strip():
        return ToolResult(success=False, error="Empty diff provided")

    issues = []
    current_file = None
    current_line = 0

    for line in diff_text.split("\n"):
        # Track current file
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue

        # Track line numbers
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1))
            continue

        # Only analyze added lines
        if line.startswith("+") and not line.startswith("+++"):
            added_content = line[1:]

            if current_file:
                lang = detect_language(current_file)

                # Check patterns
                for pattern, severity, message in SECURITY_PATTERNS.get(lang, []):
                    if re.search(pattern, added_content, re.IGNORECASE):
                        issues.append(CodeIssue(
                            severity=severity,
                            category="security",
                            file=current_file,
                            line=current_line,
                            message=message,
                        ))

                for pattern, severity, message in SMELL_PATTERNS.get(lang, []):
                    if re.search(pattern, added_content, re.IGNORECASE):
                        issues.append(CodeIssue(
                            severity=severity,
                            category="style",
                            file=current_file,
                            line=current_line,
                            message=message,
                        ))

            current_line += 1

    score = calculate_score(issues)

    if not issues:
        summary = "No issues found in the changes. Looks good!"
    elif score >= 80:
        summary = "Minor issues found in the changes."
    else:
        summary = "Several issues found in the changes that should be addressed."

    return ToolResult(
        success=True,
        output={
            "score": score,
            "summary": summary,
            "issues_count": len(issues),
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "file": i.file,
                    "line": i.line,
                    "message": i.message,
                }
                for i in issues[:15]
            ],
        }
    )


def review_project(path: str = ".", max_files: int = 50) -> ToolResult:
    """
    Review an entire project for code quality.

    Scans key files and provides an overall quality assessment.
    """
    root = Path(path).resolve()

    if not root.exists():
        return ToolResult(success=False, error=f"Path not found: {path}")

    # Patterns to skip
    skip_patterns = {
        "node_modules", "__pycache__", ".git", ".venv", "venv",
        "build", "dist", ".next", "target", "Pods", ".build",
    }

    all_issues = []
    files_reviewed = 0
    files_by_score = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

    # Find code files
    code_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".swift", ".go", ".rs", ".java", ".kt"}

    for file_path in root.rglob("*"):
        if files_reviewed >= max_files:
            break

        # Skip non-code files
        if file_path.suffix.lower() not in code_extensions:
            continue

        # Skip ignored directories
        if any(skip in str(file_path) for skip in skip_patterns):
            continue

        if not file_path.is_file():
            continue

        try:
            content = file_path.read_text(errors="ignore")
            rel_path = str(file_path.relative_to(root))

            issues = analyze_file(rel_path, content)
            all_issues.extend(issues)

            score = calculate_score(issues)
            if score >= 90:
                files_by_score["A"] += 1
            elif score >= 80:
                files_by_score["B"] += 1
            elif score >= 70:
                files_by_score["C"] += 1
            elif score >= 60:
                files_by_score["D"] += 1
            else:
                files_by_score["F"] += 1

            files_reviewed += 1

        except Exception:
            continue

    if files_reviewed == 0:
        return ToolResult(success=False, error="No code files found to review")

    overall_score = calculate_score(all_issues)

    # Group issues by category
    by_category = defaultdict(int)
    by_severity = defaultdict(int)
    for issue in all_issues:
        by_category[issue.category] += 1
        by_severity[issue.severity] += 1

    # Top issues by file
    issues_by_file = defaultdict(list)
    for issue in all_issues:
        issues_by_file[issue.file].append(issue)

    worst_files = sorted(
        issues_by_file.items(),
        key=lambda x: sum(1 for i in x[1] if i.severity == "critical") * 10 + len(x[1]),
        reverse=True
    )[:5]

    return ToolResult(
        success=True,
        output={
            "path": str(root),
            "files_reviewed": files_reviewed,
            "overall_score": overall_score,
            "grade_distribution": files_by_score,
            "total_issues": len(all_issues),
            "by_severity": dict(by_severity),
            "by_category": dict(by_category),
            "worst_files": [
                {"file": f, "issues": len(issues)}
                for f, issues in worst_files
            ],
            "top_issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "file": i.file,
                    "line": i.line,
                    "message": i.message,
                }
                for i in sorted(all_issues, key=lambda x: (x.severity == "critical", x.severity == "warning"), reverse=True)[:10]
            ],
        }
    )


def suggest_fixes(path: str) -> ToolResult:
    """
    Analyze a file and suggest specific fixes for issues found.

    Returns actionable suggestions with code examples.
    """
    file_path = Path(path).resolve()

    if not file_path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")

    try:
        content = file_path.read_text(errors="ignore")
    except Exception as e:
        return ToolResult(success=False, error=f"Cannot read file: {e}")

    lang = detect_language(str(file_path))
    lines = content.split("\n")
    suggestions = []

    # Language-specific fix suggestions
    fix_patterns = {
        "python": [
            (r"except\s*:", "except Exception as e:", "Catch specific exceptions"),
            (r"== None", "is None", "Use 'is None' for None comparisons"),
            (r"!= None", "is not None", "Use 'is not None' for None comparisons"),
            (r"== True", "", "Remove '== True', just use the boolean directly"),
            (r"== False", "not ", "Use 'not x' instead of 'x == False'"),
            (r"print\(.*\)", "logger.info(...)", "Consider using logging instead of print"),
        ],
        "javascript": [
            (r"var\s+", "const ", "Use const/let instead of var"),
            (r"== null", "=== null", "Use strict equality (===)"),
            (r"!= null", "!== null", "Use strict inequality (!==)"),
            (r"function\s+\w+\s*\([^)]*\)\s*{", "const fn = (...) => {", "Consider arrow functions"),
            (r"console\.log", "// console.log", "Remove or disable console.log"),
        ],
        "swift": [
            (r"!\.", "?.", "Use optional chaining instead of force unwrap"),
            (r"try!", "try?", "Use try? for optional try, or proper error handling"),
            (r"as!", "as?", "Use optional cast (as?) instead of force cast"),
        ],
    }

    for pattern, replacement, reason in fix_patterns.get(lang, []):
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                suggestions.append({
                    "line": i,
                    "current": line.strip(),
                    "suggestion": replacement if replacement else "Remove this pattern",
                    "reason": reason,
                })

    return ToolResult(
        success=True,
        output={
            "file": str(file_path),
            "language": lang,
            "suggestions": suggestions[:20],  # Limit to 20 suggestions
            "total_suggestions": len(suggestions),
        }
    )


# Tool classes
@dataclass
class CodeReviewFileTool(Tool):
    """Review a file for code quality issues."""

    name: str = "review.file"
    description: str = "Review a file for code quality issues, security vulnerabilities, and best practices. Returns a score and detailed analysis."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="path", type=str, description="Path to the file to review"),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return review_file(**kwargs)


@dataclass
class CodeReviewDiffTool(Tool):
    """Review a git diff for code quality issues."""

    name: str = "review.diff"
    description: str = "Review a git diff for code quality issues. Great for PR reviews."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="diff_text", type=str, description="The diff text to review"),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return review_diff(**kwargs)


@dataclass
class CodeReviewProjectTool(Tool):
    """Review an entire project for code quality."""

    name: str = "review.project"
    description: str = "Review an entire project for code quality. Scans multiple files and provides an overall assessment."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="path", type=str, description="Project directory path", default="."),
        ToolParam(name="max_files", type=int, description="Maximum files to review", default=50, required=False),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return review_project(**kwargs)


@dataclass
class CodeSuggestFixesTool(Tool):
    """Suggest specific fixes for issues in a file."""

    name: str = "review.suggest"
    description: str = "Suggest specific fixes for issues in a file with code examples."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="path", type=str, description="Path to the file"),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return suggest_fixes(**kwargs)


# Instantiate and register tools
code_review_file = CodeReviewFileTool()
code_review_diff = CodeReviewDiffTool()
code_review_project = CodeReviewProjectTool()
code_suggest_fixes = CodeSuggestFixesTool()

registry.register(code_review_file)
registry.register(code_review_diff)
registry.register(code_review_project)
registry.register(code_suggest_fixes)
