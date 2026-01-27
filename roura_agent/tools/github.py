"""
Roura Agent GitHub Tools - GitHub integration via gh CLI.

© Roura.io
"""
from __future__ import annotations

import subprocess
import json
from dataclasses import dataclass, field
from typing import Optional

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry


def run_gh_command(args: list[str], cwd: Optional[str] = None) -> tuple[bool, str, str]:
    """
    Run a gh CLI command and return (success, stdout, stderr).
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=60,
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
        return False, "", "gh CLI not found. Install with: brew install gh"
    except Exception as e:
        return False, "", str(e)


def check_gh_auth() -> tuple[bool, str]:
    """Check if gh CLI is authenticated."""
    success, stdout, stderr = run_gh_command(["auth", "status"])
    if success:
        return True, stdout
    return False, stderr


@dataclass
class GitHubPRListTool(Tool):
    """List pull requests."""

    name: str = "github.pr.list"
    description: str = "List pull requests for the current repository"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("state", str, "PR state: open, closed, merged, all", required=False, default="open"),
        ToolParam("limit", int, "Maximum number of PRs to list", required=False, default=10),
    ])

    def execute(self, state: str = "open", limit: int = 10) -> ToolResult:
        """List pull requests."""
        success, stdout, stderr = run_gh_command([
            "pr", "list",
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,author,createdAt,url",
        ])

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        try:
            prs = json.loads(stdout) if stdout else []
            return ToolResult(success=True, output={"prs": prs, "count": len(prs)})
        except json.JSONDecodeError:
            return ToolResult(success=True, output={"raw": stdout})

    def dry_run(self, state: str = "open", limit: int = 10) -> str:
        return f"Would list {limit} {state} pull requests"


@dataclass
class GitHubPRViewTool(Tool):
    """View pull request details."""

    name: str = "github.pr.view"
    description: str = "View details of a specific pull request"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("number", int, "PR number", required=True),
    ])

    def execute(self, number: int) -> ToolResult:
        """View PR details."""
        success, stdout, stderr = run_gh_command([
            "pr", "view", str(number),
            "--json", "number,title,body,state,author,createdAt,url,additions,deletions,changedFiles,commits,reviews",
        ])

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        try:
            pr = json.loads(stdout) if stdout else {}
            return ToolResult(success=True, output=pr)
        except json.JSONDecodeError:
            return ToolResult(success=True, output={"raw": stdout})

    def dry_run(self, number: int) -> str:
        return f"Would view PR #{number}"


@dataclass
class GitHubPRCreateTool(Tool):
    """Create a pull request."""

    name: str = "github.pr.create"
    description: str = "Create a new pull request"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("title", str, "PR title", required=True),
        ToolParam("body", str, "PR description", required=False, default=""),
        ToolParam("base", str, "Base branch (default: main)", required=False, default="main"),
        ToolParam("draft", bool, "Create as draft PR", required=False, default=False),
    ])

    def execute(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> ToolResult:
        """Create a pull request."""
        args = ["pr", "create", "--title", title, "--base", base]

        if body:
            args.extend(["--body", body])

        if draft:
            args.append("--draft")

        success, stdout, stderr = run_gh_command(args)

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        return ToolResult(success=True, output={"url": stdout, "title": title})

    def dry_run(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> str:
        draft_str = " (draft)" if draft else ""
        return f"Would create PR{draft_str}: {title}"

    def preview(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> dict:
        return {
            "title": title,
            "body": body[:200] + "..." if len(body) > 200 else body,
            "base": base,
            "draft": draft,
        }


@dataclass
class GitHubIssuesTool(Tool):
    """List issues."""

    name: str = "github.issue.list"
    description: str = "List issues for the current repository"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("state", str, "Issue state: open, closed, all", required=False, default="open"),
        ToolParam("limit", int, "Maximum number of issues", required=False, default=10),
        ToolParam("label", str, "Filter by label", required=False, default=None),
    ])

    def execute(
        self,
        state: str = "open",
        limit: int = 10,
        label: Optional[str] = None,
    ) -> ToolResult:
        """List issues."""
        args = [
            "issue", "list",
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,author,createdAt,url,labels",
        ]

        if label:
            args.extend(["--label", label])

        success, stdout, stderr = run_gh_command(args)

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        try:
            issues = json.loads(stdout) if stdout else []
            return ToolResult(success=True, output={"issues": issues, "count": len(issues)})
        except json.JSONDecodeError:
            return ToolResult(success=True, output={"raw": stdout})

    def dry_run(
        self,
        state: str = "open",
        limit: int = 10,
        label: Optional[str] = None,
    ) -> str:
        label_str = f" with label '{label}'" if label else ""
        return f"Would list {limit} {state} issues{label_str}"


@dataclass
class GitHubIssueViewTool(Tool):
    """View issue details."""

    name: str = "github.issue.view"
    description: str = "View details of a specific issue"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("number", int, "Issue number", required=True),
    ])

    def execute(self, number: int) -> ToolResult:
        """View issue details."""
        success, stdout, stderr = run_gh_command([
            "issue", "view", str(number),
            "--json", "number,title,body,state,author,createdAt,url,labels,comments",
        ])

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        try:
            issue = json.loads(stdout) if stdout else {}
            return ToolResult(success=True, output=issue)
        except json.JSONDecodeError:
            return ToolResult(success=True, output={"raw": stdout})

    def dry_run(self, number: int) -> str:
        return f"Would view issue #{number}"


@dataclass
class GitHubIssueCreateTool(Tool):
    """Create an issue."""

    name: str = "github.issue.create"
    description: str = "Create a new issue"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("title", str, "Issue title", required=True),
        ToolParam("body", str, "Issue description", required=False, default=""),
        ToolParam("labels", str, "Comma-separated labels", required=False, default=None),
    ])

    def execute(
        self,
        title: str,
        body: str = "",
        labels: Optional[str] = None,
    ) -> ToolResult:
        """Create an issue."""
        args = ["issue", "create", "--title", title]

        if body:
            args.extend(["--body", body])

        if labels:
            for label in labels.split(","):
                args.extend(["--label", label.strip()])

        success, stdout, stderr = run_gh_command(args)

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        return ToolResult(success=True, output={"url": stdout, "title": title})

    def dry_run(
        self,
        title: str,
        body: str = "",
        labels: Optional[str] = None,
    ) -> str:
        return f"Would create issue: {title}"

    def preview(
        self,
        title: str,
        body: str = "",
        labels: Optional[str] = None,
    ) -> dict:
        return {
            "title": title,
            "body": body[:200] + "..." if len(body) > 200 else body,
            "labels": labels.split(",") if labels else [],
        }


@dataclass
class GitHubRepoTool(Tool):
    """Get repository information."""

    name: str = "github.repo.view"
    description: str = "Get information about the current repository"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=list)

    def execute(self) -> ToolResult:
        """Get repo info."""
        success, stdout, stderr = run_gh_command([
            "repo", "view",
            "--json", "name,owner,description,url,defaultBranchRef,stargazerCount,forkCount,isPrivate",
        ])

        if not success:
            return ToolResult(success=False, output=None, error=stderr)

        try:
            repo = json.loads(stdout) if stdout else {}
            return ToolResult(success=True, output=repo)
        except json.JSONDecodeError:
            return ToolResult(success=True, output={"raw": stdout})

    def dry_run(self) -> str:
        return "Would show repository information"


# Create tool instances
github_pr_list = GitHubPRListTool()
github_pr_view = GitHubPRViewTool()
github_pr_create = GitHubPRCreateTool()
github_issue_list = GitHubIssuesTool()
github_issue_view = GitHubIssueViewTool()
github_issue_create = GitHubIssueCreateTool()
github_repo_view = GitHubRepoTool()

# Register tools
registry.register(github_pr_list)
registry.register(github_pr_view)
registry.register(github_pr_create)
registry.register(github_issue_list)
registry.register(github_issue_view)
registry.register(github_issue_create)
registry.register(github_repo_view)
