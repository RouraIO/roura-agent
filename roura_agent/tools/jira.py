"""
Roura Agent Jira Tools - Jira integration via REST API.

© Roura.io
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import httpx

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry


def get_jira_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Get Jira configuration from environment.

    Expected env vars:
    - JIRA_URL: Base URL (e.g., https://company.atlassian.net)
    - JIRA_EMAIL: User email
    - JIRA_TOKEN: API token
    """
    return (
        os.getenv("JIRA_URL"),
        os.getenv("JIRA_EMAIL"),
        os.getenv("JIRA_TOKEN"),
    )


def jira_request(
    method: str,
    endpoint: str,
    data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> tuple[bool, dict, str]:
    """
    Make a Jira API request.

    Returns (success, response_data, error_message).
    """
    base_url, email, token = get_jira_config()

    if not all([base_url, email, token]):
        return False, {}, "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_TOKEN"

    url = urljoin(base_url, f"/rest/api/3/{endpoint}")

    try:
        response = httpx.request(
            method,
            url,
            auth=(email, token),
            json=data,
            params=params,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

        if response.status_code >= 400:
            try:
                error_data = response.json()
                errors = error_data.get("errorMessages", [])
                return False, {}, "; ".join(errors) if errors else f"HTTP {response.status_code}"
            except Exception:
                return False, {}, f"HTTP {response.status_code}"

        if response.content:
            return True, response.json(), ""
        return True, {}, ""

    except httpx.TimeoutException:
        return False, {}, "Request timed out"
    except Exception as e:
        return False, {}, str(e)


@dataclass
class JiraSearchTool(Tool):
    """Search Jira issues with JQL."""

    name: str = "jira.search"
    description: str = "Search Jira issues using JQL"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("jql", str, "JQL query string", required=True),
        ToolParam("limit", int, "Maximum results", required=False, default=10),
    ])

    def execute(self, jql: str, limit: int = 10) -> ToolResult:
        """Search issues."""
        success, data, error = jira_request(
            "GET",
            "search",
            params={
                "jql": jql,
                "maxResults": limit,
                "fields": "key,summary,status,assignee,priority,created,updated",
            },
        )

        if not success:
            return ToolResult(success=False, output=None, error=error)

        issues = []
        for item in data.get("issues", []):
            fields = item.get("fields", {})
            issues.append({
                "key": item.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
            })

        return ToolResult(success=True, output={
            "issues": issues,
            "total": data.get("total", len(issues)),
            "count": len(issues),
        })

    def dry_run(self, jql: str, limit: int = 10) -> str:
        return f"Would search Jira: {jql}"


@dataclass
class JiraIssueTool(Tool):
    """Get Jira issue details."""

    name: str = "jira.issue.get"
    description: str = "Get details of a Jira issue"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("key", str, "Issue key (e.g., PROJ-123)", required=True),
    ])

    def execute(self, key: str) -> ToolResult:
        """Get issue details."""
        success, data, error = jira_request("GET", f"issue/{key}")

        if not success:
            return ToolResult(success=False, output=None, error=error)

        fields = data.get("fields", {})

        issue = {
            "key": data.get("key"),
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "status": fields.get("status", {}).get("name"),
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
            "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
            "type": fields.get("issuetype", {}).get("name"),
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "labels": fields.get("labels", []),
        }

        return ToolResult(success=True, output=issue)

    def dry_run(self, key: str) -> str:
        return f"Would get issue {key}"


@dataclass
class JiraCreateIssueTool(Tool):
    """Create a Jira issue."""

    name: str = "jira.issue.create"
    description: str = "Create a new Jira issue"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("project", str, "Project key (e.g., PROJ)", required=True),
        ToolParam("summary", str, "Issue summary/title", required=True),
        ToolParam("description", str, "Issue description", required=False, default=""),
        ToolParam("issue_type", str, "Issue type (Task, Bug, Story, etc.)", required=False, default="Task"),
    ])

    def execute(
        self,
        project: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
    ) -> ToolResult:
        """Create an issue."""
        payload = {
            "fields": {
                "project": {"key": project},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        }

        if description:
            # Jira Cloud uses ADF (Atlassian Document Format)
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }

        success, data, error = jira_request("POST", "issue", data=payload)

        if not success:
            return ToolResult(success=False, output=None, error=error)

        return ToolResult(success=True, output={
            "key": data.get("key"),
            "id": data.get("id"),
            "self": data.get("self"),
        })

    def dry_run(
        self,
        project: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
    ) -> str:
        return f"Would create {issue_type} in {project}: {summary}"

    def preview(
        self,
        project: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
    ) -> dict:
        return {
            "project": project,
            "summary": summary,
            "description": description[:200] + "..." if len(description) > 200 else description,
            "issue_type": issue_type,
        }


