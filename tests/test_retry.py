"""
Tests for the retry and resilience module.

© Roura.io
"""
import pytest
import time
from unittest.mock import Mock, patch
from threading import Thread

from roura_agent.retry import (
    RetryStrategy,
    RetryConfig,
    calculate_delay,
    retry,
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    with_fallback,
    FallbackResult,
    RetryableOperation,
    retry_on_rate_limit,
    retry_on_network_error,
)


class TestCalculateDelay:
    """Tests for calculate_delay function."""

    def test_immediate_returns_zero(self):
        """Test IMMEDIATE strategy returns no delay."""
        config = RetryConfig(strategy=RetryStrategy.IMMEDIATE)
        assert calculate_delay(config, 0) == 0.0
        assert calculate_delay(config, 5) == 0.0

    def test_linear_returns_base_delay(self):
        """Test LINEAR strategy returns base delay."""
        config = RetryConfig(strategy=RetryStrategy.LINEAR, base_delay=2.0)
        assert calculate_delay(config, 0) == 2.0
        assert calculate_delay(config, 5) == 2.0

    def test_exponential_doubles_delay(self):
        """Test EXPONENTIAL strategy doubles delay each attempt."""
        config = RetryConfig(strategy=RetryStrategy.EXPONENTIAL, base_delay=1.0)
        assert calculate_delay(config, 0) == 1.0
        assert calculate_delay(config, 1) == 2.0
        assert calculate_delay(config, 2) == 4.0

    def test_max_delay_cap(self):
        """Test delay is capped at max_delay."""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=10.0,
            max_delay=30.0,
        )
        # 10 * 2^3 = 80, but capped at 30
        assert calculate_delay(config, 3) == 30.0

    def test_jitter_adds_randomness(self):
        """Test JITTER strategy adds random variation."""
        config = RetryConfig(strategy=RetryStrategy.JITTER, base_delay=1.0, jitter_factor=0.5)
        # Run multiple times and check values are different
        delays = [calculate_delay(config, 1) for _ in range(10)]
        # At least some should be different (very unlikely all same)
        assert len(set(delays)) > 1


