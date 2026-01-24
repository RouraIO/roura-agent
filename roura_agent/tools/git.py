"""
Roura Agent Git Tools.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry


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


# Create tool instances
git_status = GitStatusTool()
git_diff = GitDiffTool()
git_log = GitLogTool()

# Register tools
registry.register(git_status)
registry.register(git_diff)
registry.register(git_log)


def get_status(path: str = ".") -> ToolResult:
    """Convenience function to get git status."""
    return git_status.execute(path=path)


def get_diff(path: str = ".", staged: bool = False, commit: Optional[str] = None) -> ToolResult:
    """Convenience function to get git diff."""
    return git_diff.execute(path=path, staged=staged, commit=commit)


def get_log(path: str = ".", count: int = 10, oneline: bool = False) -> ToolResult:
    """Convenience function to get git log."""
    return git_log.execute(path=path, count=count, oneline=oneline)
