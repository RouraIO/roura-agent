"""
Roura Agent Secrets Detection - Prevent accidental credential exposure.

Scans content for potential secrets before:
- Writing files
- Committing to git
- Logging output

© Roura.io
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SecretMatch:
    """A detected secret in content."""
    type: str  # api_key, password, token, etc.
    pattern_name: str
    line_number: int
    column: int
    length: int
    redacted_preview: str  # First few chars + ***

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "pattern_name": self.pattern_name,
            "line_number": self.line_number,
            "column": self.column,
            "length": self.length,
            "redacted_preview": self.redacted_preview,
        }


# Secret detection patterns
# Each pattern: (name, type, regex, min_length)
SECRET_PATTERNS = [
    # API Keys
    ("aws_access_key", "api_key", r"AKIA[0-9A-Z]{16}", 20),
    ("aws_secret_key", "api_key", r"[A-Za-z0-9/+=]{40}", 40),
    ("openai_api_key", "api_key", r"sk-[A-Za-z0-9]{48,}", 50),
    ("anthropic_api_key", "api_key", r"sk-ant-[A-Za-z0-9-]{90,}", 95),
    ("github_token", "token", r"gh[pousr]_[A-Za-z0-9]{36,}", 40),
    ("github_pat", "token", r"github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}", 82),
    ("gitlab_token", "token", r"glpat-[A-Za-z0-9\-_]{20,}", 26),
    ("slack_token", "token", r"xox[baprs]-[A-Za-z0-9\-]{10,}", 15),
    ("slack_webhook", "webhook", r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+", 50),
    ("stripe_key", "api_key", r"sk_(?:live|test)_[A-Za-z0-9]{24,}", 30),
    ("stripe_restricted", "api_key", r"rk_(?:live|test)_[A-Za-z0-9]{24,}", 30),
    ("twilio_key", "api_key", r"SK[a-f0-9]{32}", 34),
    ("sendgrid_key", "api_key", r"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}", 69),
    ("mailchimp_key", "api_key", r"[a-f0-9]{32}-us\d{1,2}", 35),
    ("heroku_key", "api_key", r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", 36),
    ("npm_token", "token", r"npm_[A-Za-z0-9]{36}", 40),
    ("pypi_token", "token", r"pypi-[A-Za-z0-9\-_]{50,}", 55),
    ("docker_token", "token", r"dckr_pat_[A-Za-z0-9\-_]{27}", 36),

    # Private Keys
    ("rsa_private_key", "private_key", r"-----BEGIN RSA PRIVATE KEY-----", 31),
    ("dsa_private_key", "private_key", r"-----BEGIN DSA PRIVATE KEY-----", 31),
    ("ec_private_key", "private_key", r"-----BEGIN EC PRIVATE KEY-----", 30),
    ("openssh_private_key", "private_key", r"-----BEGIN OPENSSH PRIVATE KEY-----", 35),
    ("pgp_private_key", "private_key", r"-----BEGIN PGP PRIVATE KEY BLOCK-----", 37),

    # Generic secrets
    ("generic_api_key", "api_key", r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9\-_]{20,}['\"]", 25),
    ("generic_secret", "secret", r"(?i)secret[_-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9\-_]{20,}['\"]", 25),
    ("generic_password", "password", r"(?i)password['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]", 15),
    ("generic_token", "token", r"(?i)(?:access|auth|bearer)[_-]?token['\"]?\s*[:=]\s*['\"][A-Za-z0-9\-_.]{20,}['\"]", 25),

    # Connection strings
    ("postgres_url", "connection_string", r"postgres(?:ql)?://[^:]+:[^@]+@[^\s]+", 20),
    ("mysql_url", "connection_string", r"mysql://[^:]+:[^@]+@[^\s]+", 15),
    ("mongodb_url", "connection_string", r"mongodb(?:\+srv)?://[^:]+:[^@]+@[^\s]+", 20),
    ("redis_url", "connection_string", r"redis://:[^@]+@[^\s]+", 15),

    # JWT
    ("jwt_token", "token", r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", 50),

    # Base64 encoded secrets (high entropy, long)
    ("base64_secret", "encoded_secret", r"(?:[A-Za-z0-9+/]{4}){10,}={0,2}", 40),
]

# Files that typically contain secrets (warn but don't block)
SECRET_FILE_PATTERNS = [
    r"\.env$",
    r"\.env\.\w+$",
    r"credentials\.json$",
    r"secrets\.json$",
    r"secrets\.ya?ml$",
    r"\.pem$",
    r"\.key$",
    r"id_rsa$",
    r"id_ed25519$",
    r"\.p12$",
    r"\.pfx$",
]

# Common false positive patterns to ignore
FALSE_POSITIVE_PATTERNS = [
    r"example",
    r"placeholder",
    r"your[_-]?(?:api[_-]?)?key",
    r"xxx+",
    r"test",
    r"dummy",
    r"fake",
    r"sample",
    r"<[^>]+>",  # Template placeholders
    r"\$\{[^}]+\}",  # Variable substitution
    r"\{\{[^}]+\}\}",  # Mustache templates
]


def is_false_positive(content: str, match_start: int, match_end: int) -> bool:
    """Check if a match is likely a false positive."""
    # Get surrounding context
    context_start = max(0, match_start - 50)
    context_end = min(len(content), match_end + 50)
    context = content[context_start:context_end].lower()

    # Check for false positive patterns
    for pattern in FALSE_POSITIVE_PATTERNS:
        if re.search(pattern, context, re.IGNORECASE):
            return True

    return False


def redact_secret(secret: str, show_chars: int = 4) -> str:
    """Redact a secret, showing only first few characters."""
    if len(secret) <= show_chars:
        return "*" * len(secret)
    return secret[:show_chars] + "*" * (len(secret) - show_chars)


def scan_content(content: str, filename: Optional[str] = None) -> list[SecretMatch]:
    """
    Scan content for potential secrets.

    Args:
        content: The text content to scan
        filename: Optional filename for context

    Returns:
        List of SecretMatch objects for detected secrets
    """
    matches = []
    lines = content.split("\n")

    for pattern_name, secret_type, pattern, min_length in SECRET_PATTERNS:
        for match in re.finditer(pattern, content):
            matched_text = match.group()

            # Skip if too short
            if len(matched_text) < min_length:
                continue

            # Skip false positives
            if is_false_positive(content, match.start(), match.end()):
                continue

            # Calculate line and column
            line_start = content.rfind("\n", 0, match.start()) + 1
            line_number = content[:match.start()].count("\n") + 1
            column = match.start() - line_start + 1

            matches.append(SecretMatch(
                type=secret_type,
                pattern_name=pattern_name,
                line_number=line_number,
                column=column,
                length=len(matched_text),
                redacted_preview=redact_secret(matched_text),
            ))

    # Deduplicate (same position might match multiple patterns)
    seen = set()
    unique_matches = []
    for m in matches:
        key = (m.line_number, m.column, m.length)
        if key not in seen:
            seen.add(key)
            unique_matches.append(m)

    return unique_matches


def scan_file(file_path: str) -> list[SecretMatch]:
    """Scan a file for secrets."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return scan_content(content, filename=file_path)
    except Exception:
        return []


