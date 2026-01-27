"""
Roura Agent Glob Tool - Find files by pattern.

© Roura.io
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry


# Directories to always ignore
IGNORE_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "env",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".build",
    "target",
    ".idea",
    ".vscode",
    "coverage",
    ".coverage",
    ".nyc_output",
    "vendor",
    "Pods",
    ".gradle",
    ".roura",
}

# Files to always ignore
IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    ".gitignore",
    ".dockerignore",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "Pipfile.lock",
}


def should_ignore_dir(name: str) -> bool:
    """Check if a directory should be ignored."""
    return name in IGNORE_DIRS or name.startswith(".")


def should_ignore_file(name: str) -> bool:
    """Check if a file should be ignored."""
    return name in IGNORE_FILES


@dataclass
class GlobResult:
    """Result of a glob operation."""
    path: str
    relative_path: str
    is_file: bool
    size: int
    modified: float


def glob_files(
    pattern: str,
    root: Optional[str] = None,
    max_results: int = 500,
    include_hidden: bool = False,
) -> list[GlobResult]:
    """
    Find files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "**/*.py", "src/**/*.ts")
        root: Root directory to search from (default: cwd)
        max_results: Maximum number of results to return
        include_hidden: Whether to include hidden files/directories

    Returns:
        List of matching files/directories
    """
    root_path = Path(root) if root else Path.cwd()
    root_path = root_path.resolve()

    if not root_path.exists():
        return []

    results: list[GlobResult] = []

    # Handle patterns with ** (recursive)
    if "**" in pattern:
        # Use pathlib's glob for recursive patterns
        for match in root_path.glob(pattern):
            if len(results) >= max_results:
                break

            # Skip ignored directories
            try:
                rel_parts = match.relative_to(root_path).parts
                if any(should_ignore_dir(part) for part in rel_parts):
                    continue

                # Skip hidden unless requested
                if not include_hidden:
                    if any(part.startswith(".") for part in rel_parts):
                        continue

                # Skip ignored files
                if match.is_file() and should_ignore_file(match.name):
                    continue

                stat = match.stat()
                results.append(GlobResult(
                    path=str(match),
                    relative_path=str(match.relative_to(root_path)),
                    is_file=match.is_file(),
                    size=stat.st_size if match.is_file() else 0,
                    modified=stat.st_mtime,
                ))
            except (OSError, ValueError):
                continue
    else:
        # Non-recursive pattern - walk and match
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Filter out ignored directories
            dirnames[:] = [
                d for d in dirnames
                if not should_ignore_dir(d) and (include_hidden or not d.startswith("."))
            ]

            current = Path(dirpath)

            for name in filenames:
                if len(results) >= max_results:
                    break

                # Skip hidden unless requested
                if not include_hidden and name.startswith("."):
                    continue

                # Skip ignored files
                if should_ignore_file(name):
                    continue

                # Check if filename matches pattern
                if fnmatch.fnmatch(name, pattern):
                    filepath = current / name
                    try:
                        stat = filepath.stat()
                        results.append(GlobResult(
                            path=str(filepath),
                            relative_path=str(filepath.relative_to(root_path)),
                            is_file=True,
                            size=stat.st_size,
                            modified=stat.st_mtime,
                        ))
                    except OSError:
                        continue

            if len(results) >= max_results:
                break

    # Sort by modification time (most recent first)
    results.sort(key=lambda r: r.modified, reverse=True)

    return results


@dataclass
class GlobTool(Tool):
    """Find files by glob pattern."""

    name: str = "glob"
    description: str = "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts')"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("pattern", str, "Glob pattern to match (e.g., '**/*.py')", required=True),
        ToolParam("path", str, "Root directory to search from (default: current directory)", required=False, default=None),
        ToolParam("max_results", int, "Maximum number of results (default: 100)", required=False, default=100),
    ])

    def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        max_results: int = 100,
    ) -> ToolResult:
        """Find files matching a glob pattern."""
        try:
            results = glob_files(
                pattern=pattern,
                root=path,
                max_results=max_results,
            )

            # Format results
            files = []
            for r in results:
                files.append({
                    "path": r.relative_path,
                    "size": r.size,
                })

            return ToolResult(
                success=True,
                output={
                    "pattern": pattern,
                    "root": str(Path(path).resolve()) if path else str(Path.cwd()),
                    "count": len(files),
                    "truncated": len(results) >= max_results,
                    "files": files,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )

    def dry_run(
        self,
        pattern: str,
        path: Optional[str] = None,
        max_results: int = 100,
    ) -> str:
        """Describe what would be searched."""
        root = Path(path).resolve() if path else Path.cwd()
        return f"Would search for '{pattern}' in {root}"


# Create and register tool instance
glob_tool = GlobTool()
registry.register(glob_tool)


# Convenience function
def find_files(
    pattern: str,
    path: Optional[str] = None,
    max_results: int = 100,
) -> ToolResult:
    """Find files matching a glob pattern."""
    return glob_tool.execute(pattern=pattern, path=path, max_results=max_results)
