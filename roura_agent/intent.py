"""
Roura Agent Intent Classification - Hard Mode Routing.

Implements 5-type intent routing with Hard Mode auto-escalation.
When Hard Mode tokens are detected, routes to exhaustive workflows.

© Roura.io
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class Intent(Enum):
    """Intent types for routing user requests."""
    CHAT = "chat"
    CODE_WRITE = "code_write"
    CODE_REVIEW_QUICK = "code_review_quick"
    CODE_REVIEW_EXHAUSTIVE = "code_review_exhaustive"
    DIAGNOSE = "diagnose"
    RESEARCH = "research"


# Hard Mode tokens - any of these triggers CODE workflow (never pure CHAT)
HARD_MODE_TOKENS = frozenset([
    "code", "repo", "review", "improve", "architecture", "swift", "xcode",
    "auth", "service", "tests", "refactor", "bug", "error", "crash", "build",
    "compile", "lint", "ci", "workflow", "model", "view", "viewmodel", "screen",
    "firebase", "api", "networking", "concurrency", "actor", "mainactor",
    "performance", "memory", "leak", "ui", "ux", "beam", "feed", "cell",
    "python", "typescript", "javascript", "rust", "go", "kotlin", "java",
    "test", "pytest", "unittest", "jest", "debug", "fix", "implement",
    "create", "add", "update", "delete", "remove", "migrate", "deploy",
])

# Diagnose triggers - error/failure related
DIAGNOSE_TRIGGERS = frozenset([
    "error", "crash", "failing", "fails", "stack trace", "traceback",
    "exception", "build failed", "test failed", "compile", "broken",
    "not working", "doesn't work", "bug", "issue",
])

# Code write triggers - action verbs
CODE_WRITE_TRIGGERS = frozenset([
    "create", "implement", "wire", "add", "generate", "refactor", "write",
    "build", "make", "update", "migrate", "delete", "remove", "modify",
    "change", "fix", "develop", "design", "construct",
])

# Review triggers
REVIEW_TRIGGERS = frozenset([
    "review", "how is my code", "thoughts on", "quality", "improve",
    "architecture", "audit", "analyze", "assess", "evaluate", "check",
    "how are we doing", "what do you think",
])


@dataclass
class IntentDecision:
    """Result of intent classification."""
    intent: Intent
    confidence: float
    hard_mode_triggered: bool
    matched_tokens: list[str] = field(default_factory=list)
    rationale: str = ""
    requires_repo: bool = False
    requires_execution_loop: bool = False

    def __post_init__(self):
        # Auto-derive requires_repo and requires_execution_loop
        repo_intents = {
            Intent.CODE_WRITE,
            Intent.CODE_REVIEW_EXHAUSTIVE,
            Intent.CODE_REVIEW_QUICK,
            Intent.DIAGNOSE,
            Intent.RESEARCH,
        }
        exec_loop_intents = {Intent.CODE_WRITE, Intent.DIAGNOSE}

        self.requires_repo = self.intent in repo_intents
        self.requires_execution_loop = self.intent in exec_loop_intents


def classify_intent(user_text: str) -> IntentDecision:
    """
    Classify user intent with Hard Mode routing.

    Hard Mode is ALWAYS ON by default. When hard mode tokens are detected,
    routes to exhaustive/action workflows instead of simple chat.

    Args:
        user_text: The user's input message

    Returns:
        IntentDecision with classified intent and metadata
    """
    # Step 1: Normalize text
    text = user_text.lower().strip()
    text = re.sub(r'\s+', ' ', text)  # Collapse whitespace

    # Step 2: Check for hard mode tokens
    matched_tokens = []
    for token in HARD_MODE_TOKENS:
        if token in text:
            matched_tokens.append(token)

    hard_mode_triggered = len(matched_tokens) > 0

    # Step 3: Classify based on hard mode and specific triggers
    if hard_mode_triggered:
        # Check for DIAGNOSE triggers first (error/failure scenarios)
        diagnose_matches = [t for t in DIAGNOSE_TRIGGERS if t in text]
        if diagnose_matches:
            return IntentDecision(
                intent=Intent.DIAGNOSE,
                confidence=0.95 if len(diagnose_matches) > 1 else 0.85,
                hard_mode_triggered=True,
                matched_tokens=matched_tokens,
                rationale=f"Diagnose triggers detected: {diagnose_matches}",
            )

        # Check for CODE_WRITE triggers (action verbs)
        write_matches = [t for t in CODE_WRITE_TRIGGERS if t in text]
        if write_matches:
            return IntentDecision(
                intent=Intent.CODE_WRITE,
                confidence=0.95 if len(write_matches) > 1 else 0.85,
                hard_mode_triggered=True,
                matched_tokens=matched_tokens,
                rationale=f"Code write triggers detected: {write_matches}",
            )

        # Check for REVIEW triggers
        review_matches = [t for t in REVIEW_TRIGGERS if t in text]
        if review_matches:
            return IntentDecision(
                intent=Intent.CODE_REVIEW_EXHAUSTIVE,
                confidence=0.95 if len(review_matches) > 1 else 0.85,
                hard_mode_triggered=True,
                matched_tokens=matched_tokens,
                rationale=f"Review triggers detected: {review_matches}",
            )

        # Default for hard mode: CODE_REVIEW_EXHAUSTIVE (important per spec)
        return IntentDecision(
            intent=Intent.CODE_REVIEW_EXHAUSTIVE,
            confidence=0.80,
            hard_mode_triggered=True,
            matched_tokens=matched_tokens,
            rationale="Hard mode triggered, defaulting to exhaustive review",
        )

    # Not hard mode - check for light review patterns
    review_matches = [t for t in REVIEW_TRIGGERS if t in text]
    if review_matches:
        return IntentDecision(
            intent=Intent.CODE_REVIEW_QUICK,
            confidence=0.75,
            hard_mode_triggered=False,
            matched_tokens=[],
            rationale="Review keywords without hard mode tokens",
        )

    # Check if it's a question (research)
    if text.endswith("?") or text.startswith(("what", "how", "why", "where", "when", "who")):
        return IntentDecision(
            intent=Intent.RESEARCH,
            confidence=0.70,
            hard_mode_triggered=False,
            matched_tokens=[],
            rationale="Question pattern detected",
        )

    # Default: CHAT
    return IntentDecision(
        intent=Intent.CHAT,
        confidence=0.60,
        hard_mode_triggered=False,
        matched_tokens=[],
        rationale="No special patterns detected, defaulting to chat",
    )


def get_intent_label(intent: Intent) -> str:
    """Get human-readable label for intent."""
    labels = {
        Intent.CHAT: "MODE: CHAT",
        Intent.CODE_WRITE: "MODE: CODE_WRITE",
        Intent.CODE_REVIEW_QUICK: "MODE: REVIEW (Quick)",
        Intent.CODE_REVIEW_EXHAUSTIVE: "MODE: REVIEW (Deep)",
        Intent.DIAGNOSE: "MODE: DIAGNOSE",
        Intent.RESEARCH: "MODE: RESEARCH",
    }
    return labels.get(intent, "MODE: UNKNOWN")
