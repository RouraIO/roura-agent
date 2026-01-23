"""
Roura Agent Tools - CLI-callable, approval-gated tools.
"""
from .base import Tool, ToolResult, ToolParam, RiskLevel, ToolRegistry, registry
from .doctor import run_all_checks, format_results, has_critical_failures
from .fs import fs_read, fs_list, read_file, list_directory

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
    "read_file",
    "list_directory",
]
