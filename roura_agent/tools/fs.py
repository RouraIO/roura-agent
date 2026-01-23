"""
Roura Agent Filesystem Tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry


@dataclass
class FsReadTool(Tool):
    """Read file contents."""

    name: str = "fs.read"
    description: str = "Read the contents of a file"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the file to read", required=True),
        ToolParam("offset", int, "Line number to start from (1-indexed)", required=False, default=1),
        ToolParam("lines", int, "Number of lines to read (0 = all)", required=False, default=0),
    ])

    def execute(
        self,
        path: str,
        offset: int = 1,
        lines: int = 0,
    ) -> ToolResult:
        """Read file contents."""
        try:
            file_path = Path(path).resolve()

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"File not found: {path}",
                )

            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Not a file: {path}",
                )

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)

            # Apply offset (1-indexed)
            start_idx = max(0, offset - 1)

            # Apply line limit
            if lines > 0:
                end_idx = start_idx + lines
            else:
                end_idx = total_lines

            selected_lines = all_lines[start_idx:end_idx]

            # Format with line numbers
            formatted_lines = []
            for i, line in enumerate(selected_lines, start=start_idx + 1):
                # Remove trailing newline for consistent formatting
                line_content = line.rstrip("\n\r")
                formatted_lines.append(f"{i:6d}\t{line_content}")

            output = {
                "path": str(file_path),
                "total_lines": total_lines,
                "showing": f"{start_idx + 1}-{min(end_idx, total_lines)}",
                "content": "\n".join(formatted_lines),
            }

            return ToolResult(success=True, output=output)

        except PermissionError:
            return ToolResult(
                success=False,
                output=None,
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Error reading file: {e}",
            )

    def dry_run(self, path: str, offset: int = 1, lines: int = 0) -> str:
        """Describe what would be read."""
        file_path = Path(path).resolve()
        if lines > 0:
            return f"Would read {lines} lines from {file_path} starting at line {offset}"
        else:
            return f"Would read all lines from {file_path} starting at line {offset}"


@dataclass
class FsListTool(Tool):
    """List directory contents."""

    name: str = "fs.list"
    description: str = "List contents of a directory"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the directory to list", required=True),
        ToolParam("all", bool, "Include hidden files", required=False, default=False),
    ])

    def execute(
        self,
        path: str,
        all: bool = False,
    ) -> ToolResult:
        """List directory contents."""
        try:
            dir_path = Path(path).resolve()

            if not dir_path.exists():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Directory not found: {path}",
                )

            if not dir_path.is_dir():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Not a directory: {path}",
                )

            entries = []
            for entry in sorted(dir_path.iterdir()):
                # Skip hidden files unless --all
                if not all and entry.name.startswith("."):
                    continue

                entry_type = "dir" if entry.is_dir() else "file"
                size = entry.stat().st_size if entry.is_file() else 0

                entries.append({
                    "name": entry.name,
                    "type": entry_type,
                    "size": size,
                })

            output = {
                "path": str(dir_path),
                "count": len(entries),
                "entries": entries,
            }

            return ToolResult(success=True, output=output)

        except PermissionError:
            return ToolResult(
                success=False,
                output=None,
                error=f"Permission denied: {path}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Error listing directory: {e}",
            )

    def dry_run(self, path: str, all: bool = False) -> str:
        """Describe what would be listed."""
        dir_path = Path(path).resolve()
        hidden = "including hidden files" if all else "excluding hidden files"
        return f"Would list contents of {dir_path} ({hidden})"


# Create tool instances
fs_read = FsReadTool()
fs_list = FsListTool()

# Register tools
registry.register(fs_read)
registry.register(fs_list)


def read_file(path: str, offset: int = 1, lines: int = 0) -> ToolResult:
    """Convenience function to read a file."""
    return fs_read.execute(path=path, offset=offset, lines=lines)


def list_directory(path: str, show_all: bool = False) -> ToolResult:
    """Convenience function to list a directory."""
    return fs_list.execute(path=path, all=show_all)
