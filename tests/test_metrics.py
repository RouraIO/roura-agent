"""
Tests for the metrics and observability module.

© Roura.io
"""
import pytest
import time
from unittest.mock import Mock, patch

from roura_agent.metrics import (
    Counter,
    Gauge,
    Histogram,
    Timer,
    TimingResult,
    MetricsRegistry,
    get_metrics,
    track_operation,
)


class TestCounter:
    """Tests for Counter metric."""

    def test_starts_at_zero(self):
        """Test counter starts at zero."""
        counter = Counter("test")
        assert counter.get() == 0.0

    def test_increment(self):
        """Test incrementing counter."""
        counter = Counter("test")
        counter.inc()
        assert counter.get() == 1.0
        counter.inc(5)
        assert counter.get() == 6.0

    def test_labels(self):
        """Test counter with labels."""
        counter = Counter("test")
        counter.inc(method="GET")
        counter.inc(method="POST")
        counter.inc(2, method="GET")

        assert counter.get(method="GET") == 3.0
        assert counter.get(method="POST") == 1.0
        assert counter.get(method="DELETE") == 0.0

    def test_reset(self):
        """Test resetting counter."""
        counter = Counter("test")
        counter.inc(10)
        counter.reset()
        assert counter.get() == 0.0


class TestGauge:
    """Tests for Gauge metric."""

    def test_starts_at_zero(self):
        """Test gauge starts at zero."""
        gauge = Gauge("test")
        assert gauge.get() == 0.0

    def test_set(self):
        """Test setting gauge value."""
        gauge = Gauge("test")
        gauge.set(42.5)
        assert gauge.get() == 42.5

    def test_inc_dec(self):
        """Test incrementing and decrementing gauge."""
        gauge = Gauge("test")
        gauge.inc()
        assert gauge.get() == 1.0
        gauge.dec(0.5)
        assert gauge.get() == 0.5

    def test_labels(self):
        """Test gauge with labels."""
        gauge = Gauge("test")
        gauge.set(10, region="us")
        gauge.set(20, region="eu")

        assert gauge.get(region="us") == 10
        assert gauge.get(region="eu") == 20


class TestHistogram:
    """Tests for Histogram metric."""

    def test_observe(self):
        """Test observing values."""
        hist = Histogram("test")
        hist.observe(0.1)
        hist.observe(0.2)
        hist.observe(0.3)

        assert hist.get_count() == 3
        assert hist.get_sum() == pytest.approx(0.6)
        assert hist.get_avg() == pytest.approx(0.2)

    def test_percentiles(self):
        """Test percentile calculations."""
        hist = Histogram("test")
        for i in range(1, 101):
            hist.observe(i)

        assert hist.get_percentile(50) == pytest.approx(50, abs=1)
        assert hist.get_percentile(95) == pytest.approx(95, abs=1)
        assert hist.get_percentile(99) == pytest.approx(99, abs=1)

    def test_empty_histogram(self):
        """Test empty histogram returns None for statistics."""
        hist = Histogram("test")
        assert hist.get_count() == 0
        assert hist.get_avg() is None
        assert hist.get_percentile(50) is None

    def test_reset(self):
        """Test resetting histogram."""
        hist = Histogram("test")
        hist.observe(1.0)
        hist.reset()
        assert hist.get_count() == 0


class TestTimer:
    """Tests for Timer."""

    def test_context_manager(self):
        """Test using timer as context manager."""
        with Timer("test") as timer:
            time.sleep(0.01)

        assert timer.duration is not None
        assert timer.duration >= 0.01

    def test_decorator(self):
        """Test using timer as decorator."""
        @Timer("test_func")
        def slow_func():
            time.sleep(0.01)
            return "done"

        result = slow_func()
        assert result == "done"

    def test_with_histogram(self):
        """Test timer records to histogram."""
        hist = Histogram("timing")

        with Timer("test", histogram=hist):
            time.sleep(0.01)

        assert hist.get_count() == 1
        assert hist.get_sum() >= 0.01

    def test_exception_handling(self):
        """Test timer handles exceptions."""
        with pytest.raises(ValueError):
            with Timer("test") as timer:
                raise ValueError("test error")

        result = timer.get_result()
        assert result.success is False
        assert "test error" in result.error


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    def test_get_or_create_counter(self):
        """Test getting or creating counter."""
        registry = MetricsRegistry()
        c1 = registry.counter("test")
        c2 = registry.counter("test")

        assert c1 is c2

    def test_get_or_create_gauge(self):
        """Test getting or creating gauge."""
        registry = MetricsRegistry()
        g1 = registry.gauge("test")
        g2 = registry.gauge("test")

        assert g1 is g2

    def test_get_or_create_histogram(self):
        """Test getting or creating histogram."""
        registry = MetricsRegistry()
        h1 = registry.histogram("test")
        h2 = registry.histogram("test")

        assert h1 is h2

    def test_timer_creation(self):
        """Test creating timer from registry."""
        registry = MetricsRegistry()
        timer = registry.timer("test", histogram_name="test_duration")

        assert timer.name == "test"
        assert timer.histogram is not None

    def test_get_all(self):
        """Test getting all metrics."""
        registry = MetricsRegistry()
        registry.counter("requests").inc(10)
        registry.gauge("connections").set(5)
        registry.histogram("duration").observe(0.5)

        all_metrics = registry.get_all()

        assert "counters" in all_metrics
        assert "gauges" in all_metrics
        assert "histograms" in all_metrics
        assert all_metrics["counters"]["requests"] == 10
        assert all_metrics["gauges"]["connections"] == 5
        assert all_metrics["histograms"]["duration"]["count"] == 1

    def test_reset_all(self):
        """Test resetting all metrics."""
        registry = MetricsRegistry()
        registry.counter("test").inc(10)
        registry.histogram("test").observe(1.0)
        registry.gauge("test").set(5)

        registry.reset_all()

        assert registry.counter("test").get() == 0
        assert registry.histogram("test").get_count() == 0
        # Gauge is NOT reset
        assert registry.gauge("test").get() == 5


class TestGlobalMetrics:
    """Tests for global metrics functions."""

    def test_get_metrics_singleton(self):
        """Test get_metrics returns singleton."""
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_track_operation_success(self):
        """Test tracking successful operation."""
        with track_operation("test_op", label="value") as op:
            op.set_result("success")
            op.add_metadata(extra="info")

        m = get_metrics()
        assert m.counter("test_op_total").get(label="value") >= 1
        assert m.histogram("test_op_duration_seconds").get_count() >= 1

    def test_track_operation_failure(self):
        """Test tracking failed operation."""
        with pytest.raises(ValueError):
            with track_operation("failing_op") as op:
                raise ValueError("error")

        m = get_metrics()
        assert m.counter("failing_op_errors_total").get() >= 1


class TestThreadSafety:
    """Tests for thread safety."""

    def test_counter_thread_safe(self):
        """Test counter is thread safe."""
        import threading

        counter = Counter("test")
        threads = []

        def inc_many():
            for _ in range(1000):
                counter.inc()

        for _ in range(10):
            t = threading.Thread(target=inc_many)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert counter.get() == 10000

    def test_histogram_thread_safe(self):
        """Test histogram is thread safe."""
        import threading

        hist = Histogram("test")
        threads = []

        def observe_many():
            for i in range(100):
                hist.observe(i * 0.01)

        for _ in range(10):
            t = threading.Thread(target=observe_many)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert hist.get_count() == 1000
