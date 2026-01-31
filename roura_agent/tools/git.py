"""
Roura Agent Git Tools.

© Roura.io
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..secrets import check_before_commit, format_secret_warning
from .base import RiskLevel, Tool, ToolParam, ToolResult, registry


def run_git_command(args: list[str], cwd: Optional[str] = None) -> tuple[bool, str, str]:
    """
    Run a git command and return (success, stdout, stderr).
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        return (
            result.returncode == 0,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except FileNotFoundError:
        return False, "", "git not found in PATH"
    except Exception as e:
        return False, "", str(e)


def get_repo_root(cwd: Optional[str] = None) -> Optional[str]:
    """Get the root of the git repository."""
    success, stdout, _ = run_git_command(["rev-parse", "--show-toplevel"], cwd=cwd)
    return stdout if success else None


@dataclass
class GitStatusTool(Tool):
    """Show git working tree status."""

    name: str = "git.status"
    description: str = "Show the working tree status"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to repository (default: current directory)", required=False, default="."),
    ])

    def execute(self, path: str = ".") -> ToolResult:
        """Get git status."""
        repo_root = get_repo_root(cwd=path)
        if not repo_root:
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a git repository: {path}",
            )

        # Get porcelain status for parsing
        success, stdout, stderr = run_git_command(
            ["status", "--porcelain", "-b"],
            cwd=path,
        )

        if not success:
            return ToolResult(
                success=False,
                output=None,
                error=f"git status failed: {stderr}",
            )

        # Parse status
        lines = stdout.splitlines()
        branch = None
        staged = []
        modified = []
        untracked = []

        for line in lines:
            if line.startswith("##"):
                # Branch line: ## main...origin/main
                branch_part = line[3:].split("...")[0]
                branch = branch_part
            elif line:
                status_code = line[:2]
                filename = line[3:]

                # Index status (first char)
                if status_code[0] in "MADRC":
                    staged.append({"status": status_code[0], "file": filename})

                # Worktree status (second char)
                if status_code[1] == "M":
                    modified.append(filename)
                elif status_code[1] == "?":
                    untracked.append(filename)
                elif status_code[1] == "D":
                    modified.append(filename)

        # Get human-readable status too
        _, human_status, _ = run_git_command(["status", "--short"], cwd=path)

        output = {
            "repo_root": repo_root,
            "branch": branch,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "clean": len(staged) == 0 and len(modified) == 0 and len(untracked) == 0,
            "status_short": human_status,
        }

        return ToolResult(success=True, output=output)

    def dry_run(self, path: str = ".") -> str:
        """Describe what would be shown."""
        return f"Would show git status for {Path(path).resolve()}"


@dataclass
class GitDiffTool(Tool):
    """Show git diff."""

    name: str = "git.diff"
    description: str = "Show changes between commits, commit and working tree, etc."
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to repository or file", required=False, default="."),
        ToolParam("staged", bool, "Show staged changes (--cached)", required=False, default=False),
        ToolParam("commit", str, "Compare against specific commit", required=False, default=None),
    ])

    def execute(
        self,
        path: str = ".",
        staged: bool = False,
        commit: Optional[str] = None,
    ) -> ToolResult:
        """Get git diff."""
        # Determine if path is a file or directory
        path_obj = Path(path).resolve()
        if path_obj.is_file():
            cwd = str(path_obj.parent)
            target = str(path_obj)
        else:
            cwd = path
            target = None

        repo_root = get_repo_root(cwd=cwd)
        if not repo_root:
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a git repository: {path}",
            )

        # Build diff command
        args = ["diff"]
        if staged:
            args.append("--cached")
        if commit:
            args.append(commit)
        if target:
            args.extend(["--", target])

        success, stdout, stderr = run_git_command(args, cwd=cwd)

        if not success:
            return ToolResult(
                success=False,
                output=None,
                error=f"git diff failed: {stderr}",
            )

        # Get stats
        stat_args = ["diff", "--stat"]
        if staged:
            stat_args.append("--cached")
        if commit:
            stat_args.append(commit)
        if target:
            stat_args.extend(["--", target])

        _, stat_stdout, _ = run_git_command(stat_args, cwd=cwd)

        output = {
            "repo_root": repo_root,
            "staged": staged,
            "commit": commit,
            "diff": stdout,
            "stat": stat_stdout,
            "has_changes": len(stdout) > 0,
        }

        return ToolResult(success=True, output=output)

    def dry_run(
        self,
        path: str = ".",
        staged: bool = False,
        commit: Optional[str] = None,
    ) -> str:
        """Describe what would be shown."""
        diff_type = "staged" if staged else "unstaged"
        if commit:
            return f"Would show diff against {commit} for {Path(path).resolve()}"
        return f"Would show {diff_type} diff for {Path(path).resolve()}"


