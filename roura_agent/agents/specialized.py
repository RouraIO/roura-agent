"""
Roura Agent Specialized Agents - Domain-specific agents with tool execution.

Each agent has:
- Specific tool permissions (what tools it can use)
- A specialized system prompt
- Pattern matching for task routing

© Roura.io
"""
from __future__ import annotations

import re
from typing import Optional, Any

from rich.console import Console

from .base import (
    BaseAgent,
    AgentCapability,
    AgentContext,
    AgentResult,
)
from .executor import ToolPermissions


class CodeAgent(BaseAgent):
    """Agent specialized in writing and modifying code."""

    name = "code"
    description = "Writes, modifies, and refactors code"
    capabilities = [
        AgentCapability.CODE_WRITE,
        AgentCapability.CODE_READ,
        AgentCapability.FILE_SYSTEM,
    ]

    # Tools this agent can use
    allowed_tools = {
        'fs.read', 'fs.list', 'fs.write', 'fs.edit',
        'glob.find', 'grep.search',
    }

    PATTERNS = [
        r"write\s+(code|function|class|method)",
        r"implement\b",
        r"create\s+(a\s+)?(function|class|module|file)",
        r"add\s+(a\s+)?(feature|functionality|method)",
        r"refactor\b",
        r"modify\s+(the\s+)?code",
        r"edit\s+(the\s+)?file",
        r"update\s+(the\s+)?(code|function|class)",
    ]

    @property
    def system_prompt(self) -> str:
        return """You are a Code Agent specialized in writing and modifying code.

## Your Tools
You have access to these tools:
- fs.read: Read file contents
- fs.list: List directory contents
- fs.write: Create or overwrite files
- fs.edit: Edit files with search/replace
- glob.find: Find files by pattern
- grep.search: Search file contents

## How to Work
1. First, ALWAYS read existing files before modifying them
2. Understand the codebase structure using fs.list and glob.find
3. Write clean, well-structured code
4. Use fs.edit for small changes, fs.write for new files or major rewrites

## Rules
- ALWAYS read a file before editing it
- Use precise search/replace patterns in fs.edit
- Follow existing code style and conventions
- Add appropriate comments for complex logic
- Handle edge cases and errors appropriately

## When Done
Summarize what you did and any files created/modified."""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        # Check patterns
        matches = sum(1 for p in self.PATTERNS if re.search(p, task_lower))

        if matches > 0:
            confidence = min(0.9, 0.6 + (matches * 0.1))
            return True, confidence

        # Lower confidence for general tasks
        if any(word in task_lower for word in ["code", "function", "class", "file"]):
            return True, 0.4

        return False, 0.0


class TestAgent(BaseAgent):
    """Agent specialized in writing and running tests."""

    name = "test"
    description = "Writes and runs tests, checks coverage"
    capabilities = [
        AgentCapability.TEST_WRITE,
        AgentCapability.TEST_RUN,
        AgentCapability.CODE_READ,
        AgentCapability.SHELL,
    ]

    allowed_tools = {
        'fs.read', 'fs.list', 'fs.write', 'fs.edit',
        'shell.exec', 'glob.find', 'grep.search',
    }

    PATTERNS = [
        r"write\s+(a\s+)?test",
        r"add\s+(a\s+)?test",
        r"test\s+(the\s+|this\s+)?",
        r"unit\s+test",
        r"integration\s+test",
        r"coverage\b",
        r"pytest\b",
        r"unittest\b",
    ]

    @property
    def system_prompt(self) -> str:
        return """You are a Test Agent specialized in writing and running tests.

## Your Tools
- fs.read: Read source files to understand what to test
- fs.list: List project structure
- fs.write: Write test files
- fs.edit: Modify existing tests
- shell.exec: Run test commands (pytest, npm test, etc.)
- glob.find: Find test files and source files
- grep.search: Search for patterns in code

## How to Work
1. Read the source code to understand what needs testing
2. Check for existing test files with glob.find
3. Write comprehensive tests covering:
   - Happy path
   - Edge cases
   - Error conditions
4. Run tests with shell.exec to verify they pass
5. Check coverage if requested

## Test Writing Guidelines
- Use descriptive test names
- Follow AAA pattern: Arrange, Act, Assert
- One assertion per test when possible
- Use fixtures and setup/teardown appropriately
- Include docstrings explaining what each test verifies

## Running Tests
For Python: `pytest` or `python -m pytest`
For JavaScript: `npm test` or `jest`
For Go: `go test ./...`

Always run tests after writing them to verify they work."""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        matches = sum(1 for p in self.PATTERNS if re.search(p, task_lower))

        if matches > 0:
            confidence = min(0.9, 0.6 + (matches * 0.1))
            return True, confidence

        if "test" in task_lower:
            return True, 0.5

        return False, 0.0


