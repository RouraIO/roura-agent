"""
Roura Agent Tools - CLI-callable, approval-gated tools.

© Roura.io
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
from .schema import (
    tool_to_json_schema,
    tools_to_json_schema,
    registry_to_json_schema,
    get_tool_names,
    get_tool_descriptions,
)
from .glob import glob_tool, find_files
from .grep import grep_tool, search_files
from .memory import memory_store, memory_recall, memory_clear, store_note, recall_notes, clear_memory
from .webfetch import web_fetch, web_search, fetch_webpage, search_web

# New Phase 1 tools: Testing, Building, Linting
from .testing import (
    TestRunTool,
    TestFailuresTool,
    TestLastTool,
    TestCoverageTool,
    TestFixTool,
    TestWatchTool,
    run_tests,
    detect_test_framework,
)
from .build import (
    BuildRunTool,
    BuildErrorsTool,
    BuildCleanTool,
    BuildFixTool,
    BuildWatchTool,
    run_build,
    detect_build_system,
)
from .lint import (
    LintRunTool,
    LintFixTool,
    FormatRunTool,
    FormatCheckTool,
    TypecheckRunTool,
    TypecheckFixTool,
    run_lint,
    detect_linter,
    detect_formatter,
    detect_typechecker,
)

# Phase 6: Claude Code Feature Parity
from .mcp import (
    MCPManager,
    MCPServer,
    MCPServerConfig,
    MCPServerStatus,
    MCPTransportType,
    MCPToolDefinition,
    MCPResourceDefinition,
    MCPPromptDefinition,
    MCPListServersTool,
    MCPListToolsTool,
    MCPCallToolTool,
    MCPConnectTool,
    MCPDisconnectTool,
    get_mcp_manager,
    list_mcp_servers,
    list_mcp_tools,
    call_mcp_tool,
)
from .image import (
    ImageData,
    ImageSource,
    ImageInfo,
    ImageAnalyzer,
    ImageReadTool,
    ImageAnalyzeTool,
    ImageCompareTool,
    ImageToBase64Tool,
    ImageFromUrlTool,
    get_image_analyzer,
    set_image_analyzer,
    create_vision_callback,
    read_image,
    analyze_image,
    compare_images,
)
from .notebook import (
    Notebook,
    NotebookCell,
    CellType,
    NotebookExecutor,
    NotebookReadTool,
    NotebookEditTool,
    NotebookAddCellTool,
    NotebookRemoveCellTool,
    NotebookExecuteTool,
    NotebookCreateTool,
    NotebookToPythonTool,
    NotebookClearOutputsTool,
    get_notebook_executor,
    read_notebook,
    edit_notebook_cell,
    execute_notebook,
    create_notebook,
)
from .project import (
    analyze_project,
    find_related_files,
    get_project_summary,
    project_analyze,
    project_related,
    project_summary,
)
from .review import (
    review_file,
    review_diff,
    review_project,
    suggest_fixes,
    code_review_file,
    code_review_diff,
    code_review_project,
    code_suggest_fixes,
)

__all__ = [
    # Base
    "Tool",
    "ToolResult",
    "ToolParam",
    "RiskLevel",
    "ToolRegistry",
    "registry",
    # Schema
    "tool_to_json_schema",
    "tools_to_json_schema",
    "registry_to_json_schema",
    "get_tool_names",
    "get_tool_descriptions",
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
    # Glob & Grep
    "glob_tool",
    "find_files",
    "grep_tool",
    "search_files",
    # Memory
    "memory_store",
    "memory_recall",
    "memory_clear",
    "store_note",
    "recall_notes",
    "clear_memory",
    # Web
    "web_fetch",
    "web_search",
    "fetch_webpage",
    "search_web",
    # Testing
    "TestRunTool",
    "TestFailuresTool",
    "TestLastTool",
    "TestCoverageTool",
    "TestFixTool",
    "TestWatchTool",
    "run_tests",
    "detect_test_framework",
    # Build
    "BuildRunTool",
    "BuildErrorsTool",
    "BuildCleanTool",
    "BuildFixTool",
    "BuildWatchTool",
    "run_build",
    "detect_build_system",
    # Lint & Format
    "LintRunTool",
    "LintFixTool",
    "FormatRunTool",
    "FormatCheckTool",
    "TypecheckRunTool",
    "TypecheckFixTool",
    "run_lint",
    "detect_linter",
    "detect_formatter",
    "detect_typechecker",
    # MCP Server Support (Phase 6)
    "MCPManager",
    "MCPServer",
    "MCPServerConfig",
    "MCPServerStatus",
    "MCPTransportType",
    "MCPToolDefinition",
    "MCPResourceDefinition",
    "MCPPromptDefinition",
    "MCPListServersTool",
    "MCPListToolsTool",
    "MCPCallToolTool",
    "MCPConnectTool",
    "MCPDisconnectTool",
    "get_mcp_manager",
    "list_mcp_servers",
    "list_mcp_tools",
    "call_mcp_tool",
    # Image Understanding (Phase 6)
    "ImageData",
    "ImageSource",
    "ImageInfo",
    "ImageAnalyzer",
    "ImageReadTool",
    "ImageAnalyzeTool",
    "ImageCompareTool",
    "ImageToBase64Tool",
    "ImageFromUrlTool",
    "get_image_analyzer",
    "set_image_analyzer",
    "create_vision_callback",
    "read_image",
    "analyze_image",
    "compare_images",
    # Jupyter Notebook Support (Phase 6)
    "Notebook",
    "NotebookCell",
    "CellType",
    "NotebookExecutor",
    "NotebookReadTool",
    "NotebookEditTool",
    "NotebookAddCellTool",
    "NotebookRemoveCellTool",
    "NotebookExecuteTool",
    "NotebookCreateTool",
    "NotebookToPythonTool",
    "NotebookClearOutputsTool",
    "get_notebook_executor",
    "read_notebook",
    "edit_notebook_cell",
    "execute_notebook",
    "create_notebook",
    # Project Analysis (Phase 7)
    "analyze_project",
    "find_related_files",
    "get_project_summary",
    "project_analyze",
    "project_related",
    "project_summary",
    # Code Review (Phase 7)
    "review_file",
    "review_diff",
    "review_project",
    "suggest_fixes",
    "code_review_file",
    "code_review_diff",
    "code_review_project",
    "code_suggest_fixes",
]
