"""
Roura Agent Tools - CLI-callable, approval-gated tools.
"""
from .base import Tool, ToolResult, ToolParam, RiskLevel, ToolRegistry, registry
from .doctor import run_all_checks, format_results, has_critical_failures
from .fs import fs_read, fs_list, fs_write, fs_edit, read_file, list_directory, write_file, edit_file
from .git import git_status, git_diff, git_log, get_status, get_diff, get_log

__all__ = [
    # Base
    "Tool",
    "ToolResult",
    "ToolParam",
    "RiskLevel",
    "ToolRegistry",
    "registry",
    # Doctor
    "run_all_checks",
    "format_results",
    "has_critical_failures",
    # Filesystem
    "fs_read",
    "fs_list",
    "fs_write",
    "fs_edit",
    "read_file",
    "list_directory",
    "write_file",
    "edit_file",
    # Git
    "git_status",
    "git_diff",
    "git_log",
    "get_status",
    "get_diff",
    "get_log",
]
