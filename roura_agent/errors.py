"""
Roura Agent Errors - User-friendly error messages with recovery hints.

This module provides a centralized error handling system with:
- Error codes (ROURA-XXX format)
- User-friendly messages
- Recovery suggestions
- Troubleshooting links

Usage:
    from roura_agent.errors import RouraError, ErrorCode, get_error_message

    # Raise with error code
    raise RouraError(ErrorCode.OLLAMA_CONNECTION_FAILED)

    # Get friendly message
    message = get_error_message(ErrorCode.FILE_NOT_FOUND, path="/some/file.py")

"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ErrorCode(Enum):
    """Error codes for Roura Agent.

    Format: ROURA-XXX
    - 0xx: Configuration errors
    - 1xx: Ollama/LLM errors
    - 2xx: File system errors
    - 3xx: Git errors
    - 4xx: Shell/command errors
    - 5xx: Integration errors (GitHub, Jira)
    - 6xx: Agent loop errors
    - 9xx: Internal errors
    """
    # Configuration errors (0xx)
    CONFIG_NOT_FOUND = "ROURA-001"
    CONFIG_INVALID = "ROURA-002"
    MODEL_NOT_SET = "ROURA-003"
    CREDENTIALS_NOT_FOUND = "ROURA-004"
    API_KEY_NOT_SET = "ROURA-005"
    API_KEY_INVALID = "ROURA-006"
    PROVIDER_NOT_AVAILABLE = "ROURA-007"

    # Ollama/LLM errors (1xx)
    OLLAMA_CONNECTION_FAILED = "ROURA-101"
    OLLAMA_TIMEOUT = "ROURA-102"
    OLLAMA_MODEL_NOT_FOUND = "ROURA-103"
    OLLAMA_INVALID_RESPONSE = "ROURA-104"
    OLLAMA_STREAMING_FAILED = "ROURA-105"
    LLM_RATE_LIMITED = "ROURA-106"
    RATE_LIMIT_EXCEEDED = "ROURA-106"  # Alias for LLM_RATE_LIMITED
    LLM_CONTEXT_TOO_LONG = "ROURA-107"

    # File system errors (2xx)
    FILE_NOT_FOUND = "ROURA-201"
    FILE_PERMISSION_DENIED = "ROURA-202"
    FILE_NOT_READABLE = "ROURA-203"
    FILE_NOT_WRITABLE = "ROURA-204"
    DIRECTORY_NOT_FOUND = "ROURA-205"
    PATH_OUTSIDE_PROJECT = "ROURA-206"
    FILE_ENCODING_ERROR = "ROURA-207"
    FILE_TOO_LARGE = "ROURA-208"
    FILE_NOT_READ_FIRST = "ROURA-209"

    # Git errors (3xx)
    GIT_NOT_A_REPO = "ROURA-301"
    GIT_COMMAND_FAILED = "ROURA-302"
    GIT_NOTHING_TO_COMMIT = "ROURA-303"
    GIT_MERGE_CONFLICT = "ROURA-304"
    GIT_DETACHED_HEAD = "ROURA-305"
    GIT_UNCOMMITTED_CHANGES = "ROURA-306"

    # Shell errors (4xx)
    SHELL_COMMAND_BLOCKED = "ROURA-401"
    SHELL_TIMEOUT = "ROURA-402"
    SHELL_PERMISSION_DENIED = "ROURA-403"
    SHELL_COMMAND_NOT_FOUND = "ROURA-404"

    # Integration errors (5xx)
    GITHUB_NOT_AUTHENTICATED = "ROURA-501"
    GITHUB_API_ERROR = "ROURA-502"
    JIRA_NOT_CONFIGURED = "ROURA-503"
    JIRA_AUTH_FAILED = "ROURA-504"
    JIRA_API_ERROR = "ROURA-505"

    # Agent loop errors (6xx)
    AGENT_MAX_ITERATIONS = "ROURA-601"
    AGENT_MAX_TOOL_CALLS = "ROURA-602"
    AGENT_TOOL_NOT_FOUND = "ROURA-603"
    AGENT_APPROVAL_REJECTED = "ROURA-604"
    AGENT_INTERRUPTED = "ROURA-605"
    AGENT_CONTEXT_OVERFLOW = "ROURA-606"

    # Internal errors (9xx)
    INTERNAL_ERROR = "ROURA-901"
    UNEXPECTED_ERROR = "ROURA-999"


@dataclass
class ErrorInfo:
    """Detailed error information."""
    code: ErrorCode
    message: str
    hint: str
    docs_url: Optional[str] = None


# Error catalog with user-friendly messages and hints
ERROR_CATALOG: dict[ErrorCode, ErrorInfo] = {
    # Configuration errors
    ErrorCode.CONFIG_NOT_FOUND: ErrorInfo(
        code=ErrorCode.CONFIG_NOT_FOUND,
        message="Configuration file not found",
        hint="Run 'roura-agent setup' to create a configuration file",
        docs_url="https://docs.roura.io/setup",
    ),
    ErrorCode.CONFIG_INVALID: ErrorInfo(
        code=ErrorCode.CONFIG_INVALID,
        message="Configuration file is invalid or corrupted",
        hint="Check the config file at ~/.config/roura-agent/config.json or run 'roura-agent setup' to recreate it",
    ),
    ErrorCode.MODEL_NOT_SET: ErrorInfo(
        code=ErrorCode.MODEL_NOT_SET,
        message="No Ollama model configured",
        hint="Run 'roura-agent setup' to select a model, or set OLLAMA_MODEL environment variable",
    ),
    ErrorCode.CREDENTIALS_NOT_FOUND: ErrorInfo(
        code=ErrorCode.CREDENTIALS_NOT_FOUND,
        message="Required credentials not found",
        hint="Run 'roura-agent setup' to configure credentials",
    ),
    ErrorCode.API_KEY_NOT_SET: ErrorInfo(
        code=ErrorCode.API_KEY_NOT_SET,
        message="API key not configured",
        hint="Set the appropriate API key environment variable:\n- OPENAI_API_KEY for OpenAI\n- ANTHROPIC_API_KEY for Anthropic",
    ),
    ErrorCode.API_KEY_INVALID: ErrorInfo(
        code=ErrorCode.API_KEY_INVALID,
        message="API key is invalid or expired",
        hint="Check that your API key is correct and has not expired.\nYou can generate a new key from the provider's dashboard",
    ),
    ErrorCode.PROVIDER_NOT_AVAILABLE: ErrorInfo(
        code=ErrorCode.PROVIDER_NOT_AVAILABLE,
        message="The requested LLM provider is not available",
        hint="Ensure the provider is installed and configured. Use 'roura-agent doctor' to check provider availability",
    ),

    # Ollama/LLM errors
    ErrorCode.OLLAMA_CONNECTION_FAILED: ErrorInfo(
        code=ErrorCode.OLLAMA_CONNECTION_FAILED,
        message="Cannot connect to Ollama",
        hint="Make sure Ollama is running: 'ollama serve'\nCheck if Ollama is accessible at the configured URL",
        docs_url="https://docs.roura.io/troubleshooting#ollama",
    ),
    ErrorCode.OLLAMA_TIMEOUT: ErrorInfo(
        code=ErrorCode.OLLAMA_TIMEOUT,
        message="Ollama request timed out",
        hint="The model may be slow to respond. Try:\n- Using a smaller model\n- Increasing the timeout in config\n- Checking system resources",
    ),
    ErrorCode.OLLAMA_MODEL_NOT_FOUND: ErrorInfo(
        code=ErrorCode.OLLAMA_MODEL_NOT_FOUND,
        message="The specified model is not available in Ollama",
        hint="Pull the model first: 'ollama pull <model-name>'\nRun 'roura-agent ping' to see available models",
    ),
    ErrorCode.OLLAMA_INVALID_RESPONSE: ErrorInfo(
        code=ErrorCode.OLLAMA_INVALID_RESPONSE,
        message="Received an invalid response from Ollama",
        hint="The model may have returned malformed output. Try rephrasing your request or using a different model",
    ),
    ErrorCode.OLLAMA_STREAMING_FAILED: ErrorInfo(
        code=ErrorCode.OLLAMA_STREAMING_FAILED,
        message="Streaming response was interrupted",
        hint="The connection to Ollama was lost. Check your network and try again",
    ),
    ErrorCode.LLM_RATE_LIMITED: ErrorInfo(
        code=ErrorCode.LLM_RATE_LIMITED,
        message="Rate limit exceeded",
        hint="Wait a moment before trying again. Local Ollama doesn't have rate limits - this may be from a cloud provider",
    ),
    ErrorCode.LLM_CONTEXT_TOO_LONG: ErrorInfo(
        code=ErrorCode.LLM_CONTEXT_TOO_LONG,
        message="The conversation context is too long for the model",
        hint="Use '/clear' to reset the conversation, or use a model with a larger context window",
    ),

    # File system errors
    ErrorCode.FILE_NOT_FOUND: ErrorInfo(
        code=ErrorCode.FILE_NOT_FOUND,
        message="File not found",
        hint="Check that the file path is correct and the file exists",
    ),
    ErrorCode.FILE_PERMISSION_DENIED: ErrorInfo(
        code=ErrorCode.FILE_PERMISSION_DENIED,
        message="Permission denied when accessing file",
        hint="Check file permissions. You may need to run with appropriate privileges",
    ),
    ErrorCode.FILE_NOT_READABLE: ErrorInfo(
        code=ErrorCode.FILE_NOT_READABLE,
        message="Cannot read file",
        hint="The file may be binary, encrypted, or have restricted permissions",
    ),
    ErrorCode.FILE_NOT_WRITABLE: ErrorInfo(
        code=ErrorCode.FILE_NOT_WRITABLE,
        message="Cannot write to file",
        hint="Check that you have write permissions and the file is not locked",
    ),
    ErrorCode.DIRECTORY_NOT_FOUND: ErrorInfo(
        code=ErrorCode.DIRECTORY_NOT_FOUND,
        message="Directory not found",
        hint="Check that the directory path is correct. Use create_dirs=True to create parent directories",
    ),
    ErrorCode.PATH_OUTSIDE_PROJECT: ErrorInfo(
        code=ErrorCode.PATH_OUTSIDE_PROJECT,
        message="Path is outside the project directory",
        hint="For safety, Roura Agent only modifies files within the project. Use absolute paths within the project",
    ),
    ErrorCode.FILE_ENCODING_ERROR: ErrorInfo(
        code=ErrorCode.FILE_ENCODING_ERROR,
        message="Cannot decode file - encoding issue",
        hint="The file may not be UTF-8 encoded. Try specifying the encoding or check if it's a binary file",
    ),
    ErrorCode.FILE_TOO_LARGE: ErrorInfo(
        code=ErrorCode.FILE_TOO_LARGE,
        message="File is too large to process",
        hint="Consider reading specific line ranges with offset/lines parameters",
    ),
    ErrorCode.FILE_NOT_READ_FIRST: ErrorInfo(
        code=ErrorCode.FILE_NOT_READ_FIRST,
        message="Cannot modify a file that hasn't been read first",
        hint="This is a safety feature. Ask me to read the file first, then make modifications",
    ),

    # Git errors
    ErrorCode.GIT_NOT_A_REPO: ErrorInfo(
        code=ErrorCode.GIT_NOT_A_REPO,
        message="Not a git repository",
        hint="Initialize a git repo with 'git init' or navigate to a directory with a git repo",
    ),
    ErrorCode.GIT_COMMAND_FAILED: ErrorInfo(
        code=ErrorCode.GIT_COMMAND_FAILED,
        message="Git command failed",
        hint="Check the git output for details. Run 'git status' to see the repository state",
    ),
    ErrorCode.GIT_NOTHING_TO_COMMIT: ErrorInfo(
        code=ErrorCode.GIT_NOTHING_TO_COMMIT,
        message="Nothing to commit",
        hint="Stage some changes with 'git add' first, or there may be no modifications",
    ),
    ErrorCode.GIT_MERGE_CONFLICT: ErrorInfo(
        code=ErrorCode.GIT_MERGE_CONFLICT,
        message="Git merge conflict detected",
        hint="Resolve the conflicts manually, then stage and commit. I can help review conflict markers",
    ),
    ErrorCode.GIT_DETACHED_HEAD: ErrorInfo(
        code=ErrorCode.GIT_DETACHED_HEAD,
        message="Git repository is in detached HEAD state",
        hint="Create a new branch to save your work: 'git checkout -b <branch-name>'",
    ),
    ErrorCode.GIT_UNCOMMITTED_CHANGES: ErrorInfo(
        code=ErrorCode.GIT_UNCOMMITTED_CHANGES,
        message="You have uncommitted changes",
        hint="Commit or stash your changes before proceeding",
    ),

    # Shell errors
    ErrorCode.SHELL_COMMAND_BLOCKED: ErrorInfo(
        code=ErrorCode.SHELL_COMMAND_BLOCKED,
        message="Command is blocked for safety",
        hint="This command is in the blocklist for safety. If you need to run it, do so manually in your terminal",
    ),
    ErrorCode.SHELL_TIMEOUT: ErrorInfo(
        code=ErrorCode.SHELL_TIMEOUT,
        message="Command timed out",
        hint="The command took too long. Try increasing the timeout or running it directly in your terminal",
    ),
    ErrorCode.SHELL_PERMISSION_DENIED: ErrorInfo(
        code=ErrorCode.SHELL_PERMISSION_DENIED,
        message="Permission denied when running command",
        hint="You may need sudo/admin privileges. Run the command manually if appropriate",
    ),
    ErrorCode.SHELL_COMMAND_NOT_FOUND: ErrorInfo(
        code=ErrorCode.SHELL_COMMAND_NOT_FOUND,
        message="Command not found",
        hint="The command may not be installed. Install it or check your PATH",
    ),

    # Integration errors
    ErrorCode.GITHUB_NOT_AUTHENTICATED: ErrorInfo(
        code=ErrorCode.GITHUB_NOT_AUTHENTICATED,
        message="GitHub CLI not authenticated",
        hint="Run 'gh auth login' to authenticate with GitHub",
    ),
    ErrorCode.GITHUB_API_ERROR: ErrorInfo(
        code=ErrorCode.GITHUB_API_ERROR,
        message="GitHub API error",
        hint="Check your network connection and GitHub status. You may need to re-authenticate",
    ),
    ErrorCode.JIRA_NOT_CONFIGURED: ErrorInfo(
        code=ErrorCode.JIRA_NOT_CONFIGURED,
        message="Jira is not configured",
        hint="Run 'roura-agent setup' to configure Jira integration",
    ),
    ErrorCode.JIRA_AUTH_FAILED: ErrorInfo(
        code=ErrorCode.JIRA_AUTH_FAILED,
        message="Jira authentication failed",
        hint="Check your Jira credentials. You may need to regenerate your API token at https://id.atlassian.com/manage-profile/security/api-tokens",
    ),
    ErrorCode.JIRA_API_ERROR: ErrorInfo(
        code=ErrorCode.JIRA_API_ERROR,
        message="Jira API error",
        hint="Check your network and Jira instance status. The project or issue may not exist",
    ),

    # Agent loop errors
    ErrorCode.AGENT_MAX_ITERATIONS: ErrorInfo(
        code=ErrorCode.AGENT_MAX_ITERATIONS,
        message="Maximum iterations reached",
        hint="The task may be too complex. Try breaking it into smaller steps or use '/clear' to reset",
    ),
    ErrorCode.AGENT_MAX_TOOL_CALLS: ErrorInfo(
        code=ErrorCode.AGENT_MAX_TOOL_CALLS,
        message="Tool call limit reached for this turn",
        hint="Send another message to continue, or increase max_tool_calls_per_turn in config",
    ),
    ErrorCode.AGENT_TOOL_NOT_FOUND: ErrorInfo(
        code=ErrorCode.AGENT_TOOL_NOT_FOUND,
        message="Tool not found",
        hint="Run '/tools' to see available tools",
    ),
    ErrorCode.AGENT_APPROVAL_REJECTED: ErrorInfo(
        code=ErrorCode.AGENT_APPROVAL_REJECTED,
        message="Operation was not approved",
        hint="The operation was skipped. You can approve with 'yes' or skip with 'no'",
    ),
    ErrorCode.AGENT_INTERRUPTED: ErrorInfo(
        code=ErrorCode.AGENT_INTERRUPTED,
        message="Operation was interrupted",
        hint="You pressed ESC to interrupt. The partial progress has been preserved",
    ),
    ErrorCode.AGENT_CONTEXT_OVERFLOW: ErrorInfo(
        code=ErrorCode.AGENT_CONTEXT_OVERFLOW,
        message="Context window overflow",
        hint="The conversation is too long. Use '/clear' to reset or let auto-summarization compress it",
    ),

    # Internal errors
    ErrorCode.INTERNAL_ERROR: ErrorInfo(
        code=ErrorCode.INTERNAL_ERROR,
        message="An internal error occurred",
        hint="This is a bug. Please report it at https://github.com/roura-io/roura-agent/issues",
    ),
    ErrorCode.UNEXPECTED_ERROR: ErrorInfo(
        code=ErrorCode.UNEXPECTED_ERROR,
        message="An unexpected error occurred",
        hint="Check the logs for details. If this persists, please report it",
    ),
}


class RouraError(Exception):
    """Base exception for Roura Agent errors.

    Provides user-friendly error messages with recovery hints.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        hint: str | None = None,
        details: dict | None = None,
        cause: Exception | None = None,
    ):
        self.code = code
        self.details = details or {}
        self.cause = cause

        # Get info from catalog
        info = ERROR_CATALOG.get(code)
        if info:
            self.message = message or info.message
            self.hint = hint or info.hint
            self.docs_url = info.docs_url
        else:
            self.message = message or "An error occurred"
            self.hint = hint or "Check the logs for more details"
            self.docs_url = None

        # Format message with details
        if details:
            for key, value in details.items():
                self.message = self.message.replace(f"{{{key}}}", str(value))
                self.hint = self.hint.replace(f"{{{key}}}", str(value))

        super().__init__(f"[{code.value}] {self.message}")

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def format_for_user(self) -> str:
        """Format error message for display to user."""
        from .branding import Colors, Icons

        lines = [f"[{Colors.ERROR}]{Icons.ERROR} Error ({self.code.value})[/{Colors.ERROR}]: {self.message}"]

        if self.hint:
            lines.append(f"\n[{Colors.DIM}]Hint: {self.hint}[/{Colors.DIM}]")

        if self.docs_url:
            lines.append(f"\n[{Colors.DIM}]Docs: {self.docs_url}[/{Colors.DIM}]")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert error to dictionary for logging/JSON output."""
        return {
            "code": self.code.value,
            "message": self.message,
            "hint": self.hint,
            "docs_url": self.docs_url,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


# Convenience functions for common error patterns


def get_error_message(code: ErrorCode, **kwargs) -> str:
    """Get a formatted error message for a given error code."""
    error = RouraError(code, details=kwargs)
    return error.format_for_user()


def get_error_hint(code: ErrorCode) -> str | None:
    """Get the recovery hint for an error code."""
    info = ERROR_CATALOG.get(code)
    return info.hint if info else None


def wrap_exception(
    exc: Exception,
    code: ErrorCode,
    message: str | None = None,
) -> RouraError:
    """Wrap a standard exception in a RouraError."""
    return RouraError(code=code, message=message, cause=exc)


# Exception handlers for common patterns


def handle_connection_error(exc: Exception, url: str) -> RouraError:
    """Handle connection errors with appropriate error code."""
    if "Connection refused" in str(exc) or "Connection error" in str(exc):
        return RouraError(
            ErrorCode.OLLAMA_CONNECTION_FAILED,
            details={"url": url},
            cause=exc,
        )
    elif "timeout" in str(exc).lower():
        return RouraError(ErrorCode.OLLAMA_TIMEOUT, cause=exc)
    else:
        return RouraError(ErrorCode.UNEXPECTED_ERROR, message=str(exc), cause=exc)


def handle_file_error(exc: Exception, path: str) -> RouraError:
    """Handle file operation errors with appropriate error code."""
    exc_str = str(exc).lower()

    if isinstance(exc, FileNotFoundError) or "no such file" in exc_str:
        return RouraError(
            ErrorCode.FILE_NOT_FOUND,
            message=f"File not found: {path}",
            cause=exc,
        )
    elif isinstance(exc, PermissionError) or "permission denied" in exc_str:
        return RouraError(
            ErrorCode.FILE_PERMISSION_DENIED,
            message=f"Permission denied: {path}",
            cause=exc,
        )
    elif isinstance(exc, UnicodeDecodeError):
        return RouraError(
            ErrorCode.FILE_ENCODING_ERROR,
            message=f"Cannot decode file: {path}",
            cause=exc,
        )
    elif isinstance(exc, IsADirectoryError):
        return RouraError(
            ErrorCode.FILE_NOT_FOUND,
            message=f"Expected a file but found a directory: {path}",
            cause=exc,
        )
    else:
        return RouraError(
            ErrorCode.UNEXPECTED_ERROR,
            message=f"Error accessing {path}: {exc}",
            cause=exc,
        )


def handle_git_error(exc: Exception, operation: str) -> RouraError:
    """Handle git errors with appropriate error code."""
    exc_str = str(exc).lower()

    if "not a git repository" in exc_str:
        return RouraError(ErrorCode.GIT_NOT_A_REPO, cause=exc)
    elif "nothing to commit" in exc_str:
        return RouraError(ErrorCode.GIT_NOTHING_TO_COMMIT, cause=exc)
    elif "merge conflict" in exc_str or "conflict" in exc_str:
        return RouraError(ErrorCode.GIT_MERGE_CONFLICT, cause=exc)
    elif "detached head" in exc_str:
        return RouraError(ErrorCode.GIT_DETACHED_HEAD, cause=exc)
    else:
        return RouraError(
            ErrorCode.GIT_COMMAND_FAILED,
            message=f"Git {operation} failed: {exc}",
            cause=exc,
        )


# Troubleshooting guide mapping
TROUBLESHOOTING = {
    "ollama": """