@dataclass
class JiraTransitionTool(Tool):
    """Transition a Jira issue to a new status."""

    name: str = "jira.issue.transition"
    description: str = "Move a Jira issue to a new status"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("key", str, "Issue key (e.g., PROJ-123)", required=True),
        ToolParam("status", str, "Target status name", required=True),
    ])

    def execute(self, key: str, status: str) -> ToolResult:
        """Transition issue."""
        # First, get available transitions
        success, data, error = jira_request("GET", f"issue/{key}/transitions")

        if not success:
            return ToolResult(success=False, output=None, error=error)

        # Find matching transition
        transition_id = None
        for transition in data.get("transitions", []):
            if transition.get("name", "").lower() == status.lower():
                transition_id = transition.get("id")
                break
            if transition.get("to", {}).get("name", "").lower() == status.lower():
                transition_id = transition.get("id")
                break

        if not transition_id:
            available = [t.get("name") for t in data.get("transitions", [])]
            return ToolResult(
                success=False,
                output=None,
                error=f"Transition to '{status}' not available. Available: {', '.join(available)}",
            )

        # Perform transition
        success, _, error = jira_request(
            "POST",
            f"issue/{key}/transitions",
            data={"transition": {"id": transition_id}},
        )

        if not success:
            return ToolResult(success=False, output=None, error=error)

        return ToolResult(success=True, output={
            "key": key,
            "new_status": status,
        })

    def dry_run(self, key: str, status: str) -> str:
        return f"Would move {key} to '{status}'"


@dataclass
class JiraCommentTool(Tool):
    """Add a comment to a Jira issue."""

    name: str = "jira.issue.comment"
    description: str = "Add a comment to a Jira issue"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("key", str, "Issue key (e.g., PROJ-123)", required=True),
        ToolParam("body", str, "Comment text", required=True),
    ])

    def execute(self, key: str, body: str) -> ToolResult:
        """Add comment."""
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }

        success, data, error = jira_request("POST", f"issue/{key}/comment", data=payload)

        if not success:
            return ToolResult(success=False, output=None, error=error)

        return ToolResult(success=True, output={
            "key": key,
            "comment_id": data.get("id"),
        })

    def dry_run(self, key: str, body: str) -> str:
        return f"Would add comment to {key}"


@dataclass
class JiraMyIssuesTool(Tool):
    """Get issues assigned to current user."""

    name: str = "jira.my_issues"
    description: str = "Get issues assigned to you"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("status", str, "Filter by status (optional)", required=False, default=None),
        ToolParam("limit", int, "Maximum results", required=False, default=10),
    ])

    def execute(self, status: Optional[str] = None, limit: int = 10) -> ToolResult:
        """Get my issues."""
        jql = "assignee = currentUser()"
        if status:
            jql += f" AND status = '{status}'"
        jql += " ORDER BY updated DESC"

        # Reuse search tool
        search_tool = JiraSearchTool()
        return search_tool.execute(jql=jql, limit=limit)

    def dry_run(self, status: Optional[str] = None, limit: int = 10) -> str:
        status_str = f" with status '{status}'" if status else ""
        return f"Would get your assigned issues{status_str}"


# Create tool instances
jira_search = JiraSearchTool()
jira_issue = JiraIssueTool()
jira_create = JiraCreateIssueTool()
jira_transition = JiraTransitionTool()
jira_comment = JiraCommentTool()
jira_my_issues = JiraMyIssuesTool()

# Register tools
registry.register(jira_search)
registry.register(jira_issue)
registry.register(jira_create)
registry.register(jira_transition)
registry.register(jira_comment)
registry.register(jira_my_issues)
