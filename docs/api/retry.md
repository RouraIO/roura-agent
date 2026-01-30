# Retry & Resilience Module

The `roura_agent.retry` module provides robust error recovery patterns for building resilient applications.

## Overview

This module includes:
- **Retry Decorator**: Automatic retry with configurable backoff strategies
- **Circuit Breaker**: Prevent cascade failures with fail-fast behavior
- **Fallback Pattern**: Graceful degradation when operations fail
- **Retryable Operation**: Context manager for explicit retry control

## Retry Strategies

```python
from roura_agent.retry import RetryStrategy

# Available strategies
RetryStrategy.IMMEDIATE    # No delay between retries
RetryStrategy.LINEAR       # Constant delay
RetryStrategy.EXPONENTIAL  # Exponential backoff (default)
RetryStrategy.JITTER       # Exponential with random variation
```

## Basic Usage

### Retry Decorator

```python
from roura_agent.retry import retry

@retry(max_attempts=3, base_delay=1.0)
def fetch_data():
    """Automatically retries up to 3 times on failure."""
    return api.call()

# With specific exceptions
@retry(
    max_attempts=5,
    base_delay=2.0,
    retryable=(ConnectionError, TimeoutError),
)
def network_call():
    return requests.get(url)

# With callback on retry
def log_retry(error, attempt):
    print(f"Retry {attempt}: {error}")

@retry(max_attempts=3, on_retry=log_retry)
def important_operation():
    return do_work()
```

### RetryConfig

```python
from roura_agent.retry import RetryConfig, RetryStrategy

config = RetryConfig(
    max_attempts=5,           # Maximum retry attempts
    base_delay=1.0,           # Base delay in seconds
    max_delay=60.0,           # Maximum delay cap
    strategy=RetryStrategy.EXPONENTIAL,
    jitter_factor=0.1,        # For JITTER strategy
    retryable_exceptions=(Exception,),
    on_retry=None,            # Optional callback
)
```

## Circuit Breaker

The circuit breaker prevents cascade failures by failing fast when a service is unavailable.

### States

- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Service unavailable, requests fail immediately
- **HALF_OPEN**: Testing if service recovered

### Usage

```python
from roura_agent.retry import CircuitBreaker, CircuitOpenError

breaker = CircuitBreaker(
    failure_threshold=5,    # Failures before opening
    success_threshold=2,    # Successes to close from half-open
    timeout=30.0,           # Seconds before testing recovery
)

@breaker
def call_external_service():
    return api.request()

# Handle circuit open
try:
    result = call_external_service()
except CircuitOpenError:
    # Service is unavailable, use fallback
    result = get_cached_data()
```

### Manual Control

```python
# Check state
if breaker.state == CircuitState.OPEN:
    print("Service is down")

# Manual reset
breaker.reset()
```

## Fallback Pattern

Graceful degradation when operations fail.

```python
from roura_agent.retry import with_fallback, FallbackResult

@with_fallback(fallback_value=[])
def get_items():
    return api.fetch_items()

# Returns FallbackResult
result = get_items()
if result.used_fallback:
    print(f"Using fallback due to: {result.original_error}")
items = result.value

# With fallback function
def cached_items(user_id):
    return cache.get(f"items:{user_id}", [])

@with_fallback(fallback_func=cached_items)
def get_user_items(user_id):
    return api.fetch_user_items(user_id)

# Only catch specific exceptions
@with_fallback(
    fallback_value="unknown",
    exceptions=(ConnectionError, TimeoutError),
)
def get_status():
    return api.get_status()
```

## Retryable Operation Context Manager

For explicit control over the retry loop.

```python
from roura_agent.retry import RetryableOperation

with RetryableOperation(max_attempts=3, base_delay=1.0) as op:
    while op.should_retry():
        try:
            result = risky_operation()
            op.success(result)
        except RecoverableError as e:
            op.failure(e)

# Access result (raises last error if all attempts failed)
final_result = op.result
print(f"Succeeded on attempt {op.attempt}")
```

## Specialized Decorators

### Rate Limit Retry

Optimized for API rate limits with longer delays.

```python
from roura_agent.retry import retry_on_rate_limit

@retry_on_rate_limit
def api_call():
    return client.request()

# Equivalent to:
# @retry(max_attempts=5, base_delay=2.0, max_delay=120.0, strategy=JITTER)
```

### Network Error Retry

Retries on common network exceptions.

```python
from roura_agent.retry import retry_on_network_error

@retry_on_network_error
def fetch_data():
    return httpx.get(url)

# Catches: ConnectionError, TimeoutError, httpx.TimeoutException,
#          httpx.ConnectError, httpx.NetworkError
```

## Delay Calculation

```python
from roura_agent.retry import calculate_delay, RetryConfig

config = RetryConfig(
    strategy=RetryStrategy.EXPONENTIAL,
    base_delay=1.0,
    max_delay=30.0,
)

# Calculate delay for each attempt
print(calculate_delay(config, 0))  # 1.0
print(calculate_delay(config, 1))  # 2.0
print(calculate_delay(config, 2))  # 4.0
print(calculate_delay(config, 5))  # 30.0 (capped)
```

## Best Practices

1. **Choose appropriate retry counts**: Network calls typically need 3-5 retries, database operations 2-3.

2. **Use exponential backoff**: Prevents overwhelming recovering services.

3. **Add jitter for distributed systems**: Prevents thundering herd problem.

4. **Set reasonable timeouts**: Don't retry indefinitely.

5. **Combine with circuit breaker**: For external service calls.

```python
breaker = CircuitBreaker(failure_threshold=3)

@breaker
@retry(max_attempts=3, base_delay=1.0)
def resilient_service_call():
    return external_api.call()
```

## Error Handling

```python
from roura_agent.retry import CircuitOpenError

try:
    result = protected_call()
except CircuitOpenError as e:
    # Circuit is open, service unavailable
    log.warning(f"Service down: {e}")
    result = fallback_value
except Exception as e:
    # All retries exhausted
    log.error(f"Operation failed after retries: {e}")
    raise
```

## API Reference

### Classes

| Class | Description |
|-------|-------------|
| `RetryStrategy` | Enum of backoff strategies |
| `RetryConfig` | Configuration for retry behavior |
| `CircuitBreaker` | Circuit breaker implementation |
| `CircuitState` | Circuit breaker states |
| `CircuitOpenError` | Raised when circuit is open |
| `FallbackResult` | Result wrapper with fallback info |
| `RetryableOperation` | Context manager for explicit retry |

### Functions

| Function | Description |
|----------|-------------|
| `retry()` | Decorator for automatic retry |
| `calculate_delay()` | Calculate delay for an attempt |
| `with_fallback()` | Decorator for fallback values |
| `retry_on_rate_limit` | Specialized for rate limits |
| `retry_on_network_error` | Specialized for network errors |
