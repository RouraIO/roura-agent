"""
Tests for Roura Agent Testing Tools.

© Roura.io
"""
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from roura_agent.tools.testing import (
    TestRunTool,
    TestFailuresTool,
    TestLastTool,
    TestCoverageTool,
    detect_test_framework,
    parse_pytest_output,
    parse_cargo_output,
    parse_go_output,
    parse_jest_output,
    run_tests,
)
from roura_agent.tools.base import RiskLevel


class TestDetectTestFramework:
    """Tests for test framework detection."""

    def test_detects_pytest_from_conftest(self, tmp_path):
        """Detect pytest from conftest.py."""
        (tmp_path / "conftest.py").write_text("# pytest config")
        assert detect_test_framework(str(tmp_path)) == "pytest"

    def test_detects_pytest_from_pyproject(self, tmp_path):
        """Detect pytest from pyproject.toml with pytest config."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")
        assert detect_test_framework(str(tmp_path)) == "pytest"

    def test_detects_cargo_from_cargo_toml(self, tmp_path):
        """Detect cargo from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        assert detect_test_framework(str(tmp_path)) == "cargo"

    def test_detects_go_from_go_mod(self, tmp_path):
        """Detect go from go.mod."""
        (tmp_path / "go.mod").write_text("module example.com/test")
        assert detect_test_framework(str(tmp_path)) == "go"

    def test_detects_jest_from_package_json(self, tmp_path):
        """Detect jest from package.json with jest test script."""
        (tmp_path / "package.json").write_text(json.dumps({
            "scripts": {"test": "jest"}
        }))
        assert detect_test_framework(str(tmp_path)) == "jest"

    def test_detects_vitest_from_package_json(self, tmp_path):
        """Detect vitest from package.json with vitest test script."""
        (tmp_path / "package.json").write_text(json.dumps({
            "scripts": {"test": "vitest run"}
        }))
        assert detect_test_framework(str(tmp_path)) == "vitest"

    def test_returns_none_for_unknown(self, tmp_path):
        """Return None when no framework detected."""
        assert detect_test_framework(str(tmp_path)) is None


class TestParsePytestOutput:
    """Tests for pytest output parsing."""

    def test_parse_passing_tests(self):
        """Parse pytest output with passing tests."""
        output = """
============================= test session starts ==============================
collected 5 items

tests/test_example.py::test_one PASSED
tests/test_example.py::test_two PASSED

============================== 5 passed in 0.12s ===============================
"""
        result = parse_pytest_output(output)
        assert result.passed == 5
        assert result.failed == 0
        assert result.success is True

    def test_parse_failing_tests(self):
        """Parse pytest output with failing tests."""
        output = """
============================= test session starts ==============================
collected 3 items

tests/test_example.py::test_one PASSED
tests/test_example.py::test_two FAILED

=================================== FAILURES ===================================
_____________________________ test_two _____________________________________

    def test_two():
>       assert 1 == 2
E       AssertionError

tests/test_example.py:10: AssertionError
=========================== short test summary info ============================
FAILED tests/test_example.py::test_two - AssertionError
============================== 1 passed, 1 failed in 0.08s =====================
"""
        result = parse_pytest_output(output)
        assert result.passed == 1
        assert result.failed == 1
        assert result.success is False

    def test_parse_with_errors(self):
        """Parse pytest output with collection errors."""
        output = """
============================= test session starts ==============================
collected 0 items / 1 error

=================================== ERRORS =====================================
________________________ ERROR collecting tests/test_bad.py ____________________
ImportError: No module named 'missing_module'
============================== 0 passed, 0 failed, 1 error in 0.05s ============
"""
        result = parse_pytest_output(output)
        assert result.errors == 1


