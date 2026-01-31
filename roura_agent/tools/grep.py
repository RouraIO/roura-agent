"""
Roura Agent Grep Tool - Search file contents with regex.

© Roura.io
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry
from .glob import should_ignore_dir, should_ignore_file


@dataclass
class GrepMatch:
    """A single grep match."""
    file: str
    line_number: int
    line: str
    match_start: int
    match_end: int


@dataclass
class GrepFileResult:
    """Grep results for a single file."""
    file: str
    relative_path: str
    matches: list[GrepMatch]


def grep_file(
    filepath: Path,
    pattern: re.Pattern,
    context_before: int = 0,
    context_after: int = 0,
    max_matches_per_file: int = 50,
) -> list[GrepMatch]:
    """
    Search a single file for pattern matches.

    Args:
        filepath: Path to the file
        pattern: Compiled regex pattern
        context_before: Number of lines before match to include
        context_after: Number of lines after match to include
        max_matches_per_file: Maximum matches to return per file

    Returns:
        List of matches found
    """
    matches = []

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, start=1):
            if len(matches) >= max_matches_per_file:
                break

            for match in pattern.finditer(line):
                matches.append(GrepMatch(
                    file=str(filepath),
                    line_number=i,
                    line=line.rstrip("\n\r"),
                    match_start=match.start(),
                    match_end=match.end(),
                ))

                if len(matches) >= max_matches_per_file:
                    break

    except (OSError, UnicodeDecodeError):
        pass

    return matches


def grep_directory(
    pattern: str,
    root: Optional[str] = None,
    file_pattern: Optional[str] = None,
    ignore_case: bool = False,
    max_results: int = 100,
    max_files: int = 500,
    context_lines: int = 0,
) -> list[GrepFileResult]:
    """
    Search for pattern in files within a directory.

    Args:
        pattern: Regex pattern to search for
        root: Root directory to search (default: cwd)
        file_pattern: Optional glob pattern to filter files (e.g., "*.py")
        ignore_case: Whether to ignore case
        max_results: Maximum total matches to return
        max_files: Maximum files to search
        context_lines: Lines of context around matches

    Returns:
        List of file results with matches
    """
    root_path = Path(root) if root else Path.cwd()
    root_path = root_path.resolve()

    if not root_path.exists():
        return []

    # Compile regex
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

    results: list[GrepFileResult] = []
    total_matches = 0
    files_searched = 0

    # Walk directory
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter out ignored directories
        dirnames[:] = [d for d in dirnames if not should_ignore_dir(d)]

        current = Path(dirpath)

        for name in filenames:
            if files_searched >= max_files:
                break
            if total_matches >= max_results:
                break

            # Skip hidden and ignored files
            if name.startswith(".") or should_ignore_file(name):
                continue

            # Check file pattern if specified
            if file_pattern:
                import fnmatch
                if not fnmatch.fnmatch(name, file_pattern):
                    continue

            # Skip binary files (heuristic based on extension)
            binary_extensions = {
                ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
                ".o", ".a", ".obj", ".class", ".jar", ".war",
                ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
                ".pdf", ".doc", ".docx", ".xls", ".xlsx",
                ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
                ".mp3", ".mp4", ".avi", ".mov", ".wav",
                ".ttf", ".otf", ".woff", ".woff2", ".eot",
                ".sqlite", ".db",
            }
            if Path(name).suffix.lower() in binary_extensions:
                continue

            filepath = current / name
            files_searched += 1

            # Search file
            matches = grep_file(
                filepath,
                regex,
                context_before=context_lines,
                context_after=context_lines,
                max_matches_per_file=max_results - total_matches,
            )

            if matches:
                results.append(GrepFileResult(
                    file=str(filepath),
                    relative_path=str(filepath.relative_to(root_path)),
                    matches=matches,
                ))
                total_matches += len(matches)

        if total_matches >= max_results or files_searched >= max_files:
            break

    return results


@dataclass
class GrepTool(Tool):
    """Search file contents with regex."""

    name: str = "grep"
    description: str = "Search file contents using regex pattern"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("pattern", str, "Regex pattern to search for", required=True),
        ToolParam("path", str, "Directory or file to search (default: current directory)", required=False, default=None),
        ToolParam("file_pattern", str, "Glob pattern to filter files (e.g., '*.py')", required=False, default=None),
        ToolParam("ignore_case", bool, "Ignore case in search (default: False)", required=False, default=False),
        ToolParam("max_results", int, "Maximum number of matches (default: 50)", required=False, default=50),
    ])

    def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        file_pattern: Optional[str] = None,
        ignore_case: bool = False,
        max_results: int = 50,
    ) -> ToolResult:
        """Search for pattern in files."""
        try:
            root_path = Path(path) if path else Path.cwd()
            root_path = root_path.resolve()

            # Check if searching a single file
            if root_path.is_file():
                flags = re.IGNORECASE if ignore_case else 0
                try:
                    regex = re.compile(pattern, flags)
                except re.error as e:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"Invalid regex pattern: {e}",
                    )

                matches = grep_file(root_path, regex, max_matches_per_file=max_results)

                return ToolResult(
                    success=True,
                    output={
                        "pattern": pattern,
                        "root": str(root_path),
                        "files_with_matches": 1 if matches else 0,
                        "total_matches": len(matches),
                        "truncated": len(matches) >= max_results,
                        "results": [{
                            "file": str(root_path),
                            "matches": [
                                {
                                    "line": m.line_number,
                                    "content": m.line,
                                }
                                for m in matches
                            ],
                        }] if matches else [],
                    },
                )

            # Search directory
            results = grep_directory(
                pattern=pattern,
                root=str(root_path),
                file_pattern=file_pattern,
                ignore_case=ignore_case,
                max_results=max_results,
            )

            # Format results
            formatted = []
            total_matches = 0

            for file_result in results:
                formatted.append({
                    "file": file_result.relative_path,
                    "matches": [
                        {
                            "line": m.line_number,
                            "content": m.line,
                        }
                        for m in file_result.matches
                    ],
                })
                total_matches += len(file_result.matches)

            return ToolResult(
                success=True,
                output={
                    "pattern": pattern,
                    "root": str(root_path),
                    "file_pattern": file_pattern,
                    "files_with_matches": len(results),
                    "total_matches": total_matches,
                    "truncated": total_matches >= max_results,
                    "results": formatted,
                },
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
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
        file_pattern: Optional[str] = None,
        ignore_case: bool = False,
        max_results: int = 50,
    ) -> str:
        """Describe what would be searched."""
        root = Path(path).resolve() if path else Path.cwd()
        file_filter = f" in {file_pattern} files" if file_pattern else ""
        case = " (case insensitive)" if ignore_case else ""
        return f"Would search for '{pattern}'{file_filter}{case} in {root}"


# Create and register tool instance
grep_tool = GrepTool()
registry.register(grep_tool)


# Convenience function
def search_files(
    pattern: str,
    path: Optional[str] = None,
    file_pattern: Optional[str] = None,
    ignore_case: bool = False,
    max_results: int = 50,
) -> ToolResult:
    """Search for pattern in files."""
    return grep_tool.execute(
        pattern=pattern,
        path=path,
        file_pattern=file_pattern,
        ignore_case=ignore_case,
        max_results=max_results,
    )