## Ollama Connection Issues

1. **Check if Ollama is running**
   ```bash
   ollama serve
   ```

2. **Verify the model is downloaded**
   ```bash
   ollama list
   ollama pull qwen2.5-coder:32b
   ```

3. **Test the connection**
   ```bash
   roura-agent ping
   ```

4. **Check the configured URL**
   - Default: http://localhost:11434
   - Custom: Set OLLAMA_BASE_URL environment variable
""",

    "github": """
## GitHub Integration Issues

1. **Check GitHub CLI authentication**
   ```bash
   gh auth status
   ```

2. **Authenticate if needed**
   ```bash
   gh auth login
   ```

3. **Verify permissions**
   - Make sure you have access to the repository
   - Check if your token has the required scopes
""",

    "jira": """
## Jira Integration Issues

1. **Generate an API token**
   - Go to: https://id.atlassian.com/manage-profile/security/api-tokens
   - Create a new token

2. **Configure Roura Agent**
   ```bash
   roura-agent setup
   ```

3. **Common issues**
   - Ensure the Jira URL is correct (e.g., https://company.atlassian.net)
   - Use your email address, not username
   - API token, not password
""",

    "files": """
## File Access Issues

1. **Check permissions**
   ```bash
   ls -la <file>
   ```

2. **Verify file exists**
   - Use absolute paths for clarity
   - Check for typos in the path

3. **File not read first error**
   - Ask the agent to read the file before modifying
   - This is a safety feature to prevent unintended changes
""",
}


def get_troubleshooting(topic: str) -> str | None:
    """Get troubleshooting guide for a topic."""
    return TROUBLESHOOTING.get(topic.lower())
