"""
Roura Agent PRO Quotas - Usage limits and rate limiting.

Provides:
- Per-resource quotas
- Rate limiting
- Quota enforcement
- Usage warnings

© Roura.io
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from ..logging import get_logger

logger = get_logger(__name__)


class QuotaType(str, Enum):
    """Types of quotas."""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    REQUESTS_PER_HOUR = "requests_per_hour"
    REQUESTS_PER_DAY = "requests_per_day"
    REQUESTS_PER_MONTH = "requests_per_month"
    TOKENS_PER_MINUTE = "tokens_per_minute"
    TOKENS_PER_DAY = "tokens_per_day"
    TOKENS_PER_MONTH = "tokens_per_month"
    CONCURRENT_REQUESTS = "concurrent_requests"
    FILE_SIZE = "file_size"
    PROJECT_COUNT = "project_count"
    MEMORY_SIZE = "memory_size"


@dataclass
class Quota:
    """A quota definition."""
    quota_type: QuotaType
    limit: int
    current: int = 0
    reset_interval_seconds: Optional[int] = None
    last_reset: Optional[str] = None
    enabled: bool = True

    def is_exceeded(self) -> bool:
        """Check if quota is exceeded."""
        if not self.enabled:
            return False
        if self.limit == -1:  # Unlimited
            return False
        return self.current >= self.limit

    def remaining(self) -> int:
        """Get remaining quota."""
        if self.limit == -1:
            return -1  # Unlimited
        return max(0, self.limit - self.current)

    def percentage_used(self) -> float:
        """Get percentage of quota used."""
        if self.limit == -1 or self.limit == 0:
            return 0.0
        return (self.current / self.limit) * 100

    def should_reset(self) -> bool:
        """Check if quota should be reset."""
        if not self.reset_interval_seconds or not self.last_reset:
            return False

        last_reset_dt = datetime.fromisoformat(self.last_reset)
        now = datetime.now()
        elapsed = (now - last_reset_dt).total_seconds()
        return elapsed >= self.reset_interval_seconds

    def reset(self) -> None:
        """Reset the quota counter."""
        self.current = 0
        self.last_reset = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "quota_type": self.quota_type.value,
            "limit": self.limit,
            "current": self.current,
            "reset_interval_seconds": self.reset_interval_seconds,
            "last_reset": self.last_reset,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Quota":
        return cls(
            quota_type=QuotaType(data["quota_type"]),
            limit=data["limit"],
            current=data.get("current", 0),
            reset_interval_seconds=data.get("reset_interval_seconds"),
            last_reset=data.get("last_reset"),
            enabled=data.get("enabled", True),
        )


@dataclass
class QuotaViolation:
    """A quota violation event."""
    quota_type: QuotaType
    limit: int
    attempted: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "quota_type": self.quota_type.value,
            "limit": self.limit,
            "attempted": self.attempted,
            "timestamp": self.timestamp,
            "message": self.message,
        }


class RateLimiter:
    """
    Token bucket rate limiter.

    Provides smooth rate limiting with burst capability.
    """

    def __init__(
        self,
        rate: float,  # Tokens per second
        burst: int,  # Maximum burst size
    ):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.monotonic()

    def _update_tokens(self) -> None:
        """Update available tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_update = now

    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens.

        Returns True if tokens were acquired, False if rate limited.
        """
        self._update_tokens()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_time(self, tokens: int = 1) -> float:
        """Get time to wait before tokens will be available."""
        self._update_tokens()
        if self.tokens >= tokens:
            return 0.0
        needed = tokens - self.tokens
        return needed / self.rate


class QuotaManager:
    """
    Manages quotas and rate limits.

    Provides:
    - Quota tracking
    - Rate limiting
    - Violation logging
    - Auto-reset
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path or self._default_storage_path()
        self._quotas: dict[QuotaType, Quota] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}
        self._violations: list[QuotaViolation] = []
        self._load()
        self._init_default_quotas()

    @staticmethod
    def _default_storage_path() -> Path:
        path = Path.home() / ".config" / "roura-agent" / "quotas.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _init_default_quotas(self) -> None:
        """Initialize default quotas."""
        defaults = {
            QuotaType.REQUESTS_PER_MINUTE: Quota(
                quota_type=QuotaType.REQUESTS_PER_MINUTE,
                limit=60,
                reset_interval_seconds=60,
            ),
            QuotaType.REQUESTS_PER_HOUR: Quota(
                quota_type=QuotaType.REQUESTS_PER_HOUR,
                limit=500,
                reset_interval_seconds=3600,
            ),
            QuotaType.REQUESTS_PER_DAY: Quota(
                quota_type=QuotaType.REQUESTS_PER_DAY,
                limit=5000,
                reset_interval_seconds=86400,
            ),
            QuotaType.TOKENS_PER_MINUTE: Quota(
                quota_type=QuotaType.TOKENS_PER_MINUTE,
                limit=100000,
                reset_interval_seconds=60,
            ),
            QuotaType.CONCURRENT_REQUESTS: Quota(
                quota_type=QuotaType.CONCURRENT_REQUESTS,
                limit=5,
            ),
            QuotaType.FILE_SIZE: Quota(
                quota_type=QuotaType.FILE_SIZE,
                limit=10 * 1024 * 1024,  # 10MB
            ),
            QuotaType.PROJECT_COUNT: Quota(
                quota_type=QuotaType.PROJECT_COUNT,
                limit=20,
            ),
        }

        for qt, quota in defaults.items():
            if qt not in self._quotas:
                self._quotas[qt] = quota

    def _load(self) -> None:
        """Load quotas from storage."""
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text())
                self._quotas = {
                    QuotaType(k): Quota.from_dict(v)
                    for k, v in data.get("quotas", {}).items()
                }
                self._violations = [
                    QuotaViolation(**v) if isinstance(v, dict) else v
                    for v in data.get("violations", [])[-100:]
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load quotas: {e}")

    def _save(self) -> None:
        """Save quotas to storage."""
        data = {
            "quotas": {qt.value: q.to_dict() for qt, q in self._quotas.items()},
            "violations": [v.to_dict() for v in self._violations[-100:]],
        }
        self._storage_path.write_text(json.dumps(data, indent=2))

    def get_quota(self, quota_type: QuotaType) -> Optional[Quota]:
        """Get a quota by type."""
        return self._quotas.get(quota_type)

    def set_quota(self, quota: Quota) -> None:
        """Set or update a quota."""
        self._quotas[quota.quota_type] = quota
        self._save()

    def check(self, quota_type: QuotaType, amount: int = 1) -> bool:
        """
        Check if operation is within quota.

        Does not consume quota, just checks.
        """
        quota = self._quotas.get(quota_type)
        if not quota:
            return True  # No quota defined

        # Check for reset
        if quota.should_reset():
            quota.reset()
            self._save()

        return quota.current + amount <= quota.limit or quota.limit == -1

    def consume(
        self,
        quota_type: QuotaType,
        amount: int = 1,
        raise_on_violation: bool = False,
    ) -> bool:
        """
        Consume quota.

        Returns True if consumed, False if quota exceeded.
        """
        quota = self._quotas.get(quota_type)
        if not quota:
            return True

        # Check for reset
        if quota.should_reset():
            quota.reset()

        # Check limit
        if quota.is_exceeded() or (quota.current + amount > quota.limit and quota.limit != -1):
            violation = QuotaViolation(
                quota_type=quota_type,
                limit=quota.limit,
                attempted=amount,
                message=f"Quota exceeded: {quota_type.value}",
            )
            self._violations.append(violation)
            self._save()

            if raise_on_violation:
                raise QuotaExceededError(violation)
            return False

        quota.current += amount
        self._save()
        return True

    def release(self, quota_type: QuotaType, amount: int = 1) -> None:
        """Release consumed quota (for concurrent limits)."""
        quota = self._quotas.get(quota_type)
        if quota:
            quota.current = max(0, quota.current - amount)
            self._save()

    def get_rate_limiter(self, name: str, rate: float, burst: int) -> RateLimiter:
        """Get or create a rate limiter."""
        if name not in self._rate_limiters:
            self._rate_limiters[name] = RateLimiter(rate, burst)
        return self._rate_limiters[name]

    def rate_limit(
        self,
        name: str,
        tokens: int = 1,
        rate: float = 1.0,
        burst: int = 10,
    ) -> bool:
        """
        Apply rate limiting.

        Returns True if allowed, False if rate limited.
        """
        limiter = self.get_rate_limiter(name, rate, burst)
        return limiter.acquire(tokens)

    def get_summary(self) -> dict[str, dict]:
        """Get summary of all quotas."""
        summary = {}
        for qt, quota in self._quotas.items():
            if quota.should_reset():
                quota.reset()
            summary[qt.value] = {
                "limit": quota.limit,
                "current": quota.current,
                "remaining": quota.remaining(),
                "percentage_used": round(quota.percentage_used(), 1),
                "exceeded": quota.is_exceeded(),
            }
        return summary

    def get_violations(self, limit: int = 20) -> list[QuotaViolation]:
        """Get recent violations."""
        return self._violations[-limit:]

    def reset_all(self) -> None:
        """Reset all quotas."""
        for quota in self._quotas.values():
            quota.reset()
        self._save()

    def update_from_plan(self, plan_limits: dict[str, int]) -> None:
        """Update quotas based on billing plan limits."""
        if "requests_per_month" in plan_limits:
            self._quotas[QuotaType.REQUESTS_PER_MONTH] = Quota(
                quota_type=QuotaType.REQUESTS_PER_MONTH,
                limit=plan_limits["requests_per_month"],
                reset_interval_seconds=30 * 24 * 3600,
            )
        if "tokens_per_month" in plan_limits:
            self._quotas[QuotaType.TOKENS_PER_MONTH] = Quota(
                quota_type=QuotaType.TOKENS_PER_MONTH,
                limit=plan_limits["tokens_per_month"],
                reset_interval_seconds=30 * 24 * 3600,
            )
        if "projects" in plan_limits:
            self._quotas[QuotaType.PROJECT_COUNT] = Quota(
                quota_type=QuotaType.PROJECT_COUNT,
                limit=plan_limits["projects"],
            )
        self._save()


class QuotaExceededError(Exception):
    """Raised when quota is exceeded."""

    def __init__(self, violation: QuotaViolation):
        self.violation = violation
        super().__init__(violation.message)


# Global quota manager
_quota_manager: Optional[QuotaManager] = None


def get_quota_manager() -> QuotaManager:
    """Get the global quota manager."""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager


def check_quota(quota_type: QuotaType, amount: int = 1) -> bool:
    """Quick check if operation is within quota."""
    return get_quota_manager().check(quota_type, amount)


def consume_quota(quota_type: QuotaType, amount: int = 1) -> bool:
    """Consume quota for an operation."""
    return get_quota_manager().consume(quota_type, amount)