@dataclass
class GitLogTool(Tool):
    """Show git commit history."""

    name: str = "git.log"
    description: str = "Show commit logs"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to repository", required=False, default="."),
        ToolParam("count", int, "Number of commits to show", required=False, default=10),
        ToolParam("oneline", bool, "Show one line per commit", required=False, default=False),
    ])

    def execute(
        self,
        path: str = ".",
        count: int = 10,
        oneline: bool = False,
    ) -> ToolResult:
        """Get git log."""
        repo_root = get_repo_root(cwd=path)
        if not repo_root:
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a git repository: {path}",
            )

        # Build log command
        args = ["log", f"-{count}"]
        if oneline:
            args.append("--oneline")
        else:
            args.append("--format=%H%n%an%n%ae%n%ai%n%s%n%b%n---COMMIT---")

        success, stdout, stderr = run_git_command(args, cwd=path)

        if not success:
            return ToolResult(
                success=False,
                output=None,
                error=f"git log failed: {stderr}",
            )

        # Parse commits
        commits = []
        if oneline:
            for line in stdout.splitlines():
                if line:
                    parts = line.split(" ", 1)
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                    })
        else:
            raw_commits = stdout.split("---COMMIT---")
            for raw in raw_commits:
                lines = raw.strip().splitlines()
                if len(lines) >= 5:
                    commits.append({
                        "hash": lines[0],
                        "author": lines[1],
                        "email": lines[2],
                        "date": lines[3],
                        "subject": lines[4],
                        "body": "\n".join(lines[5:]).strip() if len(lines) > 5 else "",
                    })

        output = {
            "repo_root": repo_root,
            "count": len(commits),
            "commits": commits,
        }

        return ToolResult(success=True, output=output)

    def dry_run(
        self,
        path: str = ".",
        count: int = 10,
        oneline: bool = False,
    ) -> str:
        """Describe what would be shown."""
        return f"Would show last {count} commits for {Path(path).resolve()}"


@dataclass
class GitAddTool(Tool):
    """Stage files for commit."""

    name: str = "git.add"
    description: str = "Stage files for commit"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("files", list, "Files to stage (list of paths)", required=True),
        ToolParam("path", str, "Path to repository", required=False, default="."),
    ])

    def execute(
        self,
        files: list[str],
        path: str = ".",
    ) -> ToolResult:
        """Stage files for commit."""
        repo_root = get_repo_root(cwd=path)
        if not repo_root:
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a git repository: {path}",
            )

        if not files:
            return ToolResult(
                success=False,
                output=None,
                error="No files specified to add",
            )

        # Validate files exist
        missing = []
        for f in files:
            file_path = Path(path) / f if not Path(f).is_absolute() else Path(f)
            if not file_path.exists() and f != ".":
                missing.append(f)

        if missing:
            return ToolResult(
                success=False,
                output=None,
                error=f"Files not found: {', '.join(missing)}",
            )

        # Run git add
        success, stdout, stderr = run_git_command(["add"] + files, cwd=path)

        if not success:
            return ToolResult(
                success=False,
                output=None,
                error=f"git add failed: {stderr}",
            )

        # Get status to show what was staged
        _, status_out, _ = run_git_command(["status", "--porcelain"], cwd=path)
        staged = []
        for line in status_out.splitlines():
            if line and line[0] in "MADRC":
                staged.append({"status": line[0], "file": line[3:]})

        output = {
            "repo_root": repo_root,
            "files_requested": files,
            "staged": staged,
            "staged_count": len(staged),
        }

        return ToolResult(success=True, output=output)

    def dry_run(self, files: list[str], path: str = ".") -> str:
        """Describe what would be staged."""
        return f"Would stage {len(files)} file(s): {', '.join(files[:5])}{'...' if len(files) > 5 else ''}"

    def preview(self, files: list[str], path: str = ".") -> dict:
        """Preview what would be staged."""
        repo_root = get_repo_root(cwd=path)

        preview = {
            "repo_root": repo_root,
            "files": files,
            "would_stage": [],
            "errors": [],
        }

        if not repo_root:
            preview["errors"].append(f"Not a git repository: {path}")
            return preview

        # Check each file
        for f in files:
            file_path = Path(path) / f if not Path(f).is_absolute() else Path(f)
            if f == ".":
                # Get all unstaged/untracked files
                _, status_out, _ = run_git_command(["status", "--porcelain"], cwd=path)
                for line in status_out.splitlines():
                    if line and line[0] == "?" or line[1] in "MD":
                        preview["would_stage"].append(line[3:])
            elif file_path.exists():
                preview["would_stage"].append(f)
            else:
                preview["errors"].append(f"File not found: {f}")

        return preview


