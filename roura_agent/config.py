"""
Roura Agent Configuration - Secure credential storage, project detection, and centralized config.

Provides:
- Secure credential storage
- Project detection and analysis
- Multi-source configuration (env, files, CLI)
- Type-safe config access

© Roura.io
"""
from __future__ import annotations

import json
import logging
import os
import stat
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


# Config locations
CONFIG_DIR = Path.home() / ".config" / "roura-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"  # Stored with restricted permissions


@dataclass
class OllamaConfig:
    """Ollama configuration."""
    base_url: str = "http://localhost:11434"
    model: str = ""


@dataclass
class JiraConfig:
    """Jira configuration."""
    url: str = ""
    email: str = ""
    # Token stored separately in credentials file


@dataclass
class GitHubConfig:
    """GitHub configuration."""
    # Uses gh CLI, so just store preferences
    default_base_branch: str = "main"


@dataclass
class AgentConfig:
    """Agent behavior configuration."""
    max_tool_calls: int = 3
    require_approval: bool = True
    auto_read_on_modify: bool = True
    stream_responses: bool = True


@dataclass
class Config:
    """Main configuration."""
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    jira: JiraConfig = field(default_factory=JiraConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    def to_dict(self) -> dict:
        return {
            "ollama": asdict(self.ollama),
            "jira": asdict(self.jira),
            "github": asdict(self.github),
            "agent": asdict(self.agent),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        return cls(
            ollama=OllamaConfig(**data.get("ollama", {})),
            jira=JiraConfig(**data.get("jira", {})),
            github=GitHubConfig(**data.get("github", {})),
            agent=AgentConfig(**data.get("agent", {})),
        )


@dataclass
class Credentials:
    """Sensitive credentials stored separately."""
    jira_token: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Credentials:
        return cls(**data)


# --- Configuration Validation ---


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Configuration validation failed: {', '.join(errors)}")


def validate_url(url: str, name: str) -> list[str]:
    """Validate a URL format."""
    errors = []
    if not url:
        return errors  # Empty is allowed (not configured)

    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            errors.append(f"{name}: URL must include scheme (http:// or https://)")
        elif parsed.scheme not in ("http", "https"):
            errors.append(f"{name}: URL scheme must be http or https, got '{parsed.scheme}'")
        if not parsed.netloc:
            errors.append(f"{name}: URL must include host")
    except Exception as e:
        errors.append(f"{name}: Invalid URL format: {e}")

    return errors


def validate_model_name(model: str) -> list[str]:
    """Validate an Ollama model name."""
    errors = []
    if not model:
        return errors  # Empty is allowed (not configured)

    # Model names should be alphanumeric with optional : for tags
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+(?::[a-zA-Z0-9._-]+)?$', model):
        errors.append(f"model: Invalid model name format: '{model}'")

    return errors


def validate_email(email: str, name: str) -> list[str]:
    """Validate an email format."""
    errors = []
    if not email:
        return errors  # Empty is allowed (not configured)

    import re
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        errors.append(f"{name}: Invalid email format: '{email}'")

    return errors


def validate_positive_int(value: int, name: str, min_val: int = 1, max_val: int = 1000) -> list[str]:
    """Validate a positive integer within range."""
    errors = []
    if not isinstance(value, int):
        errors.append(f"{name}: Must be an integer, got {type(value).__name__}")
    elif value < min_val:
        errors.append(f"{name}: Must be at least {min_val}, got {value}")
    elif value > max_val:
        errors.append(f"{name}: Must be at most {max_val}, got {value}")
    return errors


def validate_config(config: Config) -> list[str]:
    """
    Validate configuration values.

    Returns a list of error messages (empty if valid).
    """
    errors = []

    # Ollama config
    errors.extend(validate_url(config.ollama.base_url, "ollama.base_url"))
    errors.extend(validate_model_name(config.ollama.model))

    # Jira config
    errors.extend(validate_url(config.jira.url, "jira.url"))
    errors.extend(validate_email(config.jira.email, "jira.email"))

    # Agent config
    errors.extend(validate_positive_int(
        config.agent.max_tool_calls, "agent.max_tool_calls", min_val=1, max_val=50
    ))

    return errors


def validate_and_raise(config: Config) -> None:
    """Validate configuration and raise if invalid."""
    errors = validate_config(config)
    if errors:
        raise ConfigValidationError(errors)


def get_validated_config() -> tuple[Config, Credentials]:
    """Get effective configuration with validation."""
    config, creds = get_effective_config()
    validate_and_raise(config)
    return config, creds


def ensure_config_dir() -> None:
    """Ensure config directory exists with proper permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Set directory permissions to owner only
    os.chmod(CONFIG_DIR, stat.S_IRWXU)


def load_config() -> Config:
    """Load configuration from file."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return Config.from_dict(data)
        except Exception:
            pass
    return Config()


def save_config(config: Config) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(config.to_dict(), indent=2))


def load_credentials() -> Credentials:
    """Load credentials from secure file."""
    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(CREDENTIALS_FILE.read_text())
            return Credentials.from_dict(data)
        except Exception:
            pass
    return Credentials()


def save_credentials(creds: Credentials) -> None:
    """Save credentials to secure file with restricted permissions."""
    ensure_config_dir()
    CREDENTIALS_FILE.write_text(json.dumps(creds.to_dict(), indent=2))
    # Set file permissions to owner read/write only (600)
    os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)


