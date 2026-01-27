"""
Tests for Roura Agent Build Tools.

© Roura.io
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from roura_agent.tools.build import (
    BuildRunTool,
    BuildErrorsTool,
    BuildCleanTool,
    detect_build_system,
    parse_rust_errors,
    parse_go_errors,
    parse_typescript_errors,
    parse_swift_errors,
    parse_python_errors,
    run_build,
)
from roura_agent.tools.base import RiskLevel


class TestDetectBuildSystem:
    """Tests for build system detection."""

    def test_detects_cargo(self, tmp_path):
        """Detect cargo from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        assert detect_build_system(str(tmp_path)) == "cargo"

    def test_detects_go(self, tmp_path):
        """Detect go from go.mod."""
        (tmp_path / "go.mod").write_text("module example.com/test")
        assert detect_build_system(str(tmp_path)) == "go"

    def test_detects_npm_with_build_script(self, tmp_path):
        """Detect npm from package.json with build script."""
        (tmp_path / "package.json").write_text(json.dumps({
            "scripts": {"build": "webpack"}
        }))
        assert detect_build_system(str(tmp_path)) == "npm"

    def test_detects_swift(self, tmp_path):
        """Detect swift from Package.swift."""
        (tmp_path / "Package.swift").write_text("// swift-tools-version:5.5")
        assert detect_build_system(str(tmp_path)) == "swift"

    def test_detects_gradle(self, tmp_path):
        """Detect gradle from build.gradle."""
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }")
        assert detect_build_system(str(tmp_path)) == "gradle"

    def test_detects_maven(self, tmp_path):
        """Detect maven from pom.xml."""
        (tmp_path / "pom.xml").write_text("<project></project>")
        assert detect_build_system(str(tmp_path)) == "maven"

    def test_detects_make(self, tmp_path):
        """Detect make from Makefile."""
        (tmp_path / "Makefile").write_text("all:\n\techo hello")
        assert detect_build_system(str(tmp_path)) == "make"

    def test_detects_cmake(self, tmp_path):
        """Detect cmake from CMakeLists.txt."""
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)")
        assert detect_build_system(str(tmp_path)) == "cmake"

    def test_returns_none_for_unknown(self, tmp_path):
        """Return None when no build system detected."""
        assert detect_build_system(str(tmp_path)) is None


class TestParseRustErrors:
    """Tests for Rust error parsing."""

    def test_parse_compile_error(self):
        """Parse Rust compile error."""
        output = """
error[E0308]: mismatched types
 --> src/main.rs:10:5
  |
10|     let x: i32 = "hello";
  |            ---   ^^^^^^^ expected `i32`, found `&str`
  |            |
  |            expected due to this

error: could not compile `myproject` due to previous error
"""
        errors, warnings = parse_rust_errors(output)
        assert len(errors) == 1
        assert errors[0].file_path == "src/main.rs"
        assert errors[0].line_number == 10
        assert errors[0].error_code == "E0308"

    def test_parse_warning(self):
        """Parse Rust warning."""
        output = """
warning: unused variable: `x`
 --> src/main.rs:5:9
  |
5 |     let x = 42;
  |         ^ help: if this is intentional, prefix it with an underscore: `_x`
"""
        errors, warnings = parse_rust_errors(output)
        assert len(warnings) == 1
        assert warnings[0].file_path == "src/main.rs"


class TestParseGoErrors:
    """Tests for Go error parsing."""

    def test_parse_compile_error(self):
        """Parse Go compile error."""
        output = """
./main.go:10:5: undefined: undefinedFunc
"""
        errors, warnings = parse_go_errors(output)
        assert len(errors) == 1
        assert errors[0].file_path == "main.go"
        assert errors[0].line_number == 10
        assert errors[0].column == 5


class TestParseTypescriptErrors:
    """Tests for TypeScript error parsing."""

    def test_parse_compile_error(self):
        """Parse TypeScript compile error."""
        output = """
src/index.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.
"""
        errors, warnings = parse_typescript_errors(output)
        assert len(errors) == 1
        assert errors[0].file_path == "src/index.ts"
        assert errors[0].line_number == 10
        assert errors[0].error_code == "TS2322"


class TestParseSwiftErrors:
    """Tests for Swift error parsing."""

    def test_parse_compile_error(self):
        """Parse Swift compile error."""
        output = """
/path/to/Sources/main.swift:10:5: error: cannot convert value of type 'Int' to expected argument type 'String'
"""
        errors, warnings = parse_swift_errors(output)
        assert len(errors) == 1
        assert errors[0].line_number == 10


class TestParsePythonErrors:
    """Tests for Python error parsing."""

    def test_parse_syntax_error(self):
        """Parse Python syntax error."""
        output = """
  File "main.py", line 10
    def foo(
          ^
SyntaxError: unexpected EOF while parsing
"""
        errors, warnings = parse_python_errors(output)
        assert len(errors) == 1
        assert errors[0].file_path == "main.py"
        assert errors[0].line_number == 10


class TestBuildRunTool:
    """Tests for the BuildRunTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = BuildRunTool()
        assert tool.name == "build.run"
        assert tool.risk_level == RiskLevel.SAFE
        assert not tool.requires_approval

    @patch('roura_agent.tools.build.subprocess.run')
    def test_execute_with_cargo(self, mock_run, tmp_path):
        """Test executing with cargo."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="   Compiling test v0.1.0\n    Finished dev target",
            stderr=""
        )

        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        with patch('roura_agent.tools.build.os.getcwd', return_value=str(tmp_path)):
            tool = BuildRunTool()
            result = tool.execute()

        assert result.success is True
        assert result.output["build_success"] is True
        assert result.output["build_system"] == "cargo"


class TestBuildErrorsTool:
    """Tests for the BuildErrorsTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = BuildErrorsTool()
        assert tool.name == "build.errors"
        assert tool.risk_level == RiskLevel.SAFE


class TestBuildCleanTool:
    """Tests for the BuildCleanTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = BuildCleanTool()
        assert tool.name == "build.clean"
        assert tool.risk_level == RiskLevel.MODERATE
        assert tool.requires_approval