@dataclass
class GitCommitTool(Tool):
    """Create a commit."""

    name: str = "git.commit"
    description: str = "Create a commit with staged changes"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("message", str, "Commit message", required=True),
        ToolParam("path", str, "Path to repository", required=False, default="."),
    ])

    def execute(
        self,
        message: str,
        path: str = ".",
    ) -> ToolResult:
        """Create a commit."""
        repo_root = get_repo_root(cwd=path)
        if not repo_root:
            return ToolResult(
                success=False,
                output=None,
                error=f"Not a git repository: {path}",
            )

        if not message or not message.strip():
            return ToolResult(
                success=False,
                output=None,
                error="Commit message cannot be empty",
            )

        # Check if there are staged changes
        _, status_out, _ = run_git_command(["status", "--porcelain"], cwd=path)
        staged = [line for line in status_out.splitlines() if line and line[0] in "MADRC"]

        if not staged:
            return ToolResult(
                success=False,
                output=None,
                error="No staged changes to commit",
            )

        # SECURITY: Check staged files for secrets before commit
        staged_files = []
        for line in staged:
            # Extract file path from porcelain output (format: "XY filename" or "XY orig -> new")
            parts = line[3:].strip()
            if " -> " in parts:
                parts = parts.split(" -> ")[1]  # Use the new filename
            file_path = Path(repo_root) / parts
            if file_path.exists() and file_path.is_file():
                staged_files.append(str(file_path))

        secrets_found = check_before_commit(staged_files)
        if secrets_found:
            warnings = []
            for file_path, matches in secrets_found.items():
                warnings.append(format_secret_warning(matches, file_path))
            return ToolResult(
                success=False,
                output=None,
                error="BLOCKED: Secrets detected in staged files.\n\n" + "\n\n".join(warnings),
            )

        # Run git commit
        success, stdout, stderr = run_git_command(
            ["commit", "-m", message],
            cwd=path,
        )

        if not success:
            return ToolResult(
                success=False,
                output=None,
                error=f"git commit failed: {stderr}",
            )

        # Get the commit hash
        _, hash_out, _ = run_git_command(["rev-parse", "HEAD"], cwd=path)
        commit_hash = hash_out.strip()

        # Get commit info
        _, log_out, _ = run_git_command(
            ["log", "-1", "--format=%H%n%s%n%an%n%ai"],
            cwd=path,
        )
        log_lines = log_out.splitlines()

        output = {
            "repo_root": repo_root,
            "hash": commit_hash,
            "short_hash": commit_hash[:7],
            "message": message,
            "files_committed": len(staged),
            "author": log_lines[2] if len(log_lines) > 2 else None,
            "date": log_lines[3] if len(log_lines) > 3 else None,
        }

        return ToolResult(success=True, output=output)

    def dry_run(self, message: str, path: str = ".") -> str:
        """Describe what would be committed."""
        return f"Would create commit with message: {message[:50]}{'...' if len(message) > 50 else ''}"

    def preview(self, message: str, path: str = ".") -> dict:
        """Preview what would be committed."""
        repo_root = get_repo_root(cwd=path)

        preview = {
            "repo_root": repo_root,
            "message": message,
            "staged_files": [],
            "staged_diff": None,
            "error": None,
        }

        if not repo_root:
            preview["error"] = f"Not a git repository: {path}"
            return preview

        # Get staged files
        _, status_out, _ = run_git_command(["status", "--porcelain"], cwd=path)
        for line in status_out.splitlines():
            if line and line[0] in "MADRC":
                preview["staged_files"].append({"status": line[0], "file": line[3:]})

        if not preview["staged_files"]:
            preview["error"] = "No staged changes to commit"
            return preview

        # Get staged diff
        _, diff_out, _ = run_git_command(["diff", "--cached"], cwd=path)
        preview["staged_diff"] = diff_out

        return preview


# Create tool instances
git_status = GitStatusTool()
git_diff = GitDiffTool()
git_log = GitLogTool()
git_add = GitAddTool()
git_commit = GitCommitTool()

# Register tools
registry.register(git_status)
registry.register(git_diff)
registry.register(git_log)
registry.register(git_add)
registry.register(git_commit)


def get_status(path: str = ".") -> ToolResult:
    """Convenience function to get git status."""
    return git_status.execute(path=path)


def get_diff(path: str = ".", staged: bool = False, commit: Optional[str] = None) -> ToolResult:
    """Convenience function to get git diff."""
    return git_diff.execute(path=path, staged=staged, commit=commit)


def get_log(path: str = ".", count: int = 10, oneline: bool = False) -> ToolResult:
    """Convenience function to get git log."""
    return git_log.execute(path=path, count=count, oneline=oneline)


def stage_files(files: list[str], path: str = ".") -> ToolResult:
    """Convenience function to stage files."""
    return git_add.execute(files=files, path=path)


def create_commit(message: str, path: str = ".") -> ToolResult:
    """Convenience function to create a commit."""
    return git_commit.execute(message=message, path=path)
