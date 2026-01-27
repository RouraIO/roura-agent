# Troubleshooting Guide

This guide covers common issues and their solutions, organized by error code.

## Quick Diagnostics

Run these commands to diagnose common issues:

```bash
# Check Roura Agent version
roura-agent --version

# Verify configuration
roura-agent config

# Test Ollama connection
curl http://localhost:11434/api/tags

# Check if model is available
ollama list
```

---

## Ollama Connection Errors (ROURA-1xx)

### ROURA-101: Connection Failed

**Symptoms:**
- "Could not connect to Ollama"
- "Connection refused"

**Causes:**
1. Ollama is not running
2. Ollama is running on a different port
3. Firewall blocking connection

**Solutions:**

```bash
# Start Ollama
ollama serve

# Or check if it's running
pgrep ollama

# Test connection
curl http://localhost:11434/api/tags
```

If using a non-default URL:
```bash
export OLLAMA_BASE_URL="http://localhost:11434"
roura-agent chat
```

---

### ROURA-102: Request Timeout

**Symptoms:**
- Operation takes too long and fails
- "Request timed out"

**Causes:**
1. Model is large and loading slowly
2. System resources are limited
3. Complex request with large context

**Solutions:**

```bash
# Use a smaller, faster model
export OLLAMA_MODEL="qwen2.5-coder:7b"

# Or increase timeout (future feature)
# For now, try again - the model may be cached now
```

---

### ROURA-103: Model Not Found

**Symptoms:**
- "Model 'xxx' not found"
- "pull model manifest"

**Causes:**
1. Model not installed in Ollama
2. Typo in model name

**Solutions:**

```bash
# List available models
ollama list

# Pull the model
ollama pull qwen2.5-coder:14b

# Or configure a different model
roura-agent setup
```

---

### ROURA-104: Invalid Response

**Symptoms:**
- "Unexpected response format"
- JSON parsing errors

**Causes:**
1. Model doesn't support tool calling
2. Ollama version too old
3. Network issues corrupting response

**Solutions:**

```bash
# Update Ollama
ollama --version  # Should be 0.1.29+

# Use a model with tool support
ollama pull qwen2.5-coder:14b
# or
ollama pull llama3.1:8b
```

---

## File System Errors (ROURA-2xx)

### ROURA-201: File Not Found

**Symptoms:**
- "File not found: /path/to/file"
- "No such file or directory"

**Causes:**
1. File doesn't exist
2. Path is relative and CWD is different
3. Typo in filename

**Solutions:**

```
> Use /context to see current working directory
> List the directory with: ls -la /path/to/dir
```

Always use absolute paths or paths relative to project root.

---

### ROURA-202: Permission Denied

**Symptoms:**
- "Permission denied"
- Cannot read or write file

**Causes:**
1. File permissions don't allow access
2. File is owned by different user
3. Read-only filesystem

**Solutions:**

```bash
# Check permissions
ls -la /path/to/file

# Fix permissions if needed
chmod 644 /path/to/file

# Check ownership
sudo chown $USER /path/to/file
```

---

### ROURA-203: Write Failed

**Symptoms:**
- "Failed to write file"
- "Disk full" or "No space left"

**Causes:**
1. Disk is full
2. Path doesn't exist
3. File is locked by another process

**Solutions:**

```bash
# Check disk space
df -h

# Create parent directory
mkdir -p /path/to/directory

# Check if file is locked
lsof /path/to/file
```

---

### ROURA-204: File Modified Externally

**Symptoms:**
- "File has been modified since it was read"
- Edit operation fails

**Causes:**
1. Another process modified the file
2. Editor has unsaved changes
3. Git operation changed the file

**Solutions:**

```
> Re-read the file to get latest content
> Then make your edit
```

---

### ROURA-205: Constraint Violation

**Symptoms:**
- "Must read file before modifying"
- "Cannot modify: file not in read set"

**Causes:**
1. Tried to edit a file that wasn't read first

**Solutions:**

This is a safety feature. Roura must read files before modifying to prevent blind edits.