def apply_config_to_env(config: Config, creds: Credentials) -> None:
    """Apply configuration to environment variables."""
    # Ollama
    if config.ollama.base_url:
        os.environ.setdefault("OLLAMA_BASE_URL", config.ollama.base_url)
    if config.ollama.model:
        os.environ.setdefault("OLLAMA_MODEL", config.ollama.model)

    # Jira
    if config.jira.url:
        os.environ.setdefault("JIRA_URL", config.jira.url)
    if config.jira.email:
        os.environ.setdefault("JIRA_EMAIL", config.jira.email)
    if creds.jira_token:
        os.environ.setdefault("JIRA_TOKEN", creds.jira_token)


def get_effective_config() -> tuple[Config, Credentials]:
    """Get effective configuration (file + env overrides)."""
    config = load_config()
    creds = load_credentials()

    # Environment variables override file config
    if os.getenv("OLLAMA_BASE_URL"):
        config.ollama.base_url = os.getenv("OLLAMA_BASE_URL")
    if os.getenv("OLLAMA_MODEL"):
        config.ollama.model = os.getenv("OLLAMA_MODEL")
    if os.getenv("JIRA_URL"):
        config.jira.url = os.getenv("JIRA_URL")
    if os.getenv("JIRA_EMAIL"):
        config.jira.email = os.getenv("JIRA_EMAIL")
    if os.getenv("JIRA_TOKEN"):
        creds.jira_token = os.getenv("JIRA_TOKEN")

    return config, creds


# --- Project Detection ---


@dataclass
class ProjectInfo:
    """Information about the current project."""
    root: Path
    name: str
    type: str  # swift, python, node, rust, go, etc.
    files: list[str] = field(default_factory=list)
    structure: dict = field(default_factory=dict)
    git_branch: Optional[str] = None
    description: str = ""


PROJECT_MARKERS = {
    "swift": ["Package.swift", "*.xcodeproj", "*.xcworkspace", "*.swift"],
    "python": ["pyproject.toml", "setup.py", "requirements.txt", "*.py"],
    "node": ["package.json", "*.js", "*.ts"],
    "rust": ["Cargo.toml", "*.rs"],
    "go": ["go.mod", "*.go"],
    "ruby": ["Gemfile", "*.rb"],
    "java": ["pom.xml", "build.gradle", "*.java"],
    "csharp": ["*.csproj", "*.sln", "*.cs"],
}


def detect_project_type(root: Path) -> str:
    """Detect project type based on files present."""
    for project_type, markers in PROJECT_MARKERS.items():
        for marker in markers:
            if marker.startswith("*"):
                # Glob pattern
                if list(root.glob(marker)) or list(root.glob(f"**/{marker}")):
                    return project_type
            else:
                # Exact file/dir name
                if (root / marker).exists():
                    return project_type
                # Check for glob
                if list(root.glob(marker)):
                    return project_type
    return "unknown"


