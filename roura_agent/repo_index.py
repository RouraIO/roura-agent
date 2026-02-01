"""
Roura Agent Repo Index - Persistent repository intelligence.

Builds and caches metadata about codebases for faster exploration.

© Roura.io
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict

from .repo_tools import list_files, read_file, IGNORE_DIRS


@dataclass
class RepoIndex:
    """
    Cached repository metadata for fast lookups.

    Stored at .roura/index.json within the repo.
    """
    root: str
    file_count_by_ext: dict[str, int] = field(default_factory=dict)
    largest_files: list[tuple[str, int]] = field(default_factory=list)  # (path, lines)
    symbol_hits_cache: dict[str, list[dict]] = field(default_factory=dict)
    generated_at: float = field(default_factory=time.time)
    total_files: int = 0
    total_lines: int = 0
    primary_language: str = ""
    key_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)


# Language extensions for classification
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c/cpp",
    ".cs": "csharp",
}

# Key file patterns
KEY_FILE_PATTERNS = [
    "main.py", "app.py", "cli.py", "__main__.py",
    "main.swift", "App.swift", "AppDelegate.swift",
    "index.ts", "index.js", "app.ts", "app.js",
    "main.go", "main.rs", "lib.rs",
    "router", "orchestrator", "executor", "loop",
]

# Config file patterns
CONFIG_PATTERNS = [
    "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "tsconfig.json",
    "Cargo.toml", "go.mod",
    "Package.swift",
    ".github/workflows",
    "docker-compose", "Dockerfile",
    "Makefile", "justfile",
]


def build_repo_index(root: Path, max_files: int = 5000) -> RepoIndex:
    """
    Build a comprehensive index of a repository.

    Args:
        root: Repository root directory
        max_files: Maximum files to scan

    Returns:
        RepoIndex with collected metadata
    """
    root = Path(root).resolve()

    index = RepoIndex(root=str(root))

    # Count files by extension
    ext_counts: dict[str, int] = defaultdict(int)
    file_lines: list[tuple[str, int]] = []
    test_files: list[str] = []
    config_files: list[str] = []
    key_files: list[str] = []
    total_lines = 0

    # Get all files
    all_files = list_files(root, max_files=max_files)
    index.total_files = len(all_files)

    for rel_path in all_files:
        full_path = root / rel_path
        ext = full_path.suffix.lower()

        # Count by extension
        if ext:
            ext_counts[ext] += 1

        # Check for test files
        name_lower = rel_path.lower()
        if "test" in name_lower or "spec" in name_lower:
            test_files.append(rel_path)

        # Check for config files
        for pattern in CONFIG_PATTERNS:
            if pattern.lower() in name_lower:
                config_files.append(rel_path)
                break

        # Check for key files
        for pattern in KEY_FILE_PATTERNS:
            if pattern.lower() in name_lower:
                key_files.append(rel_path)
                break

        # Count lines for code files
        if ext in LANGUAGE_EXTENSIONS:
            try:
                content = full_path.read_text(errors="ignore")
                lines = len(content.splitlines())
                total_lines += lines
                file_lines.append((rel_path, lines))
            except Exception:
                pass

    # Sort by line count and take top 50
    file_lines.sort(key=lambda x: x[1], reverse=True)
    index.largest_files = file_lines[:50]

    # Store results
    index.file_count_by_ext = dict(ext_counts)
    index.total_lines = total_lines
    index.test_files = test_files[:100]
    index.config_files = config_files[:20]
    index.key_files = key_files[:30]

    # Determine primary language
    lang_lines: dict[str, int] = defaultdict(int)
    for rel_path, lines in file_lines:
        ext = Path(rel_path).suffix.lower()
        lang = LANGUAGE_EXTENSIONS.get(ext, "")
        if lang:
            lang_lines[lang] += lines

    if lang_lines:
        index.primary_language = max(lang_lines, key=lang_lines.get)

    return index


def load_index(root: Path) -> Optional[RepoIndex]:
    """
    Load cached index from .roura/index.json.

    Args:
        root: Repository root

    Returns:
        RepoIndex if exists, None otherwise
    """
    index_path = Path(root) / ".roura" / "index.json"

    if not index_path.exists():
        return None

    try:
        data = json.loads(index_path.read_text())

        # Convert lists of lists back to tuples for largest_files
        largest = data.get("largest_files", [])
        data["largest_files"] = [(p, l) for p, l in largest]

        return RepoIndex(**data)
    except Exception:
        return None


def save_index(index: RepoIndex, root: Optional[Path] = None) -> Path:
    """
    Save index to .roura/index.json.

    Args:
        index: RepoIndex to save
        root: Repository root (uses index.root if not provided)

    Returns:
        Path to saved index file
    """
    root = Path(root or index.root)
    roura_dir = root / ".roura"
    roura_dir.mkdir(exist_ok=True)

    index_path = roura_dir / "index.json"

    # Convert to dict for JSON serialization
    data = asdict(index)

    index_path.write_text(json.dumps(data, indent=2))
    return index_path


def get_or_build_index(root: Path, max_age_seconds: int = 3600) -> RepoIndex:
    """
    Get cached index or build a new one if stale/missing.

    Args:
        root: Repository root
        max_age_seconds: Maximum age before rebuild

    Returns:
        RepoIndex (cached or fresh)
    """
    root = Path(root).resolve()

    # Try to load cached
    cached = load_index(root)

    if cached:
        age = time.time() - cached.generated_at
        if age < max_age_seconds:
            return cached

    # Build fresh
    index = build_repo_index(root)
    save_index(index, root)
    return index


def get_largest_by_language(
    index: RepoIndex,
    language: str,
    limit: int = 10,
) -> list[tuple[str, int]]:
    """
    Get largest files for a specific language.

    Args:
        index: RepoIndex to query
        language: Language name (python, swift, etc.)
        limit: Maximum files to return

    Returns:
        List of (path, lines) tuples
    """
    # Find extensions for this language
    exts = [ext for ext, lang in LANGUAGE_EXTENSIONS.items() if lang == language]

    results = []
    for path, lines in index.largest_files:
        if Path(path).suffix.lower() in exts:
            results.append((path, lines))
            if len(results) >= limit:
                break

    return results


def get_index_summary(index: RepoIndex) -> str:
    """
    Get human-readable summary of index.

    Args:
        index: RepoIndex to summarize

    Returns:
        Formatted summary string
    """
    lines = [
        f"Repository: {index.root}",
        f"Total files: {index.total_files:,}",
        f"Total lines: {index.total_lines:,}",
        f"Primary language: {index.primary_language}",
        "",
        "Files by extension:",
    ]

    # Sort by count
    sorted_exts = sorted(
        index.file_count_by_ext.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    for ext, count in sorted_exts[:10]:
        lines.append(f"  {ext}: {count}")

    if index.largest_files:
        lines.append("")
        lines.append("Largest files:")
        for path, line_count in index.largest_files[:5]:
            lines.append(f"  {path}: {line_count} lines")

    return "\n".join(lines)
