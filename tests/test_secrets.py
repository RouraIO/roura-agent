"""
Tests for Roura Agent Secrets Detection.

© Roura.io
"""
import pytest

from roura_agent.secrets import (
    scan_content,
    scan_file,
    is_secret_file,
    is_false_positive,
    redact_secret,
    redact_secrets_in_content,
    check_before_write,
    check_before_commit,
    format_secret_warning,
    SecretMatch,
)


class TestScanContent:
    """Tests for content scanning."""

    def test_detects_aws_access_key(self):
        """Detect AWS access key - requires 20 char key starting with AKIA."""
        # Real AWS access key format: AKIA + 16 alphanumeric chars
        content = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7REALKEY"
        matches = scan_content(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "aws_access_key" for m in matches)

    def test_detects_openai_key(self):
        """Detect OpenAI API key - requires sk- prefix + 48+ chars."""
        # OpenAI API key format: sk-[48+ alphanumeric chars]
        content = "OPENAI_API_KEY=sk-abcdefghij1234567890abcdefghij1234567890abcdefgh"
        matches = scan_content(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "openai_api_key" for m in matches)

    def test_detects_github_token(self):
        """Detect GitHub token - requires ghp_/gho_/ghu_/ghs_/ghr_ prefix + 36+ chars."""
        # GitHub token format: ghp_[36+ alphanumeric chars] - need exactly 36+ after prefix
        content = "GITHUB_TOKEN=ghp_abcdefghij1234567890abcdefghij123456"
        matches = scan_content(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "github_token" for m in matches)

    def test_detects_private_key(self):
        """Detect RSA private key."""
        content = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"""
        matches = scan_content(content)
        assert len(matches) >= 1
        assert any(m.type == "private_key" for m in matches)

    def test_detects_jwt_token(self):
        """Detect JWT token."""
        # A fake JWT token
        content = "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        matches = scan_content(content)
        assert len(matches) >= 1
        assert any(m.pattern_name == "jwt_token" for m in matches)

    def test_detects_postgres_connection_string(self):
        """Detect PostgreSQL connection string."""
        content = "DATABASE_URL=postgresql://user:password123@localhost:5432/mydb"
        matches = scan_content(content)
        assert len(matches) >= 1
        assert any(m.type == "connection_string" for m in matches)

    def test_detects_generic_api_key(self):
        """Detect generic API key pattern."""
        # Use a pattern that looks like an API key but isn't a real vendor format
        content = 'api_key = "rk_abcdef123456789012345678901234"'
        matches = scan_content(content)
        assert len(matches) >= 1

    def test_ignores_false_positives(self):
        """Ignore false positive patterns."""
        content = 'api_key = "your-api-key-here"'
        matches = scan_content(content)
        assert len(matches) == 0

    def test_ignores_placeholder_values(self):
        """Ignore placeholder values."""
        content = 'SECRET_KEY = "xxxxxxxxxxxxxxxxxxxxxxxx"'
        matches = scan_content(content)
        assert len(matches) == 0

    def test_ignores_example_values(self):
        """Ignore example values."""
        content = 'token = "example-token-placeholder"'
        matches = scan_content(content)
        assert len(matches) == 0

    def test_empty_content(self):
        """Handle empty content."""
        matches = scan_content("")
        assert len(matches) == 0


class TestIsFalsePositive:
    """Tests for false positive detection."""

    def test_example_is_false_positive(self):
        """'example' context is a false positive."""
        content = "example_api_key = 'AKIAIOSFODNN7EXAMPLE'"
        assert is_false_positive(content, 19, 39)

    def test_test_is_false_positive(self):
        """'test' context is a false positive."""
        content = "test_token = 'ghp_testxxxxxxxxxxxxxxxxxxxxxxxxxx'"
        assert is_false_positive(content, 14, 50)

    def test_real_key_is_not_false_positive(self):
        """Real key is not a false positive."""
        content = "production_key = 'AKIAIOSFODNN7REALKEY'"
        assert not is_false_positive(content, 19, 39)


class TestRedactSecret:
    """Tests for secret redaction."""

    def test_redact_long_secret(self):
        """Redact a long secret."""
        secret = "sk-1234567890abcdefghij"
        result = redact_secret(secret)
        # Shows first 4 chars, redacts the rest
        assert result.startswith("sk-1")
        assert "*" in result
        assert len(result) == len(secret)

    def test_redact_short_secret(self):
        """Redact a short secret."""
        result = redact_secret("abc")
        assert result == "***"

    def test_custom_show_chars(self):
        """Custom number of visible characters."""
        secret = "sk-1234567890"
        result = redact_secret(secret, show_chars=6)
        assert result.startswith("sk-123")
        assert len(result) == len(secret)


class TestIsSecretFile:
    """Tests for secret file detection."""

    def test_env_file(self):
        """Detect .env file."""
        assert is_secret_file(".env")
        assert is_secret_file(".env.local")
        assert is_secret_file(".env.production")

    def test_credentials_file(self):
        """Detect credentials file."""
        assert is_secret_file("credentials.json")

    def test_secrets_file(self):
        """Detect secrets file."""
        assert is_secret_file("secrets.json")
        assert is_secret_file("secrets.yaml")
        assert is_secret_file("secrets.yml")

    def test_key_file(self):
        """Detect key files."""
        assert is_secret_file("private.key")
        assert is_secret_file("server.pem")

    def test_ssh_keys(self):
        """Detect SSH key files."""
        assert is_secret_file("id_rsa")
        assert is_secret_file("id_ed25519")

    def test_normal_file(self):
        """Normal files are not secret files."""
        assert not is_secret_file("main.py")
        assert not is_secret_file("README.md")
        assert not is_secret_file("config.json")


class TestCheckBeforeWrite:
    """Tests for pre-write checking."""

    def test_safe_content(self):
        """Safe content passes."""
        is_safe, matches = check_before_write("print('hello')", "main.py")
        assert is_safe
        assert len(matches) == 0

    def test_unsafe_content(self):
        """Unsafe content is detected."""
        content = "OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnopqrstuvwxyz12345678"
        is_safe, matches = check_before_write(content, "config.py")
        assert not is_safe
        assert len(matches) >= 1


class TestRedactSecretsInContent:
    """Tests for content redaction."""

    def test_redact_single_secret(self):
        """Redact a single secret - uses valid token format."""
        # Use a real-looking token (need 36+ chars after prefix)
        content = "token=ghp_abcdefghij1234567890abcdefghij123456"
        redacted = redact_secrets_in_content(content)
        # Either the token is redacted (contains stars) or the original is not present
        assert "*" in redacted or "abcdefghij1234567890" not in redacted

    def test_preserve_structure(self):
        """Preserve content structure after redaction."""
        # Use a valid-looking OpenAI key format
        content = """line 1
OPENAI_API_KEY=sk-abcdefghij1234567890abcdefghij1234567890abcdefgh
line 3"""
        redacted = redact_secrets_in_content(content)
        lines = redacted.split("\n")
        assert len(lines) == 3
        assert lines[0] == "line 1"
        assert lines[2] == "line 3"


class TestFormatSecretWarning:
    """Tests for warning formatting."""

    def test_format_single_match(self):
        """Format warning for single match."""
        matches = [SecretMatch(
            type="api_key",
            pattern_name="openai_api_key",
            line_number=5,
            column=1,
            length=50,
            redacted_preview="sk-p****",
        )]
        warning = format_secret_warning(matches)
        assert "SECRETS DETECTED" in warning
        assert "Line 5" in warning
        assert "openai_api_key" in warning

    def test_format_with_file_path(self):
        """Format warning with file path."""
        matches = [SecretMatch(
            type="token",
            pattern_name="github_token",
            line_number=10,
            column=5,
            length=40,
            redacted_preview="ghp_****",
        )]
        warning = format_secret_warning(matches, file_path="config.py")
        assert "config.py" in warning
