# Working with Git

Roura Agent provides powerful git integration for common development workflows.

## Prerequisites

- Git installed and configured
- Working in a git repository

## Checking Repository Status

### Quick Status

```
> What's the git status?
```

Roura uses `git.status` to show:
- Current branch
- Staged and unstaged changes
- Untracked files

### Viewing Changes

```
> Show me what changed in the last commit
```

or

```
> What are the uncommitted changes to auth.py?
```

## Making Commits

### Simple Commit

```
> Stage and commit the changes to config.py with message "Update database settings"
```

Roura will:
1. Run `git.status` to see current state
2. Run `git.add` to stage files
3. Ask for approval before `git.commit`

### Commit with Diff Review

```
> Show me the diff and help me write a commit message
```

Roura will analyze the changes and suggest an appropriate commit message.

## Branch Operations

### Check Current Branch

```
> What branch am I on?
```

### View Recent History

```
> Show me the last 5 commits
```

### View Commit Details

```
> What changed in commit abc1234?
```

## Common Workflows

### Feature Development

```
> I'm starting work on the user profile feature. Create a new branch.
```

Then after making changes:

```
> Stage all the changes and create a commit describing the profile page implementation
```

### Bug Fixes

```
> Show me the recent commits that touched payment.py - there's a regression
```

After identifying the issue:

```
> Fix the discount calculation and commit with a message referencing bug #123
```

### Code Review Preparation

```
> Show me all uncommitted changes and help me organize them into logical commits
```

## Git Tool Reference

| Tool | Description | Risk |
|------|-------------|------|
| `git.status` | Repository status | SAFE |
| `git.diff` | View changes | SAFE |
| `git.log` | Commit history | SAFE |
| `git.add` | Stage files | MODERATE |
| `git.commit` | Create commit | DANGEROUS |

## Tips

### Atomic Commits

Ask Roura to help organize changes:

```
> I have changes to 5 files. Help me split them into logical commits.
```

### Good Commit Messages

Roura can write commit messages following conventions:

```
> Write a conventional commit message for these changes
```

### Avoiding Mistakes

- Roura always shows `git.status` before committing
- Commit operations require explicit approval
- Use `/undo` for file changes (but not for commits - those require git commands)

## Troubleshooting

### "Not a git repository"

Make sure you're in a git-initialized directory:

```bash
git init
# or
cd /path/to/your/repo
roura-agent chat
```

### Merge Conflicts

```
> There are merge conflicts in auth.py. Show me the conflicts and help resolve them.
```

Roura will read the file, identify conflict markers, and help you choose resolutions.

## Next Steps

- [Jira Integration](jira-integration.md) - Connect commits to Jira issues
- [Getting Started](getting-started.md) - Basic usage guide
