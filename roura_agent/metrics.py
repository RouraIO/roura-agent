"""
Roura Agent Metrics - Observability and performance tracking.

Provides metrics collection, timers, and performance tracking.

© Roura.io
"""
from __future__ import annotations

import time
import functools
import threading
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar
from datetime import datetime
from collections import defaultdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class MetricValue:
    """A metric value with timestamp."""
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """A monotonically increasing counter metric."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.Lock()
        self._labels: Dict[tuple, float] = defaultdict(float)

    def inc(self, amount: float = 1.0, **labels) -> None:
        """Increment the counter."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                self._labels[key] += amount
            else:
                self._value += amount

    def get(self, **labels) -> float:
        """Get the current value."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                return self._labels.get(key, 0.0)
            return self._value

    def reset(self) -> None:
        """Reset the counter."""
        with self._lock:
            self._value = 0.0
            self._labels.clear()


class Gauge:
    """A gauge metric that can go up or down."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.Lock()
        self._labels: Dict[tuple, float] = defaultdict(float)

    def set(self, value: float, **labels) -> None:
        """Set the gauge value."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                self._labels[key] = value
            else:
                self._value = value

    def inc(self, amount: float = 1.0, **labels) -> None:
        """Increment the gauge."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                self._labels[key] += amount
            else:
                self._value += amount

    def dec(self, amount: float = 1.0, **labels) -> None:
        """Decrement the gauge."""
        self.inc(-amount, **labels)

    def get(self, **labels) -> float:
        """Get the current value."""
        with self._lock:
            if labels:
                key = tuple(sorted(labels.items()))
                return self._labels.get(key, 0.0)
            return self._value


class Histogram:
    """A histogram for measuring value distributions."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self, name: str, description: str = "", buckets: tuple = None):
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._values: List[float] = []
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        """Record an observation."""
        with self._lock:
            self._values.append(value)

    def get_count(self) -> int:
        """Get the number of observations."""
        with self._lock:
            return len(self._values)

    def get_sum(self) -> float:
        """Get the sum of all observations."""
        with self._lock:
            return sum(self._values)

    def get_avg(self) -> Optional[float]:
        """Get the average value."""
        with self._lock:
            if not self._values:
                return None
            return sum(self._values) / len(self._values)

    def get_percentile(self, p: float) -> Optional[float]:
        """Get the p-th percentile (0-100)."""
        with self._lock:
            if not self._values:
                return None
            sorted_values = sorted(self._values)
            idx = int(len(sorted_values) * (p / 100.0))
            idx = min(idx, len(sorted_values) - 1)
            return sorted_values[idx]

    def get_bucket_counts(self) -> Dict[float, int]:
        """Get counts per bucket."""
        with self._lock:
            counts = {b: 0 for b in self.buckets}
            for v in self._values:
                for b in self.buckets:
                    if v <= b:
                        counts[b] += 1
                        break
            return counts

    def reset(self) -> None:
        """Reset the histogram."""
        with self._lock:
            self._values.clear()


@dataclass
class TimingResult:
    """Result of a timed operation."""
    name: str
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Timer:
    """
    Context manager and decorator for timing operations.

    Example:
        with Timer("api_call") as timer:
            result = api.call()
        print(f"Took {timer.duration}s")

        @Timer("process_data")
        def process_data():
            ...
    """

    def __init__(self, name: str, histogram: Optional[Histogram] = None):
        self.name = name
        self.histogram = histogram
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._success = True
        self._error: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        """Get the duration in seconds."""
        if self._start_time is None:
            return None
        end = self._end_time or time.perf_counter()
        return end - self._start_time

    def __enter__(self) -> "Timer":
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._end_time = time.perf_counter()
        duration = self._end_time - self._start_time

        if exc_type is not None:
            self._success = False
            self._error = str(exc_val)

        if self.histogram:
            self.histogram.observe(duration)

        logger.debug(
            f"Timed operation '{self.name}': {duration:.4f}s (success={self._success})"
        )

        return False  # Don't suppress exceptions

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Use as a decorator."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with Timer(self.name or func.__name__, self.histogram):
                return func(*args, **kwargs)
        return wrapper

    def get_result(self) -> TimingResult:
        """Get the timing result."""
        return TimingResult(
            name=self.name,
            duration_seconds=self.duration or 0.0,
            start_time=datetime.fromtimestamp(self._start_time) if self._start_time else datetime.now(),
            end_time=datetime.fromtimestamp(self._end_time) if self._end_time else datetime.now(),
            success=self._success,
            error=self._error,
        )


class MetricsRegistry:
    """
    Central registry for all metrics.

    Example:
        registry = MetricsRegistry()
        counter = registry.counter("requests", "Total requests")
        counter.inc()
    """

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a gauge."""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def histogram(self, name: str, description: str = "", buckets: tuple = None) -> Histogram:
        """Get or create a histogram."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets)
            return self._histograms[name]

    def timer(self, name: str, histogram_name: Optional[str] = None) -> Timer:
        """Create a timer, optionally backed by a histogram."""
        hist = None
        if histogram_name:
            hist = self.histogram(histogram_name)
        return Timer(name, hist)

    def get_all(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary."""
        with self._lock:
            return {
                "counters": {name: c.get() for name, c in self._counters.items()},
                "gauges": {name: g.get() for name, g in self._gauges.items()},
                "histograms": {
                    name: {
                        "count": h.get_count(),
                        "sum": h.get_sum(),
                        "avg": h.get_avg(),
                        "p50": h.get_percentile(50),
                        "p95": h.get_percentile(95),
                        "p99": h.get_percentile(99),
                    }
                    for name, h in self._histograms.items()
                },
            }

    def reset_all(self) -> None:
        """Reset all metrics."""
        with self._lock:
            for c in self._counters.values():
                c.reset()
            for h in self._histograms.values():
                h.reset()
            # Don't reset gauges - they represent current state