def get_git_branch(root: Path) -> Optional[str]:
    """Get current git branch."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=root,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def scan_project_files(root: Path, max_files: int = 500) -> list[str]:
    """Scan project files, respecting .gitignore patterns."""
    files = []

    # Common ignore patterns
    ignore_patterns = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "build", "dist", ".build", "DerivedData", "Pods",
        ".idea", ".vscode", "*.pyc", ".DS_Store",
    }

    def should_ignore(path: Path) -> bool:
        for pattern in ignore_patterns:
            if pattern in path.parts:
                return True
            if path.name == pattern:
                return True
        return False

    try:
        for item in root.rglob("*"):
            if len(files) >= max_files:
                break
            if item.is_file() and not should_ignore(item):
                rel_path = item.relative_to(root)
                files.append(str(rel_path))
    except Exception:
        pass

    return sorted(files)


def build_project_structure(files: list[str]) -> dict:
    """Build a tree structure from file list."""
    structure = {}

    for file_path in files:
        parts = Path(file_path).parts
        current = structure

        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # File
                if "_files" not in current:
                    current["_files"] = []
                current["_files"].append(part)
            else:
                # Directory
                if part not in current:
                    current[part] = {}
                current = current[part]

    return structure


def format_structure_tree(structure: dict, prefix: str = "", max_depth: int = 3, current_depth: int = 0) -> str:
    """Format structure as a tree string."""
    if current_depth >= max_depth:
        return ""

    lines = []

    # Files first
    files = structure.get("_files", [])
    dirs = {k: v for k, v in structure.items() if k != "_files"}

    for i, f in enumerate(files[:10]):  # Limit files shown
        is_last = (i == len(files) - 1) and not dirs
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{f}")

    if len(files) > 10:
        lines.append(f"{prefix}    ... and {len(files) - 10} more files")

    # Then directories
    dir_items = list(dirs.items())
    for i, (name, substructure) in enumerate(dir_items[:10]):
        is_last = i == len(dir_items) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{name}/")

        # Recurse
        new_prefix = prefix + ("    " if is_last else "│   ")
        subtree = format_structure_tree(substructure, new_prefix, max_depth, current_depth + 1)
        if subtree:
            lines.append(subtree)

    return "\n".join(lines)


def detect_project(path: Optional[Path] = None) -> ProjectInfo:
    """Detect and analyze the current project."""
    root = path or Path.cwd()

    # Find git root if available
    git_root = None
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=root,
            timeout=5,
        )
        if result.returncode == 0:
            git_root = Path(result.stdout.strip())
    except Exception:
        pass

    project_root = git_root or root

    # Detect type
    project_type = detect_project_type(project_root)

    # Scan files
    files = scan_project_files(project_root)

    # Build structure
    structure = build_project_structure(files)

    # Get git branch
    git_branch = get_git_branch(project_root)

    # Generate description
    description = f"{project_type.title()} project"
    if git_branch:
        description += f" on branch '{git_branch}'"
    description += f" with {len(files)} files"

    return ProjectInfo(
        root=project_root,
        name=project_root.name,
        type=project_type,
        files=files,
        structure=structure,
        git_branch=git_branch,
        description=description,
    )


def get_project_context_prompt(project: ProjectInfo) -> str:
    """Generate a context prompt for the LLM about the current project."""
    lines = [
        f"## Current Project: {project.name}",
        f"Type: {project.type}",
        f"Root: {project.root}",
    ]

    if project.git_branch:
        lines.append(f"Git Branch: {project.git_branch}")

    lines.append(f"Files: {len(project.files)} total")
    lines.append("")

    # Show structure
    lines.append("### Project Structure:")
    lines.append("```")
    tree = format_structure_tree(project.structure, max_depth=3)
    if tree:
        lines.append(tree)
    lines.append("```")

    # Key files based on project type
    key_files = []
    if project.type == "swift":
        key_files = [f for f in project.files if f.endswith((".swift", ".xib", ".storyboard"))][:20]
    elif project.type == "python":
        key_files = [f for f in project.files if f.endswith(".py")][:20]
    elif project.type == "node":
        key_files = [f for f in project.files if f.endswith((".js", ".ts", ".tsx", ".jsx"))][:20]

    if key_files:
        lines.append("")
        lines.append(f"### Key {project.type.title()} Files:")
        for f in key_files:
            lines.append(f"- {f}")

    return "\n".join(lines)


# =============================================================================
# Centralized Configuration System
# =============================================================================


class ConfigSource(Enum):
    """Configuration source priority (lower = higher priority)."""
    CLI = 1           # Command line arguments (highest priority)
    ENV = 2           # Environment variables
    PROJECT = 3       # Project-local config (.roura/config.toml)
    USER = 4          # User config (~/.config/roura/config.toml)
    GLOBAL = 5        # Global/system config
    DEFAULT = 6       # Built-in defaults (lowest priority)


@dataclass
class ConfigValue(Generic[T]):
    """A configuration value with metadata."""
    value: T
    source: ConfigSource
    key: str
    description: str = ""


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 60.0
    max_retries: int = 3


@dataclass
class ToolsConfig:
    """Tools configuration."""
    enabled: list[str] = field(default_factory=lambda: ["all"])
    disabled: list[str] = field(default_factory=list)
    require_approval: list[str] = field(default_factory=lambda: ["shell_exec", "fs_write", "git_commit"])
    auto_approve_patterns: list[str] = field(default_factory=list)
    timeout: float = 30.0


@dataclass
class MemoryConfig:
    """Memory/RAG configuration."""
    enabled: bool = True
    storage_path: Optional[str] = None
    max_entries: int = 1000
    embedding_model: str = "default"
    similarity_threshold: float = 0.7


@dataclass
class MCPConfig:
    """MCP server configuration."""
    enabled: bool = True
    servers: dict[str, dict] = field(default_factory=dict)
    auto_connect: list[str] = field(default_factory=list)
    timeout: float = 30.0


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None
    json_format: bool = False
    include_timestamps: bool = True


@dataclass
class UIConfig:
    """User interface configuration."""
    color: bool = True
    spinner: bool = True
    show_tokens: bool = False
    show_cost: bool = False
    compact_mode: bool = False
    markdown_output: bool = True


@dataclass
class SecurityConfig:
    """Security configuration."""
    allow_network: bool = True
    allow_shell: bool = True
    sandbox_mode: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=lambda: ["/etc", "/var", "/usr"])
    max_file_size: int = 10 * 1024 * 1024  # 10MB


@dataclass
class RouraConfig:
    """Main configuration container for centralized config system."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Project info
    project_root: Optional[str] = None
    project_name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouraConfig:
        """Create config from dictionary."""
        config = cls()

        if "llm" in data:
            config.llm = LLMConfig(**data["llm"])
        if "tools" in data:
            config.tools = ToolsConfig(**data["tools"])
        if "memory" in data:
            config.memory = MemoryConfig(**data["memory"])
        if "mcp" in data:
            config.mcp = MCPConfig(**data["mcp"])
        if "logging" in data:
            config.logging = LoggingConfig(**data["logging"])
        if "ui" in data:
            config.ui = UIConfig(**data["ui"])
        if "security" in data:
            config.security = SecurityConfig(**data["security"])
        if "project_root" in data:
            config.project_root = data["project_root"]
        if "project_name" in data:
            config.project_name = data["project_name"]

        return config


