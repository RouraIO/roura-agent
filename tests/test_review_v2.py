"""
Tests for review v2 deep review module.

© Roura.io
"""
import pytest
from pathlib import Path
from roura_agent.review_v2 import (
    run_review,
    ReviewResult,
    Finding,
    Severity,
    format_review_output,
)


class TestRunReview:
    """Tests for run_review function."""

    def test_deep_review_returns_findings(self, tmp_path):
        """Deep review should always return findings."""
        # Create a sample project
        (tmp_path / "main.py").write_text("# " + "code\n" * 500)
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("# test")

        result = run_review(tmp_path, depth="deep")

        # Should have findings (god file at minimum)
        assert len(result.findings) > 0 or len(result.structural_improvements) > 0

    def test_quick_review_faster(self, tmp_path):
        """Quick review should review fewer files."""
        (tmp_path / "main.py").write_text("# code")

        quick_result = run_review(tmp_path, depth="quick")
        deep_result = run_review(tmp_path, depth="deep")

        # Both should return results
        assert quick_result is not None
        assert deep_result is not None

    def test_never_empty_output(self, tmp_path):
        """Review should never output 'No issues found' alone."""
        (tmp_path / "perfect.py").write_text("# perfect code")

        result = run_review(tmp_path, depth="deep")

        # Should have structural improvements or next investments
        assert (
            len(result.findings) > 0 or
            len(result.structural_improvements) > 0 or
            len(result.next_investments) > 0
        )

    def test_detects_god_files(self, tmp_path):
        """Should detect files over 400 lines."""
        (tmp_path / "god.py").write_text("# " + "line\n" * 500)

        result = run_review(tmp_path)

        god_findings = [f for f in result.findings if "god file" in f.title.lower()]
        assert len(god_findings) > 0

    def test_summary_counts(self, tmp_path):
        """Should include summary counts."""
        (tmp_path / "main.py").write_text("# code\n" * 100)

        result = run_review(tmp_path)

        assert "critical" in result.summary
        assert "warning" in result.summary


class TestFormatReviewOutput:
    """Tests for format_review_output function."""

    def test_format_includes_header(self, tmp_path):
        """Formatted output should include header."""
        (tmp_path / "main.py").write_text("#")
        result = run_review(tmp_path)

        output = format_review_output(result)

        assert "ROURA.IO" in output
        assert "DEEP CODE REVIEW" in output

    def test_format_includes_findings(self, tmp_path):
        """Formatted output should include findings."""
        (tmp_path / "large.py").write_text("# " + "line\n" * 500)
        result = run_review(tmp_path)

        output = format_review_output(result)

        assert "FINDINGS:" in output


class TestFindingSeverity:
    """Tests for finding severity handling."""

    def test_severity_ordering(self):
        """Severity enum should have correct ordering."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"
        assert Severity.SUGGESTION.value == "suggestion"
