"""
Roura Agent Filesystem Tools.

© Roura.io
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry
from ..secrets import check_before_write, format_secret_warning, is_secret_file
from ..safety import (
    check_path_allowed,
    check_modification_allowed,
    record_modification,
    is_dry_run,
    is_readonly,
    check_write_allowed,
)


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


@dataclass
class FsWriteTool(Tool):
    """Write content to a file."""

    name: str = "fs.write"
    description: str = "Write content to a file (create or overwrite)"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the file to write", required=True),
        ToolParam("content", str, "Content to write to the file", required=True),
        ToolParam("create_dirs", bool, "Create parent directories if needed", required=False, default=False),
    ])

    def execute(
        self,
        path: str,
        content: str,
        create_dirs: bool = False,
    ) -> ToolResult:
        """Write content to a file."""
        try:
            file_path = Path(path).resolve()

            # SAFETY: Check if writes are allowed (readonly/dry-run mode)
            write_allowed, write_error = check_write_allowed()
            if not write_allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=write_error,
                )

            # SAFETY: Check if path is allowed
            path_allowed, path_error = check_path_allowed(str(file_path))
            if not path_allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"BLOCKED: {path_error}",
                )

            # SAFETY: Check blast radius limits
            lines_to_write = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            mod_allowed, mod_error = check_modification_allowed(str(file_path), lines_to_write)
            if not mod_allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"BLOCKED: {mod_error}",
                )

            # SECURITY: Check for secrets before writing
            is_safe, secret_matches = check_before_write(content, str(file_path))
            if not is_safe:
                warning = format_secret_warning(secret_matches, str(file_path))
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"BLOCKED: Secrets detected in content.\n\n{warning}",
                )

            # Warn if writing to a known secrets file
            if is_secret_file(str(file_path)):
                # Allow but warn - these files are meant for secrets
                pass

            # Check if parent directory exists
            if not file_path.parent.exists():
                if create_dirs:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                else:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"Parent directory does not exist: {file_path.parent}",
                    )

            # Check if path is a directory
            if file_path.exists() and file_path.is_dir():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Cannot write to directory: {path}",
                )

            # Track if this is a new file or overwrite
            is_new = not file_path.exists()
            old_content = None
            if not is_new:
                try:
                    old_content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            # Write the file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Calculate stats
            lines_written = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            bytes_written = len(content.encode("utf-8"))

            output = {
                "path": str(file_path),
                "action": "created" if is_new else "overwritten",
                "lines": lines_written,
                "bytes": bytes_written,
            }

            # SAFETY: Record the modification for blast radius tracking
            record_modification(str(file_path), lines_written)

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
                error=f"Error writing file: {e}",
            )

    def dry_run(self, path: str, content: str, create_dirs: bool = False) -> str:
        """Describe what would be written."""
        file_path = Path(path).resolve()
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        bytes_count = len(content.encode("utf-8"))
        exists = file_path.exists()

        action = "Overwrite" if exists else "Create"
        return f"{action} {file_path} ({lines} lines, {bytes_count} bytes)"

    def preview(self, path: str, content: str) -> dict:
        """Generate a preview of the write operation."""
        file_path = Path(path).resolve()
        exists = file_path.exists()

        preview = {
            "path": str(file_path),
            "exists": exists,
            "action": "overwrite" if exists else "create",
            "new_content": content,
            "old_content": None,
            "diff": None,
        }

        if exists:
            try:
                old_content = file_path.read_text(encoding="utf-8", errors="replace")
                preview["old_content"] = old_content

                # Generate simple diff
                old_lines = old_content.splitlines(keepends=True)
                new_lines = content.splitlines(keepends=True)

                import difflib
                diff = list(difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{file_path.name}",
                    tofile=f"b/{file_path.name}",
                ))
                preview["diff"] = "".join(diff)
            except Exception:
                pass

        return preview


@dataclass
class FsEditTool(Tool):
    """Edit a file via search/replace."""

    name: str = "fs.edit"
    description: str = "Edit a file by replacing text (search/replace)"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the file to edit", required=True),
        ToolParam("old_text", str, "Text to search for", required=True),
        ToolParam("new_text", str, "Text to replace with", required=True),
        ToolParam("replace_all", bool, "Replace all occurrences", required=False, default=False),
    ])

    def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> ToolResult:
        """Edit file by replacing text."""
        try:
            file_path = Path(path).resolve()

            # SAFETY: Check if writes are allowed (readonly/dry-run mode)
            write_allowed, write_error = check_write_allowed()
            if not write_allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=write_error,
                )

            # SAFETY: Check if path is allowed
            path_allowed, path_error = check_path_allowed(str(file_path))
            if not path_allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"BLOCKED: {path_error}",
                )

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

            # Read current content
            content = file_path.read_text(encoding="utf-8", errors="replace")

            # Check if old_text exists
            count = content.count(old_text)
            if count == 0:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Text not found in file: {repr(old_text[:50])}{'...' if len(old_text) > 50 else ''}",
                )

            # Check for ambiguity (multiple matches when replace_all=False)
            if count > 1 and not replace_all:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Text found {count} times. Use --replace-all to replace all occurrences, or provide more context to make it unique.",
                )

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_text, new_text)
                replacements = count
            else:
                new_content = content.replace(old_text, new_text, 1)
                replacements = 1

            # Calculate lines changed for blast radius tracking
            old_lines = content.count("\n")
            new_lines = new_content.count("\n")
            lines_changed = abs(new_lines - old_lines) + replacements  # Approximate LOC change

            # SAFETY: Check blast radius limits
            mod_allowed, mod_error = check_modification_allowed(str(file_path), lines_changed)
            if not mod_allowed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"BLOCKED: {mod_error}",
                )

            # SECURITY: Check for secrets before writing
            is_safe, secret_matches = check_before_write(new_content, str(file_path))
            if not is_safe:
                warning = format_secret_warning(secret_matches, str(file_path))
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"BLOCKED: Secrets detected in edited content.\n\n{warning}",
                )

            # Write back
            file_path.write_text(new_content, encoding="utf-8")

            # SAFETY: Record the modification for blast radius tracking
            record_modification(str(file_path), lines_changed)

            output = {
                "path": str(file_path),
                "replacements": replacements,
                "old_text_preview": old_text[:100] + ("..." if len(old_text) > 100 else ""),
                "new_text_preview": new_text[:100] + ("..." if len(new_text) > 100 else ""),
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
                error=f"Error editing file: {e}",
            )

    def dry_run(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> str:
        """Describe what would be edited."""
        file_path = Path(path).resolve()
        mode = "all occurrences" if replace_all else "first occurrence"
        old_preview = old_text[:30] + ("..." if len(old_text) > 30 else "")
        new_preview = new_text[:30] + ("..." if len(new_text) > 30 else "")
        return f"Would replace {mode} of {repr(old_preview)} with {repr(new_preview)} in {file_path}"

    def preview(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> dict:
        """Generate a preview of the edit operation."""
        file_path = Path(path).resolve()

        preview = {
            "path": str(file_path),
            "exists": file_path.exists(),
            "old_text": old_text,
            "new_text": new_text,
            "occurrences": 0,
            "would_replace": 0,
            "error": None,
            "diff": None,
            "old_content": None,
            "new_content": None,
        }

        if not file_path.exists():
            preview["error"] = f"File not found: {path}"
            return preview

        if not file_path.is_file():
            preview["error"] = f"Not a file: {path}"
            return preview

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            preview["old_content"] = content

            count = content.count(old_text)
            preview["occurrences"] = count

            if count == 0:
                preview["error"] = "Text not found"
                return preview

            if count > 1 and not replace_all:
                preview["error"] = f"Text found {count} times (ambiguous)"
                preview["would_replace"] = 0
            else:
                preview["would_replace"] = count if replace_all else 1

            # Generate new content for diff
            if replace_all:
                new_content = content.replace(old_text, new_text)
            else:
                new_content = content.replace(old_text, new_text, 1)

            preview["new_content"] = new_content

            # Generate diff
            import difflib
            old_lines = content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
            ))
            preview["diff"] = "".join(diff)

        except Exception as e:
            preview["error"] = str(e)

        return preview


# Create tool instances
fs_read = FsReadTool()
fs_list = FsListTool()
fs_write = FsWriteTool()
fs_edit = FsEditTool()

# Register tools
registry.register(fs_read)
registry.register(fs_list)
registry.register(fs_write)
registry.register(fs_edit)


def read_file(path: str, offset: int = 1, lines: int = 0) -> ToolResult:
    """Convenience function to read a file."""
    return fs_read.execute(path=path, offset=offset, lines=lines)


def list_directory(path: str, show_all: bool = False) -> ToolResult:
    """Convenience function to list a directory."""
    return fs_list.execute(path=path, all=show_all)


def write_file(path: str, content: str, create_dirs: bool = False) -> ToolResult:
    """Convenience function to write a file."""
    return fs_write.execute(path=path, content=content, create_dirs=create_dirs)


def edit_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> ToolResult:
    """Convenience function to edit a file."""
    return fs_edit.execute(path=path, old_text=old_text, new_text=new_text, replace_all=replace_all)
