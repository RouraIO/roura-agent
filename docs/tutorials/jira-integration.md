# Jira Integration

Roura Agent can connect to Jira to read issues, add comments, and update status.

## Setup

### Configure Jira Credentials

Run the setup command:

```bash
roura-agent setup
```

You'll need:
- **Jira URL**: Your Jira instance (e.g., `https://company.atlassian.net`)
- **Email**: Your Jira account email
- **API Token**: Generate at [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

### Environment Variables (Alternative)

Set these environment variables:

```bash
export JIRA_URL="https://company.atlassian.net"
export JIRA_EMAIL="you@company.com"
export JIRA_TOKEN="your-api-token"
```

### Verify Configuration

```bash
roura-agent config
```

Should show Jira configuration (tokens are hidden).

## Reading Issues

### Get Issue Details

```
> Show me the details of PROJ-123
```

Roura will fetch:
- Issue summary and description
- Status, priority, assignee
- Comments (last 5)
- Linked issues

### Search Issues

```
> Find open bugs assigned to me in the AUTH project
```

```
> Show high priority issues in the current sprint
```

## Working with Issues

### Understanding Requirements

```
> Read PROJ-456 and explain what needs to be implemented
```

Roura will analyze the issue and provide:
- Summary of requirements
- Acceptance criteria
- Technical considerations

### Implementation Help

```
> Based on PROJ-456, what files do I need to modify?
```

```
> Implement the changes described in PROJ-456
```

## Updating Issues

### Add Comments

```
> Add a comment to PROJ-123 saying I've started working on this
```

```
> Update PROJ-123 with a summary of the changes I just made
```

### Link Commits

When making commits, reference the issue:

```
> Commit these changes with a message referencing PROJ-123
```

Roura will create a commit like:
```
PROJ-123: Implement user authentication flow
```

## Common Workflows

### Sprint Planning

```
> List all issues in the current sprint for the AUTH project
```

### Bug Investigation

```
> Read BUG-789 and check if the file mentioned still has that problem
```

Roura will:
1. Fetch the bug report
2. Read the relevant file
3. Analyze if the issue still exists

### Progress Updates

```
> I just finished implementing PROJ-123. Update the issue with what was done and move it to "In Review"
```

## Jira Tool Reference

| Tool | Description | Risk |
|------|-------------|------|
| `jira.get_issue` | Fetch issue details | SAFE |
| `jira.search` | Search issues with JQL | SAFE |
| `jira.add_comment` | Add comment to issue | MODERATE |
| `jira.update_status` | Change issue status | MODERATE |

## JQL Quick Reference

When searching, you can use Jira Query Language:

| Query | Example |
|-------|---------|
| Assigned to me | `assignee = currentUser()` |
| Open bugs | `type = Bug AND status = Open` |
| High priority | `priority = High` |
| Current sprint | `sprint in openSprints()` |
| Recent updates | `updated >= -7d` |

## Troubleshooting

### "Authentication Failed"

1. Verify your API token at [Atlassian Security](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Check the email matches your Atlassian account
3. Ensure the URL is correct (include `https://`)

### "Issue Not Found"

- Verify the issue key format (PROJECT-NUMBER)
- Check you have permission to view the issue
- Ensure the project exists

### "Permission Denied"

Your Jira account may not have:
- Access to the project
- Permission to add comments
- Permission to transition issues

Contact your Jira administrator.

## Security Notes

- API tokens are stored in `~/.config/roura-agent/credentials.json` with restricted permissions (600)
- Tokens are never logged or displayed
- Use read-only tokens if you only need to view issues

## Next Steps

- [Getting Started](getting-started.md) - Basic usage guide
- [Working with Git](git-workflow.md) - Git integration features