def _load_toml(path: Path) -> dict[str, Any]:
    """Load configuration from TOML file."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_json(path: Path) -> dict[str, Any]:
    """Load configuration from JSON file."""
    with open(path) as f:
        return json.load(f)


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("PyYAML is required for YAML config files: pip install pyyaml")


def load_config_file(path: Path) -> dict[str, Any]:
    """Load configuration from file based on extension."""
    if not path.exists():
        return {}

    suffix = path.suffix.lower()

    if suffix == ".toml":
        return _load_toml(path)
    elif suffix == ".json":
        return _load_json(path)
    elif suffix in (".yaml", ".yml"):
        return _load_yaml(path)
    else:
        raise ValueError(f"Unsupported config file format: {suffix}")


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, override takes precedence."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def _env_to_config(prefix: str = "ROURA_") -> dict[str, Any]:
    """Extract configuration from environment variables."""
    config: dict[str, Any] = {}

    env_mapping = {
        # LLM
        f"{prefix}LLM_PROVIDER": ("llm", "provider"),
        f"{prefix}LLM_MODEL": ("llm", "model"),
        f"{prefix}LLM_API_KEY": ("llm", "api_key"),
        f"{prefix}LLM_BASE_URL": ("llm", "base_url"),
        f"{prefix}LLM_MAX_TOKENS": ("llm", "max_tokens", int),
        f"{prefix}LLM_TEMPERATURE": ("llm", "temperature", float),
        f"{prefix}LLM_TIMEOUT": ("llm", "timeout", float),
        # Also support common API key env vars
        "ANTHROPIC_API_KEY": ("llm", "api_key"),
        "OPENAI_API_KEY": ("llm", "api_key"),
        # Logging
        f"{prefix}LOG_LEVEL": ("logging", "level"),
        f"{prefix}LOG_FILE": ("logging", "file"),
        f"{prefix}LOG_JSON": ("logging", "json_format", lambda x: x.lower() == "true"),
        # UI
        f"{prefix}COLOR": ("ui", "color", lambda x: x.lower() != "false"),
        f"{prefix}SPINNER": ("ui", "spinner", lambda x: x.lower() != "false"),
        f"{prefix}SHOW_TOKENS": ("ui", "show_tokens", lambda x: x.lower() == "true"),
        f"{prefix}SHOW_COST": ("ui", "show_cost", lambda x: x.lower() == "true"),
        # Security
        f"{prefix}ALLOW_NETWORK": ("security", "allow_network", lambda x: x.lower() != "false"),
        f"{prefix}ALLOW_SHELL": ("security", "allow_shell", lambda x: x.lower() != "false"),
        f"{prefix}SANDBOX_MODE": ("security", "sandbox_mode", lambda x: x.lower() == "true"),
        # Memory
        f"{prefix}MEMORY_ENABLED": ("memory", "enabled", lambda x: x.lower() != "false"),
        f"{prefix}MEMORY_PATH": ("memory", "storage_path"),
        # MCP
        f"{prefix}MCP_ENABLED": ("mcp", "enabled", lambda x: x.lower() != "false"),
    }

    for env_var, mapping in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            section, key = mapping[0], mapping[1]
            converter = mapping[2] if len(mapping) > 2 else str

            if section not in config:
                config[section] = {}

            try:
                config[section][key] = converter(value)  # type: ignore
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid value for {env_var}: {value} - {e}")

    return config


class ConfigManager:
    """
    Centralized configuration manager.

    Loads configuration from multiple sources in priority order:
    1. CLI arguments (highest)
    2. Environment variables
    3. Project config (.roura/config.toml)
    4. User config (~/.config/roura/config.toml)
    5. Built-in defaults (lowest)

    Example:
        config = ConfigManager()
        config.load()

        # Access config values
        model = config.get("llm.model")
        api_key = config.get("llm.api_key")

        # Get typed config objects
        llm_config = config.llm
        tools_config = config.tools
    """

    # Standard config file locations
    USER_CONFIG_DIR = Path.home() / ".config" / "roura"
    PROJECT_CONFIG_DIR = ".roura"
    CONFIG_FILENAMES = ["config.toml", "config.json", "config.yaml", "config.yml"]

    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root or Path.cwd()
        self._config = RouraConfig()
        self._sources: dict[str, ConfigSource] = {}
        self._cli_overrides: dict[str, Any] = {}
        self._loaded = False

    @property
    def config(self) -> RouraConfig:
        """Get the current configuration."""
        if not self._loaded:
            self.load()
        return self._config

    @property
    def llm(self) -> LLMConfig:
        """Get LLM configuration."""
        return self.config.llm

    @property
    def tools(self) -> ToolsConfig:
        """Get tools configuration."""
        return self.config.tools

    @property
    def memory(self) -> MemoryConfig:
        """Get memory configuration."""
        return self.config.memory

    @property
    def mcp(self) -> MCPConfig:
        """Get MCP configuration."""
        return self.config.mcp

    @property
    def logging_config(self) -> LoggingConfig:
        """Get logging configuration."""
        return self.config.logging

    @property
    def ui(self) -> UIConfig:
        """Get UI configuration."""
        return self.config.ui

    @property
    def security(self) -> SecurityConfig:
        """Get security configuration."""
        return self.config.security

    def set_cli_override(self, key: str, value: Any) -> None:
        """Set a CLI override (highest priority)."""
        self._cli_overrides[key] = value
        self._apply_overrides()

    def _find_config_file(self, directory: Path) -> Optional[Path]:
        """Find a config file in the given directory."""
        for filename in self.CONFIG_FILENAMES:
            path = directory / filename
            if path.exists():
                return path
        return None

    def _find_project_root(self) -> Optional[Path]:
        """Find the project root by looking for .roura, .git, or pyproject.toml."""
        current = self._project_root

        while current != current.parent:
            # Check for .roura directory
            if (current / self.PROJECT_CONFIG_DIR).exists():
                return current
            # Check for .git
            if (current / ".git").exists():
                return current
            # Check for pyproject.toml
            if (current / "pyproject.toml").exists():
                return current
            current = current.parent

        return self._project_root

    def load(self, reload: bool = False) -> RouraConfig:
        """
        Load configuration from all sources.

        Args:
            reload: Force reload even if already loaded

        Returns:
            The loaded configuration
        """
        if self._loaded and not reload:
            return self._config

        # Start with defaults
        config_data: dict[str, Any] = {}

        # Find project root
        project_root = self._find_project_root()

        # 1. Load user config (lowest priority after defaults)
        user_config_file = self._find_config_file(self.USER_CONFIG_DIR)
        if user_config_file:
            try:
                user_data = load_config_file(user_config_file)
                config_data = _deep_merge(config_data, user_data)
                self._record_sources(user_data, ConfigSource.USER)
                logger.debug(f"Loaded user config from {user_config_file}")
            except Exception as e:
                logger.warning(f"Failed to load user config: {e}")

        # 2. Load project config
        if project_root:
            project_config_dir = project_root / self.PROJECT_CONFIG_DIR
            project_config_file = self._find_config_file(project_config_dir)
            if project_config_file:
                try:
                    project_data = load_config_file(project_config_file)
                    config_data = _deep_merge(config_data, project_data)
                    self._record_sources(project_data, ConfigSource.PROJECT)
                    logger.debug(f"Loaded project config from {project_config_file}")
                except Exception as e:
                    logger.warning(f"Failed to load project config: {e}")

        # 3. Load environment variables
        env_data = _env_to_config()
        if env_data:
            config_data = _deep_merge(config_data, env_data)
            self._record_sources(env_data, ConfigSource.ENV)

        # 4. Apply CLI overrides (highest priority)
        if self._cli_overrides:
            cli_data = self._flatten_to_nested(self._cli_overrides)
            config_data = _deep_merge(config_data, cli_data)
            self._record_sources(cli_data, ConfigSource.CLI)

        # Set project info
        if project_root:
            config_data["project_root"] = str(project_root)
            config_data["project_name"] = project_root.name

        # Build final config
        self._config = RouraConfig.from_dict(config_data)
        self._loaded = True

        return self._config

    def _record_sources(self, data: dict[str, Any], source: ConfigSource, prefix: str = "") -> None:
        """Record the source of each config value."""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._record_sources(value, source, full_key)
            else:
                self._sources[full_key] = source

    def _flatten_to_nested(self, flat: dict[str, Any]) -> dict[str, Any]:
        """Convert flat dotted keys to nested dict."""
        result: dict[str, Any] = {}

        for key, value in flat.items():
            parts = key.split(".")
            current = result

            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            current[parts[-1]] = value

        return result

    def _apply_overrides(self) -> None:
        """Apply CLI overrides to loaded config."""
        if self._loaded:
            cli_data = self._flatten_to_nested(self._cli_overrides)
            config_data = self._config.to_dict()
            config_data = _deep_merge(config_data, cli_data)
            self._config = RouraConfig.from_dict(config_data)
            # Record sources for CLI overrides
            self._record_sources(cli_data, ConfigSource.CLI)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a config value by dotted key.

        Args:
            key: Dotted key path (e.g., "llm.model")
            default: Default value if not found

        Returns:
            The config value
        """
        if not self._loaded:
            self.load()

        parts = key.split(".")
        value: Any = self._config.to_dict()

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def get_source(self, key: str) -> Optional[ConfigSource]:
        """Get the source of a config value."""
        return self._sources.get(key)

    def validate(self) -> list[str]:
        """
        Validate the current configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Validate LLM config
        if not self._config.llm.provider:
            errors.append("llm.provider is required")

        if self._config.llm.max_tokens < 1:
            errors.append("llm.max_tokens must be positive")

        if not 0 <= self._config.llm.temperature <= 2:
            errors.append("llm.temperature must be between 0 and 2")

        # Validate tools config
        if self._config.tools.timeout <= 0:
            errors.append("tools.timeout must be positive")

        # Validate memory config
        if self._config.memory.max_entries < 1:
            errors.append("memory.max_entries must be positive")

        if not 0 <= self._config.memory.similarity_threshold <= 1:
            errors.append("memory.similarity_threshold must be between 0 and 1")

        # Validate security config
        if self._config.security.max_file_size < 1:
            errors.append("security.max_file_size must be positive")

        return errors

    def save_user_config(self, overwrite: bool = False) -> Path:
        """
        Save current configuration to user config file.

        Args:
            overwrite: Overwrite existing config

        Returns:
            Path to saved config file
        """
        config_dir = self.USER_CONFIG_DIR
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "config.toml"

        if config_file.exists() and not overwrite:
            raise FileExistsError(f"Config already exists: {config_file}")

        # Convert to TOML format
        try:
            import tomli_w
            with open(config_file, "wb") as f:
                tomli_w.dump(self._config.to_dict(), f)
        except ImportError:
            # Fallback to JSON
            config_file = config_dir / "config.json"
            with open(config_file, "w") as f:
                json.dump(self._config.to_dict(), f, indent=2)

        logger.info(f"Saved config to {config_file}")
        return config_file

    def init_project_config(self, path: Optional[Path] = None) -> Path:
        """
        Initialize a project configuration file.

        Args:
            path: Project root (defaults to current directory)

        Returns:
            Path to created config file
        """
        project_root = path or self._project_root
        config_dir = project_root / self.PROJECT_CONFIG_DIR
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "config.toml"

        if config_file.exists():
            raise FileExistsError(f"Project config already exists: {config_file}")

        # Create minimal project config
        project_config = {
            "project_name": project_root.name,
            "llm": {
                "model": self._config.llm.model,
            },
            "tools": {
                "require_approval": self._config.tools.require_approval,
            },
        }

        try:
            import tomli_w
            with open(config_file, "wb") as f:
                tomli_w.dump(project_config, f)
        except ImportError:
            config_file = config_dir / "config.json"
            with open(config_file, "w") as f:
                json.dump(project_config, f, indent=2)

        logger.info(f"Initialized project config at {config_file}")
        return config_file

    def show(self, show_secrets: bool = False) -> dict[str, Any]:
        """
        Get configuration for display.

        Args:
            show_secrets: Include sensitive values like API keys

        Returns:
            Configuration dict with secrets optionally masked
        """
        config = self._config.to_dict()

        if not show_secrets:
            # Mask sensitive values
            sensitive_keys = ["api_key", "token", "secret", "password"]

            def mask_sensitive(d: dict) -> dict:
                result = {}
                for k, v in d.items():
                    if isinstance(v, dict):
                        result[k] = mask_sensitive(v)
                    elif any(s in k.lower() for s in sensitive_keys) and v:
                        result[k] = "***"
                    else:
                        result[k] = v
                return result

            config = mask_sensitive(config)

        return config


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def reset_config_manager() -> None:
    """Reset the global configuration manager."""
    global _config_manager
    _config_manager = None
