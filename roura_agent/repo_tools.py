"""
Roura Agent Repo Tools - File listing, searching, and reading.

Provides tools for exploring and understanding codebases.

© Roura.io
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


# Directories to ignore when scanning
IGNORE_DIRS = frozenset([
    ".git", ".svn", ".hg", ".venv", "venv", "env", ".env",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".tox", "build", "dist", "DerivedData", ".build", "Pods",
    "target", ".next", ".nuxt", "coverage", ".coverage",
    ".idea", ".vscode", "*.egg-info",
])

# Default file patterns for code search
DEFAULT_CODE_GLOBS = [
    "**/*.py", "**/*.swift", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx",
    "**/*.go", "**/*.rs", "**/*.java", "**/*.kt", "**/*.rb", "**/*.php",
    "**/*.c", "**/*.cpp", "**/*.h", "**/*.hpp",
    "**/*.md", "**/*.yml", "**/*.yaml", "**/*.json", "**/*.toml",
]


def _should_ignore(path: Path) -> bool:
    """Check if a path should be ignored."""
    parts = path.parts
    for part in parts:
        if part in IGNORE_DIRS:
            return True
        if part.startswith(".") and part not in (".", ".."):
            # Ignore hidden directories except current/parent
            if path.is_dir():
                return True
    return False


def list_files(
    root: Path,
    globs: Optional[list[str]] = None,
    max_files: int = 10000,
) -> list[str]:
    """
    List files in a directory matching glob patterns.

    Args:
        root: Root directory to search
        globs: Glob patterns to match (default: common code files)
        max_files: Maximum number of files to return

    Returns:
        List of relative file paths
    """
    root = Path(root).resolve()
    if not root.exists():
        return []

    globs = globs or DEFAULT_CODE_GLOBS
    files = []
    seen = set()

    for glob_pattern in globs:
        try:
            # Remove leading **/ if present since rglob is already recursive
            pattern = glob_pattern
            if pattern.startswith("**/"):
                pattern = pattern[3:]
            for path in root.rglob(pattern):
                if len(files) >= max_files:
                    break
                if not path.is_file():
                    continue
                if _should_ignore(path):
                    continue

                rel_path = str(path.relative_to(root))
                if rel_path not in seen:
                    seen.add(rel_path)
                    files.append(rel_path)
        except Exception:
            continue

    return sorted(files)


def search_symbol(
    root: Path,
    pattern: str,
    globs: Optional[list[str]] = None,
    max_results: int = 100,
    use_regex: bool = True,
) -> list[dict]:
    """
    Search for a symbol/pattern in files.

    Uses ripgrep if available, falls back to Python scanning.

    Args:
        root: Root directory to search
        pattern: Pattern to search for
        globs: File patterns to search in
        max_results: Maximum results to return
        use_regex: Whether to use regex matching

    Returns:
        List of {path, line_no, line_text} dicts
    """
    root = Path(root).resolve()
    globs = globs or DEFAULT_CODE_GLOBS
    results = []

    # Try ripgrep first (faster)
    if _has_ripgrep():
        results = _search_with_ripgrep(root, pattern, globs, max_results, use_regex)
        if results:
            return results

    # Fallback to Python scanning
    return _search_with_python(root, pattern, globs, max_results, use_regex)


def _has_ripgrep() -> bool:
    """Check if ripgrep is available."""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _search_with_ripgrep(
    root: Path,
    pattern: str,
    globs: list[str],
    max_results: int,
    use_regex: bool,
) -> list[dict]:
    """Search using ripgrep."""
    results = []

    try:
        cmd = ["rg", "--json", "-n", "--max-count", str(max_results)]

        if not use_regex:
            cmd.append("-F")  # Fixed strings

        # Add glob patterns
        for glob in globs:
            cmd.extend(["-g", glob])

        cmd.append(pattern)
        cmd.append(str(root))

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        import json
        for line in proc.stdout.splitlines():
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data.get("data", {})
                    path_data = match_data.get("path", {})
                    path = path_data.get("text", "")
                    line_no = match_data.get("line_number", 0)
                    lines = match_data.get("lines", {})
                    line_text = lines.get("text", "").strip()

                    if path:
                        # Make path relative
                        try:
                            rel_path = str(Path(path).relative_to(root))
                        except ValueError:
                            rel_path = path

                        results.append({
                            "path": rel_path,
                            "line_no": line_no,
                            "line_text": line_text[:200],  # Truncate long lines
                        })

                        if len(results) >= max_results:
                            break
            except json.JSONDecodeError:
                continue

    except Exception:
        pass

    return results


def _search_with_python(
    root: Path,
    pattern: str,
    globs: list[str],
    max_results: int,
    use_regex: bool,
) -> list[dict]:
    """Search using pure Python (fallback)."""
    results = []

    if use_regex:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = None
    else:
        regex = None

    files = list_files(root, globs)

    for file_path in files:
        if len(results) >= max_results:
            break

        full_path = root / file_path
        try:
            content = full_path.read_text(errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if len(results) >= max_results:
                    break

                matched = False
                if regex:
                    matched = bool(regex.search(line))
                else:
                    matched = pattern.lower() in line.lower()

                if matched:
                    results.append({
                        "path": file_path,
                        "line_no": i,
                        "line_text": line.strip()[:200],
                    })
        except Exception:
            continue

    return results


def read_file(path: Path, max_bytes: int = 200_000) -> str:
    """
    Read a file with size limiting.

    Args:
        path: Path to file
        max_bytes: Maximum bytes to read (default 200KB)

    Returns:
        File content (possibly truncated)
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    size = path.stat().st_size

    if size <= max_bytes:
        return path.read_text(errors="replace")

    # Read truncated with marker
    with open(path, "r", errors="replace") as f:
        content = f.read(max_bytes)

    return content + f"\n\n[... TRUNCATED: {size - max_bytes:,} bytes remaining ...]"


def read_files(paths: list[Path], max_bytes_per_file: int = 200_000) -> dict[str, str]:
    """
    Batch read multiple files.

    Args:
        paths: List of file paths
        max_bytes_per_file: Max bytes per file

    Returns:
        Dict mapping path strings to content
    """
    results = {}

    for path in paths:
        path = Path(path)
        try:
            results[str(path)] = read_file(path, max_bytes_per_file)
        except Exception as e:
            results[str(path)] = f"[ERROR: {e}]"

    return results


def get_file_info(path: Path) -> dict:
    """Get metadata about a file."""
    path = Path(path)

    if not path.exists():
        return {"exists": False, "path": str(path)}

    stat = path.stat()

    info = {
        "exists": True,
        "path": str(path),
        "name": path.name,
        "extension": path.suffix,
        "size_bytes": stat.st_size,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }

    if path.is_file():
        try:
            content = path.read_text(errors="ignore")
            info["line_count"] = len(content.splitlines())
        except Exception:
            info["line_count"] = 0

    return info