```
> Read the file first, then make the edit
```

If `auto_read_on_modify` is enabled (default), Roura will automatically read the file.

---

## Shell Errors (ROURA-3xx)

### ROURA-301: Command Failed

**Symptoms:**
- Command exits with non-zero code
- Error output shown

**Causes:**
- Command syntax error
- Missing dependencies
- Invalid arguments

**Solutions:**

Review the command output. Common fixes:

```bash
# Missing command
brew install <package>  # macOS
apt install <package>   # Linux

# Permission issues
sudo <command>  # if appropriate
```

---

### ROURA-302: Command Timeout

**Symptoms:**
- "Command timed out after X seconds"
- Long-running operation killed

**Causes:**
1. Command takes too long
2. Command is waiting for input
3. Infinite loop in script

**Solutions:**

```
> Try running with shorter timeout or different flags
> For interactive commands, provide all input via flags
```

---

### ROURA-303: Unsafe Command

**Symptoms:**
- "Command not allowed"
- Operation blocked

**Causes:**
1. Running in safe mode
2. Command is on blocklist

**Solutions:**

If you need to run the command:

```bash
# Disable safe mode (use with caution)
roura-agent chat  # without --safe-mode
```

---

## Git Errors (ROURA-4xx)

### ROURA-401: Not a Repository

**Symptoms:**
- "Not a git repository"
- Git commands fail

**Solutions:**

```bash
# Initialize a repository
git init

# Or navigate to a git repository
cd /path/to/repo
roura-agent chat
```

---

### ROURA-402: Uncommitted Changes

**Symptoms:**
- "Working tree has uncommitted changes"
- Cannot switch branches

**Solutions:**

```
> Show me the uncommitted changes
> Either commit them or stash them
```

---

### ROURA-403: Merge Conflict

**Symptoms:**
- "Merge conflict in file"
- Cannot complete operation

**Solutions:**

```
> Show me the conflicts in the file
> Help me resolve them
```

---

## Jira Errors (ROURA-5xx)

### ROURA-501: Authentication Failed

**Symptoms:**
- "Invalid credentials"
- "401 Unauthorized"

**Causes:**
1. Invalid API token
2. Wrong email address
3. Token expired

**Solutions:**

1. Generate a new token at [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Run `roura-agent setup` to reconfigure

---

### ROURA-502: Issue Not Found

**Symptoms:**
- "Issue does not exist"
- "404 Not Found"

**Causes:**
1. Wrong issue key
2. No permission to view issue
3. Issue was deleted

**Solutions:**

- Verify the issue key format (PROJECT-123)
- Check you have access in Jira's web interface

---

### ROURA-503: Permission Denied

**Symptoms:**
- "User does not have permission"
- Cannot update issue

**Solutions:**

Contact your Jira administrator for appropriate permissions.

---

## Context Errors (ROURA-6xx)

### ROURA-601: Context Limit Reached

**Symptoms:**
- "Context token limit exceeded"
- Responses become degraded

**Causes:**
1. Too many files loaded
2. Very large files in context
3. Long conversation history

**Solutions:**

```
> Use /clear to reset conversation
> Or start a new session
```

---

### ROURA-602: Iteration Limit

**Symptoms:**
- "Maximum iterations reached"
- Loop stops unexpectedly

**Causes:**
1. Complex task requiring many iterations
2. Tool calling loop

**Solutions:**

```
> Break the task into smaller parts
> Use /clear and continue with remaining work
```

---

## Getting Help

### Log Files

Logs are stored in:
- `~/.config/roura-agent/logs/roura-agent.log` (user-wide)
- `.roura/logs/roura-agent.log` (project-local)

### Debug Mode

Run with debug logging:

```bash
roura-agent chat --debug
```

### Report Issues

If you encounter a bug:

1. Check existing issues: https://github.com/roura-io/roura-agent/issues
2. Include:
   - Error code and message
   - Steps to reproduce
   - Relevant log output
   - System info (OS, Python version, Ollama version)
