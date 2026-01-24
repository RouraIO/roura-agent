"""
Roura Agent Tools - CLI-callable, approval-gated tools.
"""
from .base import Tool, ToolResult, ToolParam, RiskLevel, ToolRegistry, registry
from .doctor import run_all_checks, format_results, has_critical_failures
from .fs import fs_read, fs_list, fs_write, fs_edit, read_file, list_directory, write_file, edit_file
from .git import (
    git_status, git_diff, git_log, git_add, git_commit,
    get_status, get_diff, get_log, stage_files, create_commit,
)
from .shell import shell_exec, shell_background, run_command, run_background
from .github import (
    github_pr_list, github_pr_view, github_pr_create,
    github_issue_list, github_issue_view, github_issue_create,
    github_repo_view,
)
from .jira import (
    jira_search, jira_issue, jira_create,
    jira_transition, jira_comment, jira_my_issues,
)

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
    "git_add",
    "git_commit",
    "get_status",
    "get_diff",
    "get_log",
    "stage_files",
    "create_commit",
    # Shell
    "shell_exec",
    "shell_background",
    "run_command",
    "run_background",
]
