"""
Roura Agent Retry & Resilience - Error recovery patterns.

Provides retry logic, circuit breakers, and graceful degradation.

© Roura.io
"""
from __future__ import annotations

import time
import random
import functools
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type, TypeVar, Generic
from enum import Enum
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryStrategy(Enum):
    """Retry backoff strategies."""
    IMMEDIATE = "immediate"         # No delay between retries
    LINEAR = "linear"               # Constant delay
    EXPONENTIAL = "exponential"     # Exponential backoff
    JITTER = "jitter"               # Exponential with randomized jitter


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0         # Base delay in seconds
    max_delay: float = 60.0         # Maximum delay cap
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    jitter_factor: float = 0.1      # For JITTER strategy
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)
    on_retry: Optional[Callable[[Exception, int], None]] = None


def calculate_delay(config: RetryConfig, attempt: int) -> float:
    """Calculate delay before next retry attempt."""
    if config.strategy == RetryStrategy.IMMEDIATE:
        return 0.0

    if config.strategy == RetryStrategy.LINEAR:
        delay = config.base_delay

    elif config.strategy in (RetryStrategy.EXPONENTIAL, RetryStrategy.JITTER):
        delay = config.base_delay * (2 ** attempt)

    else:
        delay = config.base_delay

    # Apply jitter if requested
    if config.strategy == RetryStrategy.JITTER:
        jitter = delay * config.jitter_factor * random.random()
        delay = delay + jitter

    # Cap at max delay
    return min(delay, config.max_delay)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    retryable: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator that adds retry logic to a function.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay cap
        strategy: Backoff strategy
        retryable: Tuple of exception types that should trigger retry
        on_retry: Optional callback called on each retry

    Example:
        @retry(max_attempts=3, base_delay=1.0, retryable=(ConnectionError,))
        def fetch_data():
            return requests.get(url)
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        strategy=strategy,
        retryable_exceptions=retryable,
        on_retry=on_retry,
    )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = calculate_delay(config, attempt)
                        logger.debug(
                            f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__}: "
                            f"{e}, waiting {delay:.2f}s"
                        )

                        if config.on_retry:
                            config.on_retry(e, attempt + 1)

                        if delay > 0:
                            time.sleep(delay)
                    else:
                        logger.warning(
                            f"Max retries ({config.max_attempts}) reached for {func.__name__}: {e}"
                        )

            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry state")

        return wrapper
    return decorator


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, rejecting requests
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5      # Failures before opening
    success_threshold: int = 2      # Successes to close from half-open
    timeout: float = 30.0           # Seconds in open state before half-open
    excluded_exceptions: tuple[Type[Exception], ...] = ()


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents cascade failures by failing fast when a service is down.

    Example:
        breaker = CircuitBreaker(failure_threshold=3, timeout=30)

        @breaker
        def call_external_service():
            return api.request()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
        excluded_exceptions: tuple[Type[Exception], ...] = (),
        name: str = "default",
    ):
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            excluded_exceptions=excluded_exceptions,
        )
        self.name = name
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                if self._last_failure_time:
                    elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                    if elapsed >= self.config.timeout:
                        self._state = CircuitState.HALF_OPEN
                        self._success_count = 0
            return self._state

    def _record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"Circuit breaker '{self.name}' closed")
            else:
                self._failure_count = 0

    def _record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        with self._lock:
            # Don't count excluded exceptions
            if isinstance(exception, self.config.excluded_exceptions):
                return

            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker '{self.name}' re-opened")
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}' opened after "
                    f"{self._failure_count} failures"
                )

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorate a function with circuit breaker logic."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            state = self.state

            if state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is open - "
                    f"service unavailable"
                )

            try:
                result = func(*args, **kwargs)
                self._record_success()
                return result
            except Exception as e:
                self._record_failure(e)
                raise

        return wrapper

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


@dataclass
class FallbackResult(Generic[T]):
    """Result wrapper with fallback information."""
    value: T
    used_fallback: bool = False
    original_error: Optional[Exception] = None


def with_fallback(
    fallback_value: T = None,
    fallback_func: Optional[Callable[..., T]] = None,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., FallbackResult[T]]]:
    """
    Decorator that provides fallback values on failure.

    Args:
        fallback_value: Static fallback value to return
        fallback_func: Function to call for fallback (receives original args)
        exceptions: Exception types that trigger fallback

    Example:
        @with_fallback(fallback_value=[], exceptions=(ConnectionError,))
        def get_items():
            return api.fetch_items()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., FallbackResult[T]]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> FallbackResult[T]:
            try:
                result = func(*args, **kwargs)
                return FallbackResult(value=result, used_fallback=False)
            except exceptions as e:
                logger.debug(f"Using fallback for {func.__name__}: {e}")
                if fallback_func:
                    value = fallback_func(*args, **kwargs)
                else:
                    value = fallback_value
                return FallbackResult(
                    value=value,
                    used_fallback=True,
                    original_error=e,
                )

        return wrapper
    return decorator


class RetryableOperation:
    """
    Context manager for retryable operations with cleanup.

    Example:
        with RetryableOperation(max_attempts=3) as op:
            while op.should_retry():
                try:
                    result = risky_operation()
                    op.success(result)
                except SomeError as e:
                    op.failure(e)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    ):
        self.config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            strategy=strategy,
        )
        self._attempt = 0
        self._succeeded = False
        self._result: Any = None
        self._last_error: Optional[Exception] = None

    def __enter__(self) -> "RetryableOperation":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False  # Don't suppress exceptions

    def should_retry(self) -> bool:
        """Check if another retry attempt should be made."""
        return not self._succeeded and self._attempt < self.config.max_attempts

    def success(self, result: Any = None) -> None:
        """Mark the operation as successful."""
        self._succeeded = True
        self._result = result

    def failure(self, error: Exception) -> None:
        """Record a failure and wait before next attempt."""
        self._last_error = error
        self._attempt += 1

        if self._attempt < self.config.max_attempts:
            delay = calculate_delay(self.config, self._attempt - 1)
            if delay > 0:
                time.sleep(delay)

    @property
    def result(self) -> Any:
        """Get the result if successful."""
        if not self._succeeded and self._last_error:
            raise self._last_error
        return self._result

    @property
    def attempt(self) -> int:
        """Current attempt number (1-indexed)."""
        return self._attempt + 1


def retry_on_rate_limit(func: Callable[..., T]) -> Callable[..., T]:
    """
    Specialized retry decorator for rate-limited API calls.

    Uses exponential backoff with jitter, suitable for API rate limits.
    """
    return retry(
        max_attempts=5,
        base_delay=2.0,
        max_delay=120.0,
        strategy=RetryStrategy.JITTER,
    )(func)


def retry_on_network_error(func: Callable[..., T]) -> Callable[..., T]:
    """
    Specialized retry decorator for network errors.

    Retries on common network-related exceptions.
    """
    import httpx

    return retry(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        strategy=RetryStrategy.EXPONENTIAL,
        retryable=(
            ConnectionError,
            TimeoutError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
        ),
    )(func)