class TestParseCargoOutput:
    """Tests for cargo test output parsing."""

    def test_parse_passing_tests(self):
        """Parse cargo test output with passing tests."""
        output = """
running 3 tests
test tests::test_one ... ok
test tests::test_two ... ok
test tests::test_three ... ok

test result: ok. 3 passed; 0 failed; 0 ignored
"""
        result = parse_cargo_output(output)
        assert result.passed == 3
        assert result.failed == 0
        assert result.success is True

    def test_parse_failing_tests(self):
        """Parse cargo test output with failing tests."""
        output = """
running 2 tests
test tests::test_one ... ok
test tests::test_two ... FAILED

failures:

---- tests::test_two stdout ----
thread 'tests::test_two' panicked at 'assertion failed: false'

failures:
    tests::test_two

test result: FAILED. 1 passed; 1 failed; 0 ignored
"""
        result = parse_cargo_output(output)
        assert result.passed == 1
        assert result.failed == 1
        assert result.success is False
        assert len(result.failures) >= 1


class TestParseGoOutput:
    """Tests for go test output parsing."""

    def test_parse_passing_tests(self):
        """Parse go test output with passing tests."""
        output = """
=== RUN   TestOne
--- PASS: TestOne (0.00s)
=== RUN   TestTwo
--- PASS: TestTwo (0.01s)
PASS
ok      example.com/pkg    0.02s
"""
        result = parse_go_output(output)
        assert result.passed == 2
        assert result.failed == 0
        assert result.success is True

    def test_parse_failing_tests(self):
        """Parse go test output with failing tests."""
        output = """
=== RUN   TestOne
--- PASS: TestOne (0.00s)
=== RUN   TestTwo
    main_test.go:15: Error: expected 1, got 2
--- FAIL: TestTwo (0.01s)
FAIL
exit status 1
FAIL    example.com/pkg    0.02s
"""
        result = parse_go_output(output)
        assert result.passed == 1
        assert result.failed == 1
        assert result.success is False


class TestParseJestOutput:
    """Tests for jest output parsing."""

    def test_parse_passing_tests(self):
        """Parse jest output with passing tests."""
        output = """
 PASS  tests/example.test.js
  ✓ test one (5 ms)
  ✓ test two (2 ms)

Test Suites: 1 passed, 1 total
Tests:       2 passed, 2 total
"""
        result = parse_jest_output(output)
        assert result.passed == 2
        assert result.success is True

    def test_parse_failing_tests(self):
        """Parse jest output with failing tests."""
        output = """
 FAIL  tests/example.test.js
  ✓ test one (5 ms)
  ✕ test two (3 ms)

  ● test two

    expect(received).toBe(expected)

    Expected: 2
    Received: 1

      at Object.test (tests/example.test.js:10:17)

Test Suites: 1 failed, 1 total
Tests:       1 failed, 1 passed, 2 total
"""
        result = parse_jest_output(output)
        assert result.passed == 1
        assert result.failed == 1
        assert result.success is False


class TestTestRunTool:
    """Tests for the TestRunTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = TestRunTool()
        assert tool.name == "test.run"
        assert tool.risk_level == RiskLevel.SAFE
        assert not tool.requires_approval

    @patch('roura_agent.tools.testing.subprocess.run')
    def test_execute_with_pytest(self, mock_run, tmp_path):
        """Test executing with pytest."""
        # Setup mock
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="============================== 2 passed in 0.10s ==============================",
            stderr=""
        )

        # Create pytest marker
        (tmp_path / "conftest.py").write_text("")

        with patch('roura_agent.tools.testing.os.getcwd', return_value=str(tmp_path)):
            tool = TestRunTool()
            result = tool.execute()

        assert result.success is True
        assert result.output["framework"] == "pytest"


class TestTestFailuresTool:
    """Tests for the TestFailuresTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = TestFailuresTool()
        assert tool.name == "test.failures"
        assert tool.risk_level == RiskLevel.SAFE


class TestTestLastTool:
    """Tests for the TestLastTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = TestLastTool()
        assert tool.name == "test.last"
        assert tool.risk_level == RiskLevel.SAFE


class TestTestCoverageTool:
    """Tests for the TestCoverageTool."""

    def test_tool_properties(self):
        """Verify tool properties."""
        tool = TestCoverageTool()
        assert tool.name == "test.coverage"
        assert tool.risk_level == RiskLevel.SAFE