class DebugAgent(BaseAgent):
    """Agent specialized in debugging and fixing issues."""

    name = "debug"
    description = "Debugs issues and fixes bugs"
    capabilities = [
        AgentCapability.DEBUG,
        AgentCapability.CODE_READ,
        AgentCapability.CODE_WRITE,
        AgentCapability.SHELL,
    ]

    allowed_tools = {
        'fs.read', 'fs.list', 'fs.edit',
        'shell.exec', 'glob.find', 'grep.search',
    }

    PATTERNS = [
        r"debug\b",
        r"fix\s+(the\s+|this\s+)?(bug|error|issue|problem)",
        r"troubleshoot\b",
        r"why\s+(is|does|isn't|doesn't)",
        r"not\s+working",
        r"broken\b",
        r"crash(ing|es)?\b",
        r"exception\b",
        r"error\s+message",
    ]

    @property
    def system_prompt(self) -> str:
        return """You are a Debug Agent specialized in finding and fixing bugs.

## Your Tools
- fs.read: Read source files and logs
- fs.list: Explore project structure
- fs.edit: Apply fixes to code
- shell.exec: Run commands to reproduce issues, check logs
- glob.find: Find relevant files
- grep.search: Search for error patterns, function calls, etc.

## Debugging Process
1. **Understand the problem**: Read error messages, stack traces, logs
2. **Reproduce**: Run commands to see the issue firsthand
3. **Locate**: Use grep.search to find relevant code
4. **Analyze**: Read the code to understand the logic
5. **Hypothesize**: Form theories about the cause
6. **Fix**: Apply the fix using fs.edit
7. **Verify**: Run the code again to confirm the fix

## Tips
- Search for the error message in the codebase
- Check recent changes (git log, git diff)
- Add logging/print statements if needed
- Consider edge cases and race conditions
- Look at similar code that works correctly

## When Stuck
- Look at test files for expected behavior
- Search documentation
- Check for common patterns (null checks, async/await, etc.)"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        matches = sum(1 for p in self.PATTERNS if re.search(p, task_lower))

        if matches > 0:
            confidence = min(0.95, 0.7 + (matches * 0.1))
            return True, confidence

        if any(word in task_lower for word in ["error", "bug", "fix", "broken"]):
            return True, 0.6

        return False, 0.0


class ResearchAgent(BaseAgent):
    """Agent specialized in research and information gathering."""

    name = "research"
    description = "Searches documentation and gathers information"
    capabilities = [
        AgentCapability.RESEARCH,
        AgentCapability.CODE_READ,
    ]

    allowed_tools = {
        'fs.read', 'fs.list',
        'glob.find', 'grep.search',
        'web.fetch', 'web.search',
    }

    PATTERNS = [
        r"search\s+(for|the)",
        r"find\s+(information|docs|documentation|examples)",
        r"look\s+up\b",
        r"what\s+is\b",
        r"how\s+(do|does|to)\b",
        r"explain\b",
        r"learn\s+about\b",
        r"documentation\b",
        r"api\s+(docs|reference)",
    ]

    @property
    def system_prompt(self) -> str:
        return """You are a Research Agent specialized in finding information.

## Your Tools
- fs.read: Read documentation files, READMEs, code comments
- fs.list: Explore project structure
- glob.find: Find relevant documentation
- grep.search: Search for patterns, examples, explanations
- web.fetch: Fetch web pages for documentation
- web.search: Search the web for information

## Research Process
1. Check local files first (README, docs/, comments)
2. Search the codebase for examples and usage
3. If needed, search the web for external documentation
4. Synthesize information into a clear summary

## Output Guidelines
- Provide clear, organized summaries
- Include code examples when relevant
- Cite sources (file paths, URLs)
- Highlight important caveats or gotchas
- Suggest related topics for further reading"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        matches = sum(1 for p in self.PATTERNS if re.search(p, task_lower))

        if matches > 0:
            confidence = min(0.9, 0.6 + (matches * 0.1))
            return True, confidence

        # Questions often need research
        if task.strip().endswith("?"):
            return True, 0.5

        return False, 0.0


