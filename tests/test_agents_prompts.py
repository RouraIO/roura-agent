"""
Tests for agent prompts module.

© Roura.io
"""
import pytest
from roura_agent.agents.prompts import (
    AgentPrompt,
    OutputFormat,
    REVIEW_ARCHITECT_PROMPT,
    CODING_AGENT_PROMPT,
    VERIFIER_AGENT_PROMPT,
    UNBLOCKER_AGENT_PROMPT,
    format_file_edits,
    parse_file_edits,
    format_unified_diff,
    get_agent_prompt,
    list_available_agents,
)


class TestAgentPrompts:
    """Tests for agent prompt definitions."""

    def test_review_architect_prompt_exists(self):
        """ReviewArchitect prompt should be defined."""
        assert REVIEW_ARCHITECT_PROMPT is not None
        assert REVIEW_ARCHITECT_PROMPT.name == "ReviewArchitect"
        assert REVIEW_ARCHITECT_PROMPT.output_format == OutputFormat.REVIEW

    def test_coding_agent_prompt_exists(self):
        """Coding agent prompt should be defined."""
        assert CODING_AGENT_PROMPT is not None
        assert CODING_AGENT_PROMPT.name == "Coding"
        assert CODING_AGENT_PROMPT.output_format == OutputFormat.FILE_EDITS

    def test_verifier_agent_prompt_exists(self):
        """Verifier agent prompt should be defined."""
        assert VERIFIER_AGENT_PROMPT is not None
        assert VERIFIER_AGENT_PROMPT.name == "Verifier"

    def test_unblocker_agent_prompt_exists(self):
        """Unblocker agent prompt should be defined."""
        assert UNBLOCKER_AGENT_PROMPT is not None
        assert UNBLOCKER_AGENT_PROMPT.name == "Unblocker"
        assert UNBLOCKER_AGENT_PROMPT.output_format == OutputFormat.PATCH

    def test_all_prompts_have_required_fields(self):
        """All prompts should have required contract fields."""
        prompts = [
            REVIEW_ARCHITECT_PROMPT,
            CODING_AGENT_PROMPT,
            VERIFIER_AGENT_PROMPT,
            UNBLOCKER_AGENT_PROMPT,
        ]

        for prompt in prompts:
            assert prompt.name, f"{prompt} missing name"
            assert prompt.role, f"{prompt} missing role"
            assert prompt.single_responsibility, f"{prompt} missing single_responsibility"
            assert prompt.inputs, f"{prompt} missing inputs"
            assert prompt.outputs, f"{prompt} missing outputs"
            assert prompt.stop_condition, f"{prompt} missing stop_condition"
            assert prompt.system_prompt, f"{prompt} missing system_prompt"

    def test_unblocker_invoked_automatically(self):
        """Unblocker prompt should mention automatic invocation."""
        prompt_text = UNBLOCKER_AGENT_PROMPT.system_prompt.lower()
        # Unblocker should handle repeated failures
        assert "failure" in prompt_text or "stall" in prompt_text


class TestFormatFileEdits:
    """Tests for format_file_edits function."""

    def test_formats_edits_as_json(self):
        """Should format edits as JSON."""
        edits = [
            {"path": "test.py", "action": "create", "content": "# test"}
        ]

        result = format_file_edits(edits)

        assert '"edits"' in result
        assert '"test.py"' in result
        assert '"create"' in result


class TestParseFileEdits:
    """Tests for parse_file_edits function."""

    def test_parses_json_block(self):
        """Should parse JSON code block."""
        response = '''Here are the changes:
```json
{
  "edits": [
    {"path": "test.py", "action": "create", "content": "# test"}
  ]
}
```
'''

        edits = parse_file_edits(response)

        assert len(edits) == 1
        assert edits[0]["path"] == "test.py"

    def test_parses_direct_json(self):
        """Should parse direct JSON."""
        response = '{"edits": [{"path": "test.py", "action": "modify", "content": "# new"}]}'

        edits = parse_file_edits(response)

        assert len(edits) == 1
        assert edits[0]["action"] == "modify"

    def test_returns_empty_on_invalid(self):
        """Should return empty list for invalid input."""
        edits = parse_file_edits("This is just text")

        assert edits == []


class TestFormatUnifiedDiff:
    """Tests for format_unified_diff function."""

    def test_generates_diff(self):
        """Should generate unified diff."""
        old = "line1\nline2\nline3"
        new = "line1\nmodified\nline3"

        diff = format_unified_diff(old, new, "test.py")

        assert "--- a/test.py" in diff
        assert "+++ b/test.py" in diff
        assert "-line2" in diff
        assert "+modified" in diff


class TestGetAgentPrompt:
    """Tests for get_agent_prompt function."""

    def test_gets_prompt_by_name(self):
        """Should get prompt by name."""
        prompt = get_agent_prompt("review")
        assert prompt == REVIEW_ARCHITECT_PROMPT

        prompt = get_agent_prompt("coding")
        assert prompt == CODING_AGENT_PROMPT

    def test_case_insensitive(self):
        """Should be case insensitive."""
        prompt = get_agent_prompt("CODING")
        assert prompt == CODING_AGENT_PROMPT

    def test_returns_none_for_unknown(self):
        """Should return None for unknown agent."""
        prompt = get_agent_prompt("unknown_agent")
        assert prompt is None


class TestListAvailableAgents:
    """Tests for list_available_agents function."""

    def test_lists_agents(self):
        """Should list all available agents."""
        agents = list_available_agents()

        assert "ReviewArchitect" in agents
        assert "Coding" in agents
        assert "Verifier" in agents
        assert "Unblocker" in agents
