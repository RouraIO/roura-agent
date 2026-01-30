# Metrics & Observability Module

The `roura_agent.metrics` module provides instrumentation for monitoring application performance and behavior.

## Overview

This module includes:
- **Counter**: Monotonically increasing metric (requests, errors)
- **Gauge**: Value that can go up or down (connections, queue size)
- **Histogram**: Distribution of values (latencies, sizes)
- **Timer**: Measure operation duration
- **MetricsRegistry**: Central collection point

## Quick Start

```python
from roura_agent.metrics import get_metrics, track_operation

# Get the global metrics registry
m = get_metrics()

# Track a counter
m.counter("requests_total").inc()
m.counter("requests_total").inc(method="GET")

# Track a gauge
m.gauge("active_connections").set(42)

# Track a histogram
m.histogram("response_time").observe(0.234)

# Time an operation
with track_operation("api_call", endpoint="/users") as op:
    result = api.call()
    op.set_result(result)
```

## Counter

A monotonically increasing metric. Use for counting events.

```python
from roura_agent.metrics import Counter

counter = Counter("http_requests", "Total HTTP requests")

# Increment by 1
counter.inc()

# Increment by custom amount
counter.inc(5)

# With labels
counter.inc(method="GET", status="200")
counter.inc(2, method="POST", status="201")

# Get value
total = counter.get()
get_requests = counter.get(method="GET")

# Reset
counter.reset()
```

## Gauge

A metric that can increase or decrease. Use for current state.

```python
from roura_agent.metrics import Gauge

gauge = Gauge("queue_size", "Current queue size")

# Set value
gauge.set(100)

# Increment/decrement
gauge.inc()      # +1
gauge.inc(10)    # +10
gauge.dec()      # -1
gauge.dec(5)     # -5

# With labels
gauge.set(50, region="us-east")
gauge.set(30, region="eu-west")

# Get value
current = gauge.get()
us_east = gauge.get(region="us-east")
```

## Histogram

Track distribution of values. Use for latencies, sizes.

```python
from roura_agent.metrics import Histogram

# Default buckets optimized for latencies
hist = Histogram("request_duration", "Request duration in seconds")

# Custom buckets
hist = Histogram(
    "file_size",
    "File size in bytes",
    buckets=(100, 1000, 10000, 100000, 1000000),
)

# Record observations
hist.observe(0.123)
hist.observe(0.456)
hist.observe(1.234)

# Get statistics
count = hist.get_count()     # Number of observations
total = hist.get_sum()       # Sum of all values
avg = hist.get_avg()         # Average value

# Get percentiles
p50 = hist.get_percentile(50)   # Median
p95 = hist.get_percentile(95)   # 95th percentile
p99 = hist.get_percentile(99)   # 99th percentile

# Get bucket counts
buckets = hist.get_bucket_counts()

# Reset
hist.reset()
```

## Timer

Measure operation duration. Works as context manager or decorator.

```python
from roura_agent.metrics import Timer, Histogram

# As context manager
with Timer("database_query") as timer:
    result = db.query("SELECT * FROM users")

print(f"Query took {timer.duration:.3f}s")

# As decorator
@Timer("process_data")
def process_data():
    # ... processing ...
    return result

# With histogram for aggregation
hist = Histogram("query_duration")

with Timer("query", histogram=hist):
    db.query("SELECT 1")

# Get timing result with metadata
with Timer("operation") as timer:
    try:
        result = risky_operation()
    except Exception as e:
        pass  # Timer captures exception

timing_result = timer.get_result()
print(f"Success: {timing_result.success}")
print(f"Duration: {timing_result.duration_seconds}s")
if timing_result.error:
    print(f"Error: {timing_result.error}")
```

### TimingResult

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TimingResult:
    name: str
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    success: bool
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
```

## MetricsRegistry

Central registry for all metrics. Ensures metric reuse.

```python
from roura_agent.metrics import MetricsRegistry

registry = MetricsRegistry()