class GitAgent(BaseAgent):
    """Agent specialized in Git operations."""

    name = "git"
    description = "Handles Git version control operations"
    capabilities = [
        AgentCapability.GIT,
        AgentCapability.SHELL,
    ]

    allowed_tools = {
        'fs.read', 'fs.list',
        'git.status', 'git.diff', 'git.log',
        'git.add', 'git.commit',
        'shell.exec',  # For other git commands
    }

    PATTERNS = [
        r"commit\b",
        r"push\b",
        r"pull\b",
        r"merge\b",
        r"branch\b",
        r"checkout\b",
        r"git\s+",
        r"version\s+control",
        r"rebase\b",
        r"stash\b",
    ]

    @property
    def system_prompt(self) -> str:
        return """You are a Git Agent specialized in version control operations.

## Your Tools
- fs.read: Read files to understand changes
- fs.list: See directory structure
- git.status: Check repository status
- git.diff: See uncommitted changes
- git.log: View commit history
- git.add: Stage files for commit
- git.commit: Create commits
- shell.exec: Run other git commands (push, pull, branch, etc.)

## Workflow
1. Always check git.status first to understand the current state
2. Use git.diff to review changes before committing
3. Write clear, descriptive commit messages
4. Follow conventional commit format when appropriate

## Commit Message Guidelines
- Start with a verb: Add, Fix, Update, Remove, Refactor
- Keep first line under 50 characters
- Add body for complex changes
- Reference issue numbers if applicable

## Safety Rules
- NEVER force push without explicit user request
- Always verify you're on the correct branch
- Check for uncommitted changes before switching branches
- Review changes before committing

## Common Commands (via shell.exec)
- `git branch`: List branches
- `git checkout -b <name>`: Create new branch
- `git push -u origin <branch>`: Push and set upstream
- `git pull`: Pull latest changes"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        matches = sum(1 for p in self.PATTERNS if re.search(p, task_lower))

        if matches > 0:
            confidence = min(0.95, 0.7 + (matches * 0.1))
            return True, confidence

        if "git" in task_lower:
            return True, 0.8

        return False, 0.0


class ReviewAgent(BaseAgent):
    """Agent specialized in code review."""

    name = "review"
    description = "Reviews code quality and suggests improvements"
    capabilities = [
        AgentCapability.CODE_REVIEW,
        AgentCapability.CODE_READ,
    ]

    allowed_tools = {
        'fs.read', 'fs.list',
        'glob.find', 'grep.search',
        'git.diff',  # Review changes
    }

    PATTERNS = [
        r"review\s+(the\s+|this\s+)?code",
        r"code\s+review",
        r"check\s+(the\s+)?quality",
        r"pr\s+review",
        r"pull\s+request\s+review",
        r"improve\s+(the\s+)?code",
        r"suggest(ions)?\s+for",
        r"best\s+practices",
    ]

    @property
    def system_prompt(self) -> str:
        return """You are a Code Review Agent specialized in reviewing code quality.

## Your Tools
- fs.read: Read code files to review
- fs.list: Understand project structure
- glob.find: Find related files
- grep.search: Search for patterns, duplicates, issues
- git.diff: Review specific changes

## Review Checklist
1. **Correctness**: Does the code do what it's supposed to?
2. **Edge Cases**: Are boundary conditions handled?
3. **Security**: Any vulnerabilities? (SQL injection, XSS, etc.)
4. **Performance**: Any obvious inefficiencies?
5. **Readability**: Is the code clear and well-organized?
6. **Naming**: Are variables/functions named descriptively?
7. **Documentation**: Are complex parts documented?
8. **Testing**: Is the code testable? Are tests needed?
9. **Error Handling**: Are errors handled gracefully?
10. **Style**: Does it follow project conventions?

## Output Format
For each issue found:
- **Location**: File and line number
- **Severity**: Critical / Warning / Suggestion
- **Issue**: Clear description of the problem
- **Recommendation**: How to fix it

## Tone
- Be constructive, not critical
- Explain the "why" behind suggestions
- Acknowledge good patterns you see
- Prioritize important issues over nitpicks"""

    def can_handle(
        self,
        task: str,
        context: Optional[AgentContext] = None,
    ) -> tuple[bool, float]:
        task_lower = task.lower()

        matches = sum(1 for p in self.PATTERNS if re.search(p, task_lower))

        if matches > 0:
            confidence = min(0.9, 0.6 + (matches * 0.1))
            return True, confidence

        if "review" in task_lower:
            return True, 0.6

        return False, 0.0
