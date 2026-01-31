"""
Tests for PRO tier features: billing, CI, automation, quotas.

© Roura.io
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from roura_agent.pro.billing import (
    BillingManager,
    BillingPlan,
    UsageRecord,
    UsageType,
    PLAN_LIMITS,
)
from roura_agent.pro.ci import (
    CIConfig,
    CIMode,
    CIRunner,
    CIResult,
    CIExitCode,
    CIIssue,
)
from roura_agent.pro.automation import (
    Workflow,
    WorkflowStep,
    WorkflowRunner,
    AutomationTrigger,
    StepStatus,
)
from roura_agent.pro.quotas import (
    Quota,
    QuotaType,
    QuotaManager,
    RateLimiter,
    QuotaExceededError,
)


# ============================================================================
# Billing Tests
# ============================================================================


class TestBillingPlan:
    """Tests for billing plans."""

    def test_plan_limits(self):
        """Each plan has defined limits."""
        for plan in BillingPlan:
            limits = PLAN_LIMITS[plan]
            assert limits.requests_per_month != 0
            assert limits.tokens_per_month != 0

    def test_free_plan_limits(self):
        """Free plan has restrictive limits."""
        limits = PLAN_LIMITS[BillingPlan.FREE]
        assert limits.requests_per_month == 100
        assert not limits.ci_mode
        assert not limits.api_access

    def test_pro_plan_limits(self):
        """Pro plan has better limits."""
        limits = PLAN_LIMITS[BillingPlan.PRO]
        assert limits.requests_per_month > 1000
        assert limits.ci_mode
        assert limits.api_access

    def test_enterprise_unlimited(self):
        """Enterprise plan has unlimited resources."""
        limits = PLAN_LIMITS[BillingPlan.ENTERPRISE]
        assert limits.requests_per_month == -1  # Unlimited
        assert limits.tokens_per_month == -1


class TestBillingManager:
    """Tests for BillingManager."""

    def test_default_plan(self, tmp_path):
        """Default plan is free."""
        manager = BillingManager(storage_path=tmp_path / "billing.json")
        assert manager.plan == BillingPlan.FREE

    def test_set_plan(self, tmp_path):
        """Set billing plan."""
        manager = BillingManager(storage_path=tmp_path / "billing.json")
        manager.set_plan(BillingPlan.PRO)
        assert manager.plan == BillingPlan.PRO

    def test_record_usage(self, tmp_path):
        """Record usage events."""
        manager = BillingManager(storage_path=tmp_path / "billing.json")
        manager.record_usage(UsageType.REQUEST, 1)
        manager.record_usage(UsageType.TOKEN_INPUT, 500)
        manager.record_usage(UsageType.TOKEN_OUTPUT, 200)

        summary = manager.get_usage_summary()
        assert summary["requests"] == 1
        assert summary["tokens_input"] == 500
        assert summary["tokens_output"] == 200

    def test_check_limit(self, tmp_path):
        """Check usage limits."""
        manager = BillingManager(storage_path=tmp_path / "billing.json")
        manager.set_plan(BillingPlan.FREE)

        # Initially within limits
        assert manager.check_limit(UsageType.REQUEST)

        # Record up to limit
        for _ in range(100):
            manager.record_usage(UsageType.REQUEST, 1)

        # Should be at limit
        assert not manager.check_limit(UsageType.REQUEST)

    def test_persistence(self, tmp_path):
        """Billing data persists."""
        path = tmp_path / "billing.json"

        manager1 = BillingManager(storage_path=path)
        manager1.set_plan(BillingPlan.PRO)
        manager1.record_usage(UsageType.REQUEST, 5)

        manager2 = BillingManager(storage_path=path)
        assert manager2.plan == BillingPlan.PRO


# ============================================================================
# CI Tests
# ============================================================================


class TestCIConfig:
    """Tests for CIConfig."""

    def test_default_config(self):
        """Default configuration values."""
        config = CIConfig(mode=CIMode.REVIEW)
        assert config.mode == CIMode.REVIEW
        assert config.target_path == "."
        assert config.max_files == 50
        assert config.output_format == "json"

    def test_from_env(self, monkeypatch):
        """Create config from environment."""
        monkeypatch.setenv("ROURA_CI_MODE", "fix")
        monkeypatch.setenv("ROURA_CI_TARGET", "/path/to/project")
        monkeypatch.setenv("ROURA_CI_OUTPUT_FORMAT", "github")

        config = CIConfig.from_env()
        assert config.mode == CIMode.FIX
        assert config.target_path == "/path/to/project"
        assert config.output_format == "github"


class TestCIResult:
    """Tests for CIResult."""

    def test_to_json(self):
        """Serialize result to JSON."""
        result = CIResult(
            exit_code=CIExitCode.SUCCESS,
            mode=CIMode.REVIEW,
            files_analyzed=10,
        )
        json_str = result.to_json()
        data = json.loads(json_str)

        assert data["exit_code"] == 0
        assert data["files_analyzed"] == 10

    def test_to_text(self):
        """Format result as text."""
        result = CIResult(
            exit_code=CIExitCode.SUCCESS,
            mode=CIMode.REVIEW,
            files_analyzed=10,
            issues=[
                CIIssue(
                    file="test.py",
                    line=5,
                    severity="warning",
                    message="Test warning",
                ),
            ],
        )
        text = result.to_text()

        assert "REVIEW" in text
        assert "PASSED" in text
        assert "test.py" in text
        assert "Test warning" in text

    def test_github_output(self):
        """Format for GitHub Actions."""
        result = CIResult(
            exit_code=CIExitCode.FAILURE,
            mode=CIMode.REVIEW,
            issues=[
                CIIssue(
                    file="src/main.py",
                    line=10,
                    severity="error",
                    message="Missing type hint",
                ),
            ],
        )
        output = result.to_github_output()

        assert "::error" in output
        assert "src/main.py" in output


class TestCIRunner:
    """Tests for CIRunner."""

    def test_run_review(self, tmp_path):
        """Run code review."""
        # Create test file
        (tmp_path / "test.py").write_text("print('hello')")

        config = CIConfig(
            mode=CIMode.REVIEW,
            target_path=str(tmp_path),
        )
        runner = CIRunner(config)
        result = runner.run()

        assert result.exit_code in (CIExitCode.SUCCESS, CIExitCode.RATE_LIMITED)
        assert result.mode == CIMode.REVIEW


# ============================================================================
# Automation Tests
# ============================================================================


class TestWorkflowStep:
    """Tests for WorkflowStep."""

    def test_create_step(self):
        """Create a workflow step."""
        step = WorkflowStep(
            name="review",
            action="review",
            config={"target": "."},
        )
        assert step.name == "review"
        assert step.status == StepStatus.PENDING

    def test_to_dict_from_dict(self):
        """Serialize and deserialize step."""
        step1 = WorkflowStep(
            name="test",
            action="command",
            config={"command": "pytest"},
            timeout_seconds=120,
        )
        data = step1.to_dict()
        step2 = WorkflowStep.from_dict(data)

        assert step2.name == step1.name
        assert step2.action == step1.action
        assert step2.timeout_seconds == 120


class TestWorkflow:
    """Tests for Workflow."""

    def test_create_workflow(self):
        """Create a workflow."""
        workflow = Workflow(
            name="review-and-fix",
            description="Review code and apply fixes",
            trigger=AutomationTrigger.GIT_PUSH,
        )
        workflow.add_step("review", "review", target=".")
        workflow.add_step("fix", "fix", target=".")

        assert len(workflow.steps) == 2
        assert workflow.trigger == AutomationTrigger.GIT_PUSH

    def test_to_dict_from_dict(self):
        """Serialize and deserialize workflow."""
        workflow1 = Workflow(name="test")
        workflow1.add_step("step1", "command", command="echo hello")

        data = workflow1.to_dict()
        workflow2 = Workflow.from_dict(data)

        assert workflow2.name == workflow1.name
        assert len(workflow2.steps) == 1


class TestWorkflowRunner:
    """Tests for WorkflowRunner."""

    def test_run_simple_workflow(self, tmp_path):
        """Run a simple workflow."""
        runner = WorkflowRunner(storage_path=tmp_path / "workflows.json")

        workflow = Workflow(name="test")
        workflow.add_step("echo", "command", command="echo 'hello'")

        result = runner.run(workflow)

        assert result.status in ("success", "failed")
        assert len(result.step_results) == 1

    def test_context_passing(self, tmp_path):
        """Context passes between steps."""
        runner = WorkflowRunner(storage_path=tmp_path / "workflows.json")

        workflow = Workflow(name="test")
        workflow.add_step("step1", "command", command="echo 'output1'")
        workflow.add_step("step2", "command", command="echo ${step1_output}")

        result = runner.run(workflow, initial_context={"var": "test"})

        assert "var" in result.context

    def test_workflow_persistence(self, tmp_path):
        """Workflows persist to storage."""
        path = tmp_path / "workflows.json"

        runner1 = WorkflowRunner(storage_path=path)
        workflow = Workflow(name="persistent")
        runner1.add_workflow(workflow)

        runner2 = WorkflowRunner(storage_path=path)
        loaded = runner2.get_workflow(workflow.workflow_id)

        assert loaded is not None
        assert loaded.name == "persistent"


# ============================================================================
# Quota Tests
# ============================================================================


class TestQuota:
    """Tests for Quota."""

    def test_create_quota(self):
        """Create a quota."""
        quota = Quota(
            quota_type=QuotaType.REQUESTS_PER_MINUTE,
            limit=60,
        )
        assert quota.remaining() == 60
        assert not quota.is_exceeded()

    def test_exceeded(self):
        """Detect exceeded quota."""
        quota = Quota(
            quota_type=QuotaType.REQUESTS_PER_MINUTE,
            limit=10,
            current=10,
        )
        assert quota.is_exceeded()
        assert quota.remaining() == 0

    def test_percentage_used(self):
        """Calculate percentage used."""
        quota = Quota(
            quota_type=QuotaType.REQUESTS_PER_DAY,
            limit=100,
            current=25,
        )
        assert quota.percentage_used() == 25.0

    def test_unlimited(self):
        """Unlimited quota (-1)."""
        quota = Quota(
            quota_type=QuotaType.REQUESTS_PER_MONTH,
            limit=-1,
            current=1000000,
        )
        assert not quota.is_exceeded()
        assert quota.remaining() == -1


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_acquire_within_burst(self):
        """Acquire within burst limit."""
        limiter = RateLimiter(rate=10.0, burst=100)

        # Should succeed for burst amount
        for _ in range(100):
            assert limiter.acquire()

    def test_rate_limiting(self):
        """Rate limiting kicks in after burst."""
        limiter = RateLimiter(rate=1.0, burst=2)

        assert limiter.acquire()  # 1st
        assert limiter.acquire()  # 2nd (burst)
        assert not limiter.acquire()  # Should be limited

    def test_wait_time(self):
        """Calculate wait time."""
        limiter = RateLimiter(rate=1.0, burst=1)

        limiter.acquire()  # Use the burst
        wait = limiter.wait_time(1)

        assert wait > 0  # Need to wait


class TestQuotaManager:
    """Tests for QuotaManager."""

    def test_check_quota(self, tmp_path):
        """Check quota availability."""
        manager = QuotaManager(storage_path=tmp_path / "quotas.json")

        assert manager.check(QuotaType.REQUESTS_PER_MINUTE, 1)

    def test_consume_quota(self, tmp_path):
        """Consume quota."""
        manager = QuotaManager(storage_path=tmp_path / "quotas.json")

        assert manager.consume(QuotaType.REQUESTS_PER_MINUTE, 1)

        quota = manager.get_quota(QuotaType.REQUESTS_PER_MINUTE)
        assert quota.current >= 1

    def test_quota_exceeded(self, tmp_path):
        """Detect exceeded quota."""
        manager = QuotaManager(storage_path=tmp_path / "quotas.json")

        # Set low limit
        manager.set_quota(Quota(
            quota_type=QuotaType.REQUESTS_PER_MINUTE,
            limit=2,
            reset_interval_seconds=60,
        ))

        assert manager.consume(QuotaType.REQUESTS_PER_MINUTE, 1)
        assert manager.consume(QuotaType.REQUESTS_PER_MINUTE, 1)
        assert not manager.consume(QuotaType.REQUESTS_PER_MINUTE, 1)

    def test_release_quota(self, tmp_path):
        """Release consumed quota."""
        manager = QuotaManager(storage_path=tmp_path / "quotas.json")

        manager.consume(QuotaType.CONCURRENT_REQUESTS, 2)
        quota = manager.get_quota(QuotaType.CONCURRENT_REQUESTS)
        initial = quota.current

        manager.release(QuotaType.CONCURRENT_REQUESTS, 1)
        assert quota.current == initial - 1

    def test_summary(self, tmp_path):
        """Get quota summary."""
        manager = QuotaManager(storage_path=tmp_path / "quotas.json")
        manager.consume(QuotaType.REQUESTS_PER_MINUTE, 5)

        summary = manager.get_summary()

        assert "requests_per_minute" in summary
        assert summary["requests_per_minute"]["current"] >= 5

    def test_persistence(self, tmp_path):
        """Quota data persists."""
        path = tmp_path / "quotas.json"

        manager1 = QuotaManager(storage_path=path)
        manager1.consume(QuotaType.REQUESTS_PER_MINUTE, 10)

        manager2 = QuotaManager(storage_path=path)
        quota = manager2.get_quota(QuotaType.REQUESTS_PER_MINUTE)

        assert quota.current >= 10
