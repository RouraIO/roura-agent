# Configuration Reference

Complete reference for Roura Agent configuration options.

## Module: `roura_agent.config`

### Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `config.json` | `~/.config/roura-agent/` | General settings |
| `credentials.json` | `~/.config/roura-agent/` | API tokens (restricted permissions) |

### Config Class

Main configuration dataclass.

```python
@dataclass
class Config:
    ollama: OllamaConfig
    jira: JiraConfig
    github: GitHubConfig
    agent: AgentConfig
```

### OllamaConfig

LLM provider settings.

```python
@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = ""  # Empty = auto-detect
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_url` | str | `http://localhost:11434` | Ollama API endpoint |
| `model` | str | `""` | Model name (e.g., `qwen2.5-coder:14b`) |

**Environment Variables:**
- `OLLAMA_BASE_URL` - Overrides `base_url`
- `OLLAMA_MODEL` - Overrides `model`

### JiraConfig

Jira integration settings.

```python
@dataclass
class JiraConfig:
    url: str = ""
    email: str = ""
    # Token stored in credentials.json
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | str | `""` | Jira instance URL |
| `email` | str | `""` | Jira account email |

**Environment Variables:**
- `JIRA_URL` - Overrides `url`
- `JIRA_EMAIL` - Overrides `email`
- `JIRA_TOKEN` - API token (stored in credentials)

### GitHubConfig

GitHub integration settings.

```python
@dataclass
class GitHubConfig:
    default_base_branch: str = "main"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_base_branch` | str | `"main"` | Default branch for PRs |

### AgentConfig

Agent behavior settings.

```python
@dataclass
class AgentConfig:
    max_tool_calls: int = 3
    require_approval: bool = True
    auto_read_on_modify: bool = True
    stream_responses: bool = True
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_tool_calls` | int | `3` | Max tool calls per turn |
| `require_approval` | bool | `True` | Require approval for risky ops |
| `auto_read_on_modify` | bool | `True` | Auto-read before modify |
| `stream_responses` | bool | `True` | Stream LLM responses |

### Credentials Class

Sensitive credentials stored separately.

```python
@dataclass
class Credentials:
    jira_token: str = ""
```

| Field | Type | Description |
|-------|------|-------------|
| `jira_token` | str | Jira API token |

## Functions

### load_config

Load configuration from file.

```python
def load_config() -> Config:
    """Load configuration from ~/.config/roura-agent/config.json"""
```

**Returns:** `Config` instance with loaded or default values.

### save_config

Save configuration to file.

```python
def save_config(config: Config) -> None:
    """Save configuration to file."""
```

### load_credentials

Load credentials from secure file.

```python
def load_credentials() -> Credentials:
    """Load credentials from ~/.config/roura-agent/credentials.json"""
```

### save_credentials

Save credentials with restricted permissions.

```python
def save_credentials(creds: Credentials) -> None:
    """Save credentials to file with 600 permissions."""
```

### get_effective_config

Get configuration with environment variable overrides.

```python
def get_effective_config() -> tuple[Config, Credentials]:
    """
    Get effective configuration.

    Priority (highest to lowest):
    1. Environment variables
    2. Config file values
    3. Default values
    """
```

### get_validated_config

Get configuration with validation.

```python
def get_validated_config() -> tuple[Config, Credentials]:
    """
    Get configuration with validation.

    Raises:
        ConfigValidationError: If configuration is invalid
    """
```

## Validation

### validate_config

Validate configuration values.

```python
def validate_config(config: Config) -> list[str]:
    """
    Validate configuration.

    Returns:
        List of error messages (empty if valid)
    """
```

**Validations performed:**
- URL format for `ollama.base_url` and `jira.url`
- Email format for `jira.email`
- Model name format for `ollama.model`
- Numeric ranges for `agent.max_tool_calls`

### ConfigValidationError

Exception for validation failures.

```python
class ConfigValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
```

## Project Detection

### detect_project

Detect and analyze current project.

```python
def detect_project(path: Optional[Path] = None) -> ProjectInfo:
    """
    Detect project type and structure.

    Returns ProjectInfo with:
    - root: Project root path
    - name: Project name
    - type: Project type (python, node, rust, etc.)
    - files: List of project files
    - git_branch: Current git branch
    """
```

### ProjectInfo

Project information dataclass.

```python
@dataclass
class ProjectInfo:
    root: Path
    name: str
    type: str  # swift, python, node, rust, go, etc.
    files: list[str]
    structure: dict
    git_branch: Optional[str]
    description: str
```

### Supported Project Types

| Type | Detection Markers |
|------|-------------------|
| `swift` | `Package.swift`, `*.xcodeproj`, `*.swift` |
| `python` | `pyproject.toml`, `setup.py`, `requirements.txt` |
| `node` | `package.json`, `*.js`, `*.ts` |
| `rust` | `Cargo.toml`, `*.rs` |
| `go` | `go.mod`, `*.go` |
| `ruby` | `Gemfile`, `*.rb` |
| `java` | `pom.xml`, `build.gradle`, `*.java` |
| `csharp` | `*.csproj`, `*.sln`, `*.cs` |

## Example Config File

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5-coder:14b"
  },
  "jira": {
    "url": "https://company.atlassian.net",
    "email": "developer@company.com"
  },
  "github": {
    "default_base_branch": "main"
  },
  "agent": {
    "max_tool_calls": 3,
    "require_approval": true,
    "auto_read_on_modify": true,
    "stream_responses": true
  }
}
```

## Example Credentials File

```json
{
  "jira_token": "ATATT3xFfGF0..."
}
```

**Note:** This file should have permissions `600` (owner read/write only).
