"""
Roura Agent Configuration - Secure credential storage and project detection.

© Roura.io
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
import stat


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
    def from_dict(cls, data: dict) -> "Config":
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
    def from_dict(cls, data: dict) -> "Credentials":
        return cls(**data)


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