def is_secret_file(filename: str) -> bool:
    """Check if a filename matches known secret file patterns."""
    for pattern in SECRET_FILE_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            return True
    return False


def redact_secrets_in_content(content: str) -> str:
    """Redact all detected secrets in content."""
    matches = scan_content(content)

    # Sort by position (reverse) to replace from end to start
    matches.sort(key=lambda m: (m.line_number, m.column), reverse=True)

    lines = content.split("\n")
    for match in matches:
        line_idx = match.line_number - 1
        if 0 <= line_idx < len(lines):
            line = lines[line_idx]
            col = match.column - 1
            # Replace the secret with redacted version
            lines[line_idx] = (
                line[:col] +
                "*" * match.length +
                line[col + match.length:]
            )

    return "\n".join(lines)


def check_before_write(content: str, file_path: str) -> tuple[bool, list[SecretMatch]]:
    """
    Check content for secrets before writing to file.

    Returns:
        Tuple of (is_safe, matches)
        - is_safe: True if no secrets detected
        - matches: List of detected secrets
    """
    matches = scan_content(content, filename=file_path)

    # Also check if writing to a known secret file
    if is_secret_file(file_path):
        # Don't block, but add a warning
        pass

    return len(matches) == 0, matches


def check_before_commit(file_paths: list[str]) -> dict[str, list[SecretMatch]]:
    """
    Check multiple files for secrets before git commit.

    Returns:
        Dict mapping file paths to their detected secrets
    """
    results = {}

    for file_path in file_paths:
        matches = scan_file(file_path)
        if matches:
            results[file_path] = matches

    return results


def format_secret_warning(matches: list[SecretMatch], file_path: Optional[str] = None) -> str:
    """Format a warning message for detected secrets."""
    lines = []

    if file_path:
        lines.append(f"⚠️  SECRETS DETECTED in {file_path}")
    else:
        lines.append("⚠️  SECRETS DETECTED")

    lines.append("")

    for match in matches:
        lines.append(
            f"  Line {match.line_number}: {match.pattern_name} ({match.type})"
        )
        lines.append(f"    Preview: {match.redacted_preview}")
        lines.append("")

    lines.append("These secrets will NOT be written/committed.")
    lines.append("Remove or redact them before proceeding.")

    return "\n".join(lines)