# Get or create metrics (same name returns same instance)
c1 = registry.counter("requests")
c2 = registry.counter("requests")
assert c1 is c2

# Create different metric types
counter = registry.counter("events_total", "Total events")
gauge = registry.gauge("connections", "Active connections")
histogram = registry.histogram("latency", "Request latency")

# Create timer with backing histogram
timer = registry.timer("operation", histogram_name="operation_duration")

# Get all metrics as dictionary
all_metrics = registry.get_all()
# {
#     "counters": {"events_total": 42},
#     "gauges": {"connections": 10},
#     "histograms": {
#         "latency": {"count": 100, "sum": 12.5, "avg": 0.125, ...}
#     }
# }

# Reset all metrics (except gauges)
registry.reset_all()
```

## Global Metrics

Use the global registry for application-wide metrics.

```python
from roura_agent.metrics import get_metrics

# Get singleton registry
m = get_metrics()

# Same instance everywhere
assert get_metrics() is get_metrics()

# Use it
m.counter("app_starts").inc()
m.gauge("version").set(1.0)
```

## Track Operation

High-level context manager for tracking operations.

```python
from roura_agent.metrics import track_operation

# Basic usage
with track_operation("user_registration") as op:
    user = create_user(data)
    op.set_result(user)
    op.add_metadata(user_id=user.id)

# With labels
with track_operation("api_call", endpoint="/users", method="GET") as op:
    response = api.get("/users")
    op.set_result(response)

# Automatically tracks:
# - Counter: {name}_total (incremented)
# - Counter: {name}_errors_total (on exception)
# - Histogram: {name}_duration_seconds

# Exception handling
with track_operation("risky_op") as op:
    result = might_fail()  # If this raises, error counter increments
```

## Thread Safety

All metrics are thread-safe.

```python
import threading
from roura_agent.metrics import Counter

counter = Counter("concurrent_ops")

def worker():
    for _ in range(1000):
        counter.inc()

# Safe to use from multiple threads
threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

assert counter.get() == 10000
```

## Pre-defined Metrics

Helper functions for common metric patterns.

```python
from roura_agent.metrics import _get_tool_metrics, _get_llm_metrics

# Tool metrics
tool_calls, tool_errors, tool_duration = _get_tool_metrics()

# LLM metrics
llm_requests, llm_errors, llm_duration = _get_llm_metrics()
```

## Best Practices

### 1. Use Labels Sparingly

```python
# Good - bounded cardinality
counter.inc(method="GET")
counter.inc(status_code="200")

# Bad - unbounded cardinality
counter.inc(user_id="12345")  # Too many unique values
```

### 2. Choose the Right Metric Type

```python
# Counter: Cumulative, always increasing
m.counter("requests_total")
m.counter("errors_total")
m.counter("bytes_sent")

# Gauge: Current value, can change
m.gauge("active_connections")
m.gauge("queue_size")
m.gauge("temperature")

# Histogram: Distribution of values
m.histogram("request_duration")
m.histogram("response_size")
```

### 3. Name Metrics Consistently

```python
# Use snake_case
# Include unit suffix
# End counters with _total

m.counter("http_requests_total")
m.histogram("http_request_duration_seconds")
m.gauge("process_memory_bytes")
```

### 4. Initialize Metrics at Startup

```python
# Initialize with 0 to ensure metric exists
m = get_metrics()
m.counter("errors_total").inc(0)  # Shows up even with no errors
```

## API Reference

### Classes

| Class | Description |
|-------|-------------|
| `Counter` | Monotonically increasing counter |
| `Gauge` | Value that can increase or decrease |
| `Histogram` | Distribution of observed values |
| `Timer` | Context manager/decorator for timing |
| `TimingResult` | Result of a timed operation |
| `MetricsRegistry` | Central metrics collection |
| `MetricValue` | Value with timestamp and labels |

### Functions

| Function | Description |
|----------|-------------|
| `get_metrics()` | Get global metrics registry |
| `track_operation()` | Context manager for operation tracking |

### Histogram Default Buckets

```python
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
```
