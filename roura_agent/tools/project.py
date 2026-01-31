"""
Roura Agent Project Tools - Analyze and understand large codebases.

© Roura.io
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry

# File extensions by language
LANGUAGE_EXTENSIONS = {
    "python": [".py", ".pyx", ".pxd"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "java": [".java"],
    "go": [".go"],
    "rust": [".rs"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
    "ruby": [".rb"],
    "php": [".php"],
    "csharp": [".cs"],
    "shell": [".sh", ".bash", ".zsh"],
    "yaml": [".yml", ".yaml"],
    "json": [".json"],
    "markdown": [".md", ".mdx"],
    "html": [".html", ".htm"],
    "css": [".css", ".scss", ".sass", ".less"],
}

# Common entry points by project type
ENTRY_POINTS = {
    "python": ["main.py", "app.py", "__main__.py", "cli.py", "run.py"],
    "javascript": ["index.js", "app.js", "main.js", "server.js"],
    "typescript": ["index.ts", "app.ts", "main.ts", "server.ts"],
    "swift": ["main.swift", "App.swift", "AppDelegate.swift"],
    "go": ["main.go", "cmd/main.go"],
    "rust": ["main.rs", "lib.rs"],
}

# Config files that reveal project structure
CONFIG_FILES = [
    "package.json", "pyproject.toml", "setup.py", "Cargo.toml",
    "go.mod", "build.gradle", "pom.xml", "Gemfile",
    "docker-compose.yml", "Dockerfile", ".env.example",
    "README.md", "README", "readme.md",
]


def analyze_project(path: str = ".", max_depth: int = 4) -> ToolResult:
    """
    Analyze a project's structure, languages, and key files.

    Returns a comprehensive overview suitable for understanding
    large codebases quickly.
    """
    root = Path(path).resolve()

    if not root.exists():
        return ToolResult(success=False, error=f"Path not found: {path}")

    if not root.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path}")

    # Collect stats
    stats = {
        "languages": defaultdict(lambda: {"files": 0, "lines": 0}),
        "total_files": 0,
        "total_lines": 0,
        "directories": 0,
        "config_files": [],
        "entry_points": [],
        "key_directories": [],
        "largest_files": [],
    }

    # Patterns to ignore
    ignore_patterns = {
        ".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
        "build", "dist", ".next", ".nuxt", "target", "Pods", ".build",
        ".cache", ".idea", ".vscode", "coverage", ".pytest_cache",
    }

    all_files = []

    def scan_dir(dir_path: Path, depth: int = 0):
        if depth > max_depth:
            return

        try:
            entries = list(dir_path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            name = entry.name

            # Skip ignored patterns
            if name in ignore_patterns or name.startswith("."):
                continue

            if entry.is_dir():
                stats["directories"] += 1

                # Track key directories
                if name in ["src", "lib", "app", "api", "components", "pages", "tests", "test"]:
                    rel_path = str(entry.relative_to(root))
                    if rel_path not in stats["key_directories"]:
                        stats["key_directories"].append(rel_path)

                scan_dir(entry, depth + 1)

            elif entry.is_file():
                stats["total_files"] += 1
                rel_path = str(entry.relative_to(root))

                # Check for config files
                if name in CONFIG_FILES:
                    stats["config_files"].append(rel_path)

                # Detect language and count lines
                ext = entry.suffix.lower()
                for lang, exts in LANGUAGE_EXTENSIONS.items():
                    if ext in exts:
                        try:
                            lines = len(entry.read_text(errors="ignore").splitlines())
                            stats["languages"][lang]["files"] += 1
                            stats["languages"][lang]["lines"] += lines
                            stats["total_lines"] += lines
                            all_files.append((rel_path, lines, lang))

                            # Check for entry points
                            if name in ENTRY_POINTS.get(lang, []):
                                stats["entry_points"].append(rel_path)
                        except Exception:
                            stats["languages"][lang]["files"] += 1
                        break

    scan_dir(root)

    # Find largest files
    all_files.sort(key=lambda x: x[1], reverse=True)
    stats["largest_files"] = [
        {"path": f[0], "lines": f[1], "language": f[2]}
        for f in all_files[:10]
    ]

    # Convert defaultdict to regular dict
    stats["languages"] = dict(stats["languages"])

    # Determine primary language
    if stats["languages"]:
        primary_lang = max(stats["languages"].items(), key=lambda x: x[1]["lines"])
        stats["primary_language"] = primary_lang[0]
        stats["primary_language_percentage"] = round(
            primary_lang[1]["lines"] / max(stats["total_lines"], 1) * 100, 1
        )
    else:
        stats["primary_language"] = "unknown"
        stats["primary_language_percentage"] = 0

    return ToolResult(
        success=True,
        output={
            "path": str(root),
            "summary": {
                "total_files": stats["total_files"],
                "total_lines": stats["total_lines"],
                "directories": stats["directories"],
                "primary_language": stats["primary_language"],
            },
            "languages": stats["languages"],
            "config_files": stats["config_files"][:10],
            "entry_points": stats["entry_points"][:5],
            "key_directories": stats["key_directories"][:10],
            "largest_files": stats["largest_files"][:5],
        }
    )


def find_related_files(path: str, pattern: Optional[str] = None) -> ToolResult:
    """
    Find files related to a given file (tests, imports, etc).

    Helps understand dependencies and test coverage.
    """
    file_path = Path(path).resolve()

    if not file_path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")

    # Get the project root (look for common markers)
    root = file_path.parent
    for _ in range(5):
        if any((root / marker).exists() for marker in [".git", "pyproject.toml", "package.json", "Cargo.toml"]):
            break
        if root.parent == root:
            break
        root = root.parent

    base_name = file_path.stem
    extension = file_path.suffix

    related = {
        "tests": [],
        "similar": [],
        "config": [],
    }

    # Search patterns
    test_patterns = [
        f"test_{base_name}{extension}",
        f"{base_name}_test{extension}",
        f"{base_name}.test{extension}",
        f"{base_name}.spec{extension}",
    ]

    # Search for related files
    try:
        for f in root.rglob("*"):
            if not f.is_file():
                continue

            name = f.name.lower()
            rel_path = str(f.relative_to(root))

            # Skip node_modules, etc
            if any(ignore in rel_path for ignore in ["node_modules", "__pycache__", ".git"]):
                continue

            # Check for tests
            if any(name == tp.lower() for tp in test_patterns):
                related["tests"].append(rel_path)

            # Check for similar names
            elif base_name.lower() in name and f != file_path:
                related["similar"].append(rel_path)

    except Exception as e:
        return ToolResult(success=False, error=str(e))

    return ToolResult(
        success=True,
        output={
            "file": str(file_path.relative_to(root)),
            "project_root": str(root),
            "related": related,
        }
    )


def get_project_summary(path: str = ".") -> ToolResult:
    """
    Get a quick one-paragraph summary of a project.

    Reads README and key config files to understand the project.
    """
    root = Path(path).resolve()

    summary_parts = []

    # Try to read README
    for readme_name in ["README.md", "README", "readme.md", "README.txt"]:
        readme_path = root / readme_name
        if readme_path.exists():
            try:
                content = readme_path.read_text(errors="ignore")
                # Get first paragraph
                lines = content.split("\n\n")[0].split("\n")
                # Skip title lines
                text_lines = [l for l in lines if not l.startswith("#") and l.strip()]
                if text_lines:
                    summary_parts.append(" ".join(text_lines[:3]))
                break
            except Exception:
                pass

    # Detect project type from config files
    project_type = "unknown"
    project_name = root.name

    if (root / "package.json").exists():
        try:
            import json
            pkg = json.loads((root / "package.json").read_text())
            project_name = pkg.get("name", project_name)
            project_type = "Node.js/JavaScript"
            if pkg.get("description"):
                summary_parts.insert(0, pkg["description"])
        except Exception:
            pass

    elif (root / "pyproject.toml").exists():
        project_type = "Python"
        try:
            content = (root / "pyproject.toml").read_text()
            if 'description = "' in content:
                desc = content.split('description = "')[1].split('"')[0]
                summary_parts.insert(0, desc)
        except Exception:
            pass

    elif (root / "Cargo.toml").exists():
        project_type = "Rust"

    elif (root / "go.mod").exists():
        project_type = "Go"

    elif (root / "Package.swift").exists():
        project_type = "Swift"

    # Build summary
    if not summary_parts:
        summary = f"{project_name} is a {project_type} project."
    else:
        summary = " ".join(summary_parts)

    return ToolResult(
        success=True,
        output={
            "name": project_name,
            "type": project_type,
            "summary": summary[:500],
            "path": str(root),
        }
    )


# Tool classes
@dataclass
class ProjectAnalyzeTool(Tool):
    """Analyze a project's structure, languages, and key files."""

    name: str = "project.analyze"
    description: str = "Analyze a project's structure, languages, and key files. Great for understanding large codebases."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="path", type=str, description="Project directory path", default="."),
        ToolParam(name="max_depth", type=int, description="Maximum directory depth to scan", default=4, required=False),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return analyze_project(**kwargs)


@dataclass
class ProjectRelatedTool(Tool):
    """Find files related to a given file."""

    name: str = "project.related"
    description: str = "Find files related to a given file (tests, similar files, etc)."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="path", type=str, description="Path to the file"),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return find_related_files(**kwargs)


@dataclass
class ProjectSummaryTool(Tool):
    """Get a quick summary of what a project does."""

    name: str = "project.summary"
    description: str = "Get a quick summary of what a project does."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam(name="path", type=str, description="Project directory path", default="."),
    ])

    def execute(self, **kwargs) -> ToolResult:
        return get_project_summary(**kwargs)


# Instantiate and register tools
project_analyze = ProjectAnalyzeTool()
project_related = ProjectRelatedTool()
project_summary = ProjectSummaryTool()

registry.register(project_analyze)
registry.register(project_related)
registry.register(project_summary)
