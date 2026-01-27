# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Roura Agent, please report it responsibly:

1. **Email**: security@roura.io
2. **Subject**: [SECURITY] Brief description of the issue
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (optional)

**Do not** disclose the vulnerability publicly until we have had a chance to address it.

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Resolution**: Depends on severity (Critical: 7 days, High: 30 days, Medium: 90 days)

## Security Features

Roura Agent includes multiple security features to protect your codebase:

### Secrets Detection

Files are scanned for potential secrets before writing:
- API keys
- Private keys
- Passwords
- Tokens
- Connection strings

If secrets are detected, the write operation is blocked with an explanation.

### Blast Radius Limits

Control which files can be modified:

```bash
# Only allow changes to src/ directory
roura-agent --allow "src/**/*"

# Block changes to sensitive files
roura-agent --block "*.env" --block "credentials.*"
```

### Forbidden Directories

These directories are protected by default:
- `.git/` - Git internals
- `node_modules/` - Dependencies
- `.venv/` - Virtual environments
- `__pycache__/` - Python cache

### Shell Command Blocklist

Dangerous commands are blocked:
- `rm -rf /`
- `rm -rf /*`
- `dd if=/dev/zero of=/dev/sda`
- Fork bombs
- Other destructive patterns

### Read-Before-Modify Constraint

Files must be read before they can be modified, preventing the LLM from hallucinating file contents.

### Safety Modes

```bash
# Preview all changes without writing
roura-agent --dry-run

# Block all file modifications
roura-agent --readonly

# Disable dangerous tools (shell.exec, etc.)
roura-agent --safe-mode
```

### API Key Handling

- API keys are loaded from environment variables only
- Keys are never logged or displayed
- Credentials file uses restrictive permissions (600)

## Security Best Practices

When using Roura Agent:

1. **Review before approval**: Always review the diff before approving file modifications
2. **Use blast radius limits**: Restrict modifications to relevant directories
3. **Enable dry-run for sensitive operations**: Preview complex changes first
4. **Keep credentials out of code**: Use environment variables
5. **Update regularly**: Stay on the latest version for security fixes

## Audit Trail

Roura Agent maintains session logs that can be used for auditing:

```bash
# View session history
roura-agent
> /history

# Export session for audit
> /export json
```

Sessions are stored in `~/.config/roura-agent/sessions/`.