class TestRetryDecorator:
    """Tests for retry decorator."""

    def test_succeeds_first_try(self):
        """Test function succeeds on first try."""
        mock_func = Mock(return_value="success")

        @retry(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()

        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 1

    def test_retries_on_failure(self):
        """Test function retries on failure."""
        mock_func = Mock(side_effect=[ValueError("fail"), ValueError("fail"), "success"])

        @retry(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()

        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 3

    def test_max_attempts_exceeded(self):
        """Test raises after max attempts."""
        mock_func = Mock(side_effect=ValueError("always fails"))

        @retry(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()

        with pytest.raises(ValueError, match="always fails"):
            test_func()

        assert mock_func.call_count == 3

    def test_only_retries_specified_exceptions(self):
        """Test only retries on specified exception types."""
        mock_func = Mock(side_effect=TypeError("not retryable"))

        @retry(max_attempts=3, base_delay=0.01, retryable=(ValueError,))
        def test_func():
            return mock_func()

        with pytest.raises(TypeError):
            test_func()

        # Should only try once since TypeError is not retryable
        assert mock_func.call_count == 1

    def test_on_retry_callback(self):
        """Test on_retry callback is called."""
        callback = Mock()
        mock_func = Mock(side_effect=[ValueError("fail"), "success"])

        @retry(max_attempts=3, base_delay=0.01, on_retry=callback)
        def test_func():
            return mock_func()

        test_func()
        callback.assert_called_once()
        args = callback.call_args[0]
        assert isinstance(args[0], ValueError)
        assert args[1] == 1  # First retry


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_starts_closed(self):
        """Test circuit starts in closed state."""
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED

    def test_opens_after_failures(self):
        """Test circuit opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=2)

        @breaker
        def failing_func():
            raise ValueError("failure")

        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        assert breaker.state == CircuitState.OPEN

    def test_rejects_when_open(self):
        """Test requests are rejected when circuit is open."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=10)

        @breaker
        def failing_func():
            raise ValueError("failure")

        with pytest.raises(ValueError):
            failing_func()

        # Now circuit is open
        with pytest.raises(CircuitOpenError):
            failing_func()

    def test_half_open_after_timeout(self):
        """Test circuit goes to half-open after timeout."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0.1)

        @breaker
        def failing_func():
            raise ValueError("failure")

        with pytest.raises(ValueError):
            failing_func()

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.15)

        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self):
        """Test circuit closes after success in half-open state."""
        breaker = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout=0.1)
        call_count = [0]

        @breaker
        def flaky_func():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("first call fails")
            return "success"

        # First call fails, opens circuit
        with pytest.raises(ValueError):
            flaky_func()

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.15)

        # Second call succeeds, closes circuit
        result = flaky_func()
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_reset(self):
        """Test manual reset."""
        breaker = CircuitBreaker(failure_threshold=1)

        @breaker
        def failing_func():
            raise ValueError("failure")

        with pytest.raises(ValueError):
            failing_func()

        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED


class TestWithFallback:
    """Tests for with_fallback decorator."""

    def test_returns_value_on_success(self):
        """Test returns normal value on success."""
        @with_fallback(fallback_value="default")
        def successful_func():
            return "success"

        result = successful_func()
        assert result.value == "success"
        assert result.used_fallback is False

    def test_returns_fallback_on_failure(self):
        """Test returns fallback on failure."""
        @with_fallback(fallback_value="default")
        def failing_func():
            raise ValueError("fail")

        result = failing_func()
        assert result.value == "default"
        assert result.used_fallback is True
        assert isinstance(result.original_error, ValueError)

    def test_only_catches_specified_exceptions(self):
        """Test only catches specified exceptions."""
        @with_fallback(fallback_value="default", exceptions=(ValueError,))
        def failing_func():
            raise TypeError("not caught")

        with pytest.raises(TypeError):
            failing_func()

    def test_fallback_func(self):
        """Test fallback function is called."""
        def fallback_handler(x):
            return f"fallback: {x}"

        @with_fallback(fallback_func=fallback_handler)
        def failing_func(x):
            raise ValueError("fail")

        result = failing_func("test")
        assert result.value == "fallback: test"
        assert result.used_fallback is True


class TestRetryableOperation:
    """Tests for RetryableOperation context manager."""

    def test_success_on_first_try(self):
        """Test operation succeeds on first try."""
        with RetryableOperation(max_attempts=3) as op:
            while op.should_retry():
                op.success("result")

        assert op.result == "result"
        assert op.attempt == 1

    def test_success_after_retries(self):
        """Test operation succeeds after retries."""
        attempt_count = [0]

        with RetryableOperation(max_attempts=3, base_delay=0.01) as op:
            while op.should_retry():
                attempt_count[0] += 1
                if attempt_count[0] < 3:
                    op.failure(ValueError("try again"))
                else:
                    op.success("result")

        assert op.result == "result"
        assert op.attempt == 3

    def test_raises_after_max_attempts(self):
        """Test raises last error after max attempts."""
        with RetryableOperation(max_attempts=2, base_delay=0.01) as op:
            while op.should_retry():
                op.failure(ValueError("always fails"))

        with pytest.raises(ValueError, match="always fails"):
            _ = op.result


class TestSpecializedRetryDecorators:
    """Tests for specialized retry decorators."""

    def test_retry_on_rate_limit(self):
        """Test retry_on_rate_limit decorator."""
        mock_func = Mock(side_effect=[ValueError("rate limited"), "success"])

        @retry_on_rate_limit
        def api_call():
            return mock_func()

        # Should work since we're using generic Exception retries
        result = api_call()
        assert result == "success"

    @patch("roura_agent.retry.time.sleep")
    def test_retry_on_network_error(self, mock_sleep):
        """Test retry_on_network_error decorator."""
        import httpx

        mock_func = Mock(side_effect=[httpx.ConnectError("connection failed"), "success"])

        @retry_on_network_error
        def network_call():
            return mock_func()

        result = network_call()
        assert result == "success"
        assert mock_func.call_count == 2
