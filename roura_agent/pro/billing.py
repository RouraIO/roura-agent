"""
Roura Agent PRO Billing - Usage tracking and billing management.

Provides:
- Usage-based billing tracking
- Plan management
- Invoice generation
- Payment status

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..logging import get_logger

logger = get_logger(__name__)


class BillingPlan(str, Enum):
    """Available billing plans."""
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class PlanLimits:
    """Limits for each billing plan."""
    requests_per_month: int
    tokens_per_month: int
    projects: int
    team_members: int
    priority_support: bool
    custom_models: bool
    api_access: bool
    ci_mode: bool


PLAN_LIMITS = {
    BillingPlan.FREE: PlanLimits(
        requests_per_month=100,
        tokens_per_month=100_000,
        projects=3,
        team_members=1,
        priority_support=False,
        custom_models=False,
        api_access=False,
        ci_mode=False,
    ),
    BillingPlan.PRO: PlanLimits(
        requests_per_month=5000,
        tokens_per_month=5_000_000,
        projects=20,
        team_members=1,
        priority_support=True,
        custom_models=True,
        api_access=True,
        ci_mode=True,
    ),
    BillingPlan.TEAM: PlanLimits(
        requests_per_month=25000,
        tokens_per_month=25_000_000,
        projects=100,
        team_members=10,
        priority_support=True,
        custom_models=True,
        api_access=True,
        ci_mode=True,
    ),
    BillingPlan.ENTERPRISE: PlanLimits(
        requests_per_month=-1,  # Unlimited
        tokens_per_month=-1,  # Unlimited
        projects=-1,  # Unlimited
        team_members=-1,  # Unlimited
        priority_support=True,
        custom_models=True,
        api_access=True,
        ci_mode=True,
    ),
}


class UsageType(str, Enum):
    """Types of usage to track."""
    REQUEST = "request"
    TOKEN_INPUT = "token_input"
    TOKEN_OUTPUT = "token_output"
    TOOL_CALL = "tool_call"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    CI_RUN = "ci_run"


@dataclass
class UsageRecord:
    """A single usage record."""
    usage_type: UsageType
    amount: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "usage_type": self.usage_type.value,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UsageRecord":
        return cls(
            usage_type=UsageType(data["usage_type"]),
            amount=data["amount"],
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BillingPeriod:
    """A billing period with usage summary."""
    start_date: str
    end_date: str
    plan: BillingPlan
    requests: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    tool_calls: int = 0
    ci_runs: int = 0
    amount_due: float = 0.0

    def to_dict(self) -> dict:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "plan": self.plan.value,
            "requests": self.requests,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tool_calls": self.tool_calls,
            "ci_runs": self.ci_runs,
            "amount_due": self.amount_due,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BillingPeriod":
        return cls(
            start_date=data["start_date"],
            end_date=data["end_date"],
            plan=BillingPlan(data["plan"]),
            requests=data.get("requests", 0),
            tokens_input=data.get("tokens_input", 0),
            tokens_output=data.get("tokens_output", 0),
            tool_calls=data.get("tool_calls", 0),
            ci_runs=data.get("ci_runs", 0),
            amount_due=data.get("amount_due", 0.0),
        )


class BillingManager:
    """
    Manages billing and usage tracking.

    Provides:
    - Usage recording
    - Plan limits checking
    - Usage summaries
    - Invoice generation
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path or self._default_storage_path()
        self._current_plan = BillingPlan.FREE
        self._usage_records: list[UsageRecord] = []
        self._billing_periods: list[BillingPeriod] = []
        self._api_key: Optional[str] = None
        self._load()

    @staticmethod
    def _default_storage_path() -> Path:
        path = Path.home() / ".config" / "roura-agent" / "billing.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self) -> None:
        """Load billing data from storage."""
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text())
                self._current_plan = BillingPlan(data.get("plan", "free"))
                self._usage_records = [
                    UsageRecord.from_dict(r)
                    for r in data.get("usage_records", [])
                ]
                self._billing_periods = [
                    BillingPeriod.from_dict(p)
                    for p in data.get("billing_periods", [])
                ]
                self._api_key = data.get("api_key")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load billing data: {e}")

    def _save(self) -> None:
        """Save billing data to storage."""
        # Keep only last 30 days of records
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        self._usage_records = [
            r for r in self._usage_records
            if r.timestamp >= cutoff
        ]

        data = {
            "plan": self._current_plan.value,
            "usage_records": [r.to_dict() for r in self._usage_records],
            "billing_periods": [p.to_dict() for p in self._billing_periods[-12:]],  # Keep 12 months
            "api_key": self._api_key,
        }
        self._storage_path.write_text(json.dumps(data, indent=2))

    @property
    def plan(self) -> BillingPlan:
        """Get current billing plan."""
        return self._current_plan

    @property
    def limits(self) -> PlanLimits:
        """Get limits for current plan."""
        return PLAN_LIMITS[self._current_plan]

    def set_plan(self, plan: BillingPlan, api_key: Optional[str] = None) -> None:
        """Set the billing plan."""
        self._current_plan = plan
        if api_key:
            self._api_key = api_key
        self._save()
        logger.info(f"Billing plan set to: {plan.value}")

    def record_usage(
        self,
        usage_type: UsageType,
        amount: int,
        metadata: Optional[dict] = None,
    ) -> UsageRecord:
        """Record usage."""
        record = UsageRecord(
            usage_type=usage_type,
            amount=amount,
            metadata=metadata or {},
        )
        self._usage_records.append(record)
        self._save()
        return record

    def get_usage_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Get usage summary for a period."""
        if not start_date:
            # Default to current month
            now = datetime.now()
            start_date = datetime(now.year, now.month, 1)
        if not end_date:
            end_date = datetime.now()

        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        summary = {
            "requests": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tool_calls": 0,
            "ci_runs": 0,
        }

        for record in self._usage_records:
            if start_str <= record.timestamp <= end_str:
                if record.usage_type == UsageType.REQUEST:
                    summary["requests"] += record.amount
                elif record.usage_type == UsageType.TOKEN_INPUT:
                    summary["tokens_input"] += record.amount
                elif record.usage_type == UsageType.TOKEN_OUTPUT:
                    summary["tokens_output"] += record.amount
                elif record.usage_type == UsageType.TOOL_CALL:
                    summary["tool_calls"] += record.amount
                elif record.usage_type == UsageType.CI_RUN:
                    summary["ci_runs"] += record.amount

        return summary

    def check_limit(self, usage_type: UsageType) -> bool:
        """Check if within limits for usage type."""
        limits = self.limits
        summary = self.get_usage_summary()

        if usage_type == UsageType.REQUEST:
            if limits.requests_per_month == -1:
                return True
            return summary["requests"] < limits.requests_per_month

        if usage_type in (UsageType.TOKEN_INPUT, UsageType.TOKEN_OUTPUT):
            if limits.tokens_per_month == -1:
                return True
            total_tokens = summary["tokens_input"] + summary["tokens_output"]
            return total_tokens < limits.tokens_per_month

        if usage_type == UsageType.CI_RUN:
            return limits.ci_mode

        return True

    def get_remaining(self, usage_type: UsageType) -> int:
        """Get remaining quota for usage type."""
        limits = self.limits
        summary = self.get_usage_summary()

        if usage_type == UsageType.REQUEST:
            if limits.requests_per_month == -1:
                return -1  # Unlimited
            return max(0, limits.requests_per_month - summary["requests"])

        if usage_type in (UsageType.TOKEN_INPUT, UsageType.TOKEN_OUTPUT):
            if limits.tokens_per_month == -1:
                return -1  # Unlimited
            total_tokens = summary["tokens_input"] + summary["tokens_output"]
            return max(0, limits.tokens_per_month - total_tokens)

        return -1

    def get_current_period(self) -> BillingPeriod:
        """Get or create current billing period."""
        now = datetime.now()
        start = datetime(now.year, now.month, 1)

        # Calculate end of month
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)

        start_str = start.isoformat()
        end_str = end.isoformat()

        # Find existing period
        for period in self._billing_periods:
            if period.start_date == start_str:
                return period

        # Create new period
        summary = self.get_usage_summary(start, end)
        period = BillingPeriod(
            start_date=start_str,
            end_date=end_str,
            plan=self._current_plan,
            requests=summary["requests"],
            tokens_input=summary["tokens_input"],
            tokens_output=summary["tokens_output"],
            tool_calls=summary["tool_calls"],
            ci_runs=summary["ci_runs"],
        )
        self._billing_periods.append(period)
        return period

    def is_pro(self) -> bool:
        """Check if user has a paid plan."""
        return self._current_plan in (BillingPlan.PRO, BillingPlan.TEAM, BillingPlan.ENTERPRISE)


# Global billing manager
_billing_manager: Optional[BillingManager] = None


def get_billing_manager() -> BillingManager:
    """Get the global billing manager."""
    global _billing_manager
    if _billing_manager is None:
        _billing_manager = BillingManager()
    return _billing_manager
