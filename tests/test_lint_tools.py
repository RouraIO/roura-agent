"""
Tests for Roura Agent Lint & Format Tools.

© Roura.io
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from roura_agent.tools.lint import (
    LintRunTool,
    LintFixTool,
    FormatRunTool,
    FormatCheckTool,
    TypecheckRunTool,
    detect_linter,
    detect_formatter,
    detect_typechecker,
    parse_ruff_output,
    parse_eslint_output,
    parse_clippy_output,
    parse_golangci_output,
    run_lint,
)
from roura_agent.tools.base import RiskLevel


class TestDetectLinter:
    """Tests for linter detection."""

    def test_detects_ruff(self, tmp_path):
        """Detect ruff from pyproject.toml with ruff config."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 88")
        assert detect_linter(str(tmp_path)) == "ruff"

    def test_detects_eslint(self, tmp_path):
        """Detect eslint from .eslintrc."""
        (tmp_path / ".eslintrc").write_text('{"rules": {}}')
        assert detect_linter(str(tmp_path)) == "eslint"

    def test_detects_clippy_from_cargo(self, tmp_path):
        """Detect clippy from Cargo.toml (fallback)."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        assert detect_linter(str(tmp_path)) == "clippy"

    def test_detects_golangci_from_go_mod(self, tmp_path):
        """Detect golangci-lint from go.mod (fallback)."""
        (tmp_path / "go.mod").write_text("module example.com/test")
        assert detect_linter(str(tmp_path)) == "golangci-lint"

    def test_detects_swiftlint(self, tmp_path):
        """Detect swiftlint from .swiftlint.yml."""
        (tmp_path / ".swiftlint.yml").write_text("disabled_rules: []")
        assert detect_linter(str(tmp_path)) == "swiftlint"

    def test_fallback_to_ruff_for_python(self, tmp_path):
        """Fallback to ruff for Python files."""
        (tmp_path / "main.py").write_text("print('hello')")
        assert detect_linter(str(tmp_path)) == "ruff"

    def test_returns_none_for_unknown(self, tmp_path):
        """Return None when no linter detected."""
        assert detect_linter(str(tmp_path)) is None


class TestDetectFormatter:
    """Tests for formatter detection."""

    def test_detects_prettier(self, tmp_path):
        """Detect prettier from .prettierrc."""
        (tmp_path / ".prettierrc").write_text('{"semi": false}')
        assert detect_formatter(str(tmp_path)) == "prettier"

    def test_detects_black(self, tmp_path):
        """Detect black from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 88")
        assert detect_formatter(str(tmp_path)) == "black"

    def test_detects_ruff_format(self, tmp_path):
        """Detect ruff format from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff.format]\nquote-style = 'double'")
        assert detect_formatter(str(tmp_path)) == "ruff"

    def test_detects_rustfmt(self, tmp_path):
        """Detect rustfmt from Cargo.toml (fallback)."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        assert detect_formatter(str(tmp_path)) == "rustfmt"

    def test_detects_gofmt(self, tmp_path):
        """Detect gofmt from go.mod (fallback)."""
        (tmp_path / "go.mod").write_text("module example.com/test")
        assert detect_formatter(str(tmp_path)) == "gofmt"


class TestDetectTypechecker:
    """Tests for type checker detection."""

    def test_detects_tsc(self, tmp_path):
        """Detect tsc from tsconfig.json."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        assert detect_typechecker(str(tmp_path)) == "tsc"

    def test_detects_mypy(self, tmp_path):
        """Detect mypy from mypy.ini."""
        (tmp_path / "mypy.ini").write_text("[mypy]")
        assert detect_typechecker(str(tmp_path)) == "mypy"

    def test_detects_pyright(self, tmp_path):
        """Detect pyright from pyrightconfig.json."""
        (tmp_path / "pyrightconfig.json").write_text("{}")
        assert detect_typechecker(str(tmp_path)) == "pyright"


class TestParseRuffOutput:
    """Tests for ruff output parsing."""

    def test_parse_lint_error(self):
        """Parse ruff lint error."""
        output = """
src/main.py:10:5: E501 Line too long (120 > 88)
src/main.py:15:1: F401 'os' imported but unused
"""
        issues = parse_ruff_output(output)
        assert len(issues) == 2
        assert issues[0].file_path == "src/main.py"
        assert issues[0].line_number == 10
        assert issues[0].rule == "E501"
        assert issues[1].rule == "F401"


class TestParseEslintOutput:
    """Tests for ESLint output parsing."""

    def test_parse_lint_issues(self):
        """Parse ESLint issues."""
        output = """
/path/to/src/index.js
  10:5  error    Unexpected console statement  no-console
  15:1  warning  Missing semicolon             semi
"""
        issues = parse_eslint_output(output)
        assert len(issues) == 2
        assert issues[0].line_number == 10
        assert issues[0].severity == "error"
        assert issues[1].severity == "warning"


class TestParseClippyOutput:
    """Tests for Clippy output parsing."""

    def test_parse_warning(self):
        """Parse Clippy warning."""
        # Clippy output format: warning[code]: message followed by --> file:line:col
        output = """warning[needless_return]: unneeded `return` statement
   --> src/main.rs:10:5
    |
10  |     return x;
    |     ^^^^^^^^^ help: remove `return`: `x`
"""
        issues = parse_clippy_output(output)
        assert len(issues) == 1
        assert issues[0].file_path == "src/main.rs"
        assert issues[0].rule == "needless_return"


class TestParseGolangciOutput:
    """Tests for golangci-lint output parsing."""

    def test_parse_lint_issue(self):
        """Parse golangci-lint issue."""
        output = """
main.go:10:5: S1000: should use a simple channel send/receive instead of select (gosimple)
"""
        issues = parse_golangci_output(output)
        assert len(issues) == 1
        assert issues[0].file_path == "main.go"
        assert issues[0].line_number == 10
        assert issues[0].rule == "gosimple"


class TestLintRunTool:
    """Tests for the LintRunTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = LintRunTool()
        assert tool.name == "lint.run"
        assert tool.risk_level == RiskLevel.SAFE
        assert not tool.requires_approval

    @patch('roura_agent.tools.lint.subprocess.run')
    def test_execute_with_ruff(self, mock_run, tmp_path):
        """Test executing with ruff."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="All checks passed!",
            stderr=""
        )

        (tmp_path / "pyproject.toml").write_text("[tool.ruff]")

        with patch('roura_agent.tools.lint.os.getcwd', return_value=str(tmp_path)):
            tool = LintRunTool()
            result = tool.execute()

        assert result.success is True
        assert result.output["linter"] == "ruff"


class TestLintFixTool:
    """Tests for the LintFixTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = LintFixTool()
        assert tool.name == "lint.fix"
        assert tool.risk_level == RiskLevel.MODERATE
        assert tool.requires_approval


class TestFormatRunTool:
    """Tests for the FormatRunTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = FormatRunTool()
        assert tool.name == "format.run"
        assert tool.risk_level == RiskLevel.MODERATE
        assert tool.requires_approval


class TestFormatCheckTool:
    """Tests for the FormatCheckTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = FormatCheckTool()
        assert tool.name == "format.check"
        assert tool.risk_level == RiskLevel.SAFE
        assert not tool.requires_approval


class TestTypecheckRunTool:
    """Tests for the TypecheckRunTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = TypecheckRunTool()
        assert tool.name == "typecheck.run"
        assert tool.risk_level == RiskLevel.SAFE
        assert not tool.requires_approval