# Global metrics registry
_metrics: Optional[MetricsRegistry] = None


def get_metrics() -> MetricsRegistry:
    """Get the global metrics registry."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsRegistry()
    return _metrics


# Pre-defined metrics for common operations
def _get_tool_metrics() -> tuple[Counter, Counter, Histogram]:
    """Get pre-defined tool metrics."""
    m = get_metrics()
    return (
        m.counter("tool_calls_total", "Total tool calls"),
        m.counter("tool_errors_total", "Total tool errors"),
        m.histogram("tool_duration_seconds", "Tool call duration"),
    )


def _get_llm_metrics() -> tuple[Counter, Counter, Histogram]:
    """Get pre-defined LLM metrics."""
    m = get_metrics()
    return (
        m.counter("llm_requests_total", "Total LLM requests"),
        m.counter("llm_errors_total", "Total LLM errors"),
        m.histogram("llm_duration_seconds", "LLM request duration"),
    )


@contextmanager
def track_operation(
    name: str,
    **labels,
):
    """
    Context manager for tracking an operation.

    Records timing, success/failure, and logs the result.

    Example:
        with track_operation("api_call", endpoint="/users") as op:
            result = api.call()
            op.set_result(result)
    """
    m = get_metrics()
    counter = m.counter(f"{name}_total")
    error_counter = m.counter(f"{name}_errors_total")
    histogram = m.histogram(f"{name}_duration_seconds")

    class OperationTracker:
        def __init__(self):
            self.result = None
            self.error = None
            self.success = True
            self.metadata = {}

        def set_result(self, result: Any) -> None:
            self.result = result

        def set_error(self, error: Exception) -> None:
            self.error = error
            self.success = False

        def add_metadata(self, **kwargs) -> None:
            self.metadata.update(kwargs)

    tracker = OperationTracker()
    start = time.perf_counter()

    try:
        yield tracker
    except Exception as e:
        tracker.set_error(e)
        raise
    finally:
        duration = time.perf_counter() - start
        counter.inc(**labels)
        histogram.observe(duration)

        if not tracker.success:
            error_counter.inc(**labels)

        logger.debug(
            f"Operation '{name}' completed",
            duration=f"{duration:.4f}s",
            success=tracker.success,
            **labels,
            **tracker.metadata,
        )
