"""
Tests for Hard Mode intent routing.

© Roura.io
"""
import pytest
from roura_agent.intent import (
    Intent,
    IntentDecision,
    classify_intent,
    HARD_MODE_TOKENS,
    get_intent_label,
)


class TestIntentClassification:
    """Tests for classify_intent function."""

    def test_how_is_my_code_triggers_exhaustive_review(self):
        """'how is my code' should trigger CODE_REVIEW_EXHAUSTIVE with hard mode."""
        result = classify_intent("how is my code")
        assert result.intent == Intent.CODE_REVIEW_EXHAUSTIVE
        assert result.hard_mode_triggered is True
        assert result.requires_repo is True
        assert "code" in result.matched_tokens

    def test_create_service_triggers_code_write(self):
        """'create firebase service layer' should trigger CODE_WRITE."""
        result = classify_intent("create firebase service layer")
        assert result.intent == Intent.CODE_WRITE
        assert result.hard_mode_triggered is True
        assert result.requires_execution_loop is True
        assert "firebase" in result.matched_tokens or "service" in result.matched_tokens

    def test_build_failing_triggers_diagnose(self):
        """'build failing with error' should trigger DIAGNOSE."""
        result = classify_intent("build failing with error in AuthService")
        assert result.intent == Intent.DIAGNOSE
        assert result.hard_mode_triggered is True
        assert result.requires_execution_loop is True

    def test_pure_chat_without_tokens(self):
        """A pure chat prompt without hard mode tokens should be CHAT."""
        result = classify_intent("hello there, nice to meet you")
        assert result.intent == Intent.CHAT
        assert result.hard_mode_triggered is False
        assert result.requires_repo is False

    def test_vague_prompt_with_code_token(self):
        """Vague prompt with 'code' token triggers exhaustive review."""
        result = classify_intent("thoughts on the code?")
        assert result.intent == Intent.CODE_REVIEW_EXHAUSTIVE
        assert result.hard_mode_triggered is True

    def test_error_crash_triggers_diagnose(self):
        """Error/crash keywords trigger DIAGNOSE."""
        result = classify_intent("the app keeps crashing on startup")
        assert result.intent == Intent.DIAGNOSE
        assert result.hard_mode_triggered is True

    def test_refactor_triggers_code_write(self):
        """'refactor' triggers CODE_WRITE."""
        result = classify_intent("refactor the authentication module")
        assert result.intent == Intent.CODE_WRITE
        assert result.hard_mode_triggered is True

    def test_swift_token_triggers_hard_mode(self):
        """'swift' token triggers hard mode."""
        result = classify_intent("check the swift files")
        assert result.hard_mode_triggered is True
        assert "swift" in result.matched_tokens

    def test_xcode_token_triggers_hard_mode(self):
        """'xcode' token triggers hard mode."""
        result = classify_intent("xcode build issues")
        assert result.hard_mode_triggered is True
        assert result.intent == Intent.DIAGNOSE  # "issues" triggers diagnose

    def test_architecture_triggers_review(self):
        """'architecture' triggers review."""
        result = classify_intent("review the architecture")
        assert result.intent == Intent.CODE_REVIEW_EXHAUSTIVE
        assert result.hard_mode_triggered is True

    def test_implement_triggers_code_write(self):
        """'implement' triggers CODE_WRITE."""
        result = classify_intent("implement the new auth flow")
        assert result.intent == Intent.CODE_WRITE

    def test_write_tests_triggers_code_write(self):
        """'write tests' triggers CODE_WRITE."""
        result = classify_intent("write tests for the UserService")
        assert result.intent == Intent.CODE_WRITE
        assert result.hard_mode_triggered is True

    def test_confidence_higher_with_multiple_matches(self):
        """Confidence should be higher with multiple trigger matches."""
        result = classify_intent("fix the error in the build that's failing")
        assert result.confidence >= 0.90  # Multiple diagnose triggers

    def test_requires_repo_for_code_intents(self):
        """CODE_WRITE, DIAGNOSE, REVIEW should require repo."""
        code_write = classify_intent("create a new service")
        diagnose = classify_intent("fix the error")
        review = classify_intent("review my code")

        assert code_write.requires_repo is True
        assert diagnose.requires_repo is True
        assert review.requires_repo is True

    def test_requires_execution_loop_for_write_and_diagnose(self):
        """CODE_WRITE and DIAGNOSE require execution loop."""
        code_write = classify_intent("implement feature")
        diagnose = classify_intent("fix the crash")
        review = classify_intent("review the code")

        assert code_write.requires_execution_loop is True
        assert diagnose.requires_execution_loop is True
        assert review.requires_execution_loop is False


class TestHardModeTokens:
    """Tests for HARD_MODE_TOKENS coverage."""

    def test_all_specified_tokens_exist(self):
        """Verify all specified tokens are in HARD_MODE_TOKENS."""
        required_tokens = [
            "code", "repo", "review", "improve", "architecture", "swift",
            "xcode", "auth", "service", "tests", "refactor", "bug", "error",
            "crash", "build", "compile", "lint", "ci", "workflow", "model",
            "view", "viewmodel", "screen", "firebase", "api", "networking",
            "concurrency", "actor", "mainactor", "performance", "memory",
            "leak", "ui", "ux", "beam", "feed", "cell",
        ]
        for token in required_tokens:
            assert token in HARD_MODE_TOKENS, f"Missing token: {token}"

    def test_hard_mode_tokens_lowercase(self):
        """All tokens should be lowercase."""
        for token in HARD_MODE_TOKENS:
            assert token == token.lower()


class TestIntentLabels:
    """Tests for intent label formatting."""

    def test_get_intent_label(self):
        """Test label generation for all intents."""
        assert get_intent_label(Intent.CHAT) == "MODE: CHAT"
        assert get_intent_label(Intent.CODE_WRITE) == "MODE: CODE_WRITE"
        assert get_intent_label(Intent.CODE_REVIEW_EXHAUSTIVE) == "MODE: REVIEW (Deep)"
        assert get_intent_label(Intent.DIAGNOSE) == "MODE: DIAGNOSE"


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_string(self):
        """Empty string should default to CHAT."""
        result = classify_intent("")
        assert result.intent == Intent.CHAT

    def test_whitespace_only(self):
        """Whitespace-only should default to CHAT."""
        result = classify_intent("   \n\t  ")
        assert result.intent == Intent.CHAT

    def test_case_insensitive(self):
        """Token matching should be case-insensitive."""
        result = classify_intent("CHECK THE CODE")
        assert result.hard_mode_triggered is True

    def test_mixed_case(self):
        """Mixed case should still trigger."""
        result = classify_intent("Review my Swift Code")
        assert result.hard_mode_triggered is True
        assert result.intent == Intent.CODE_REVIEW_EXHAUSTIVE
