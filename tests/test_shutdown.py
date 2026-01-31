"""
Tests for the shutdown and cancellation system.

© Roura.io
"""
import threading
import time

import pytest

from roura_agent.shutdown import (
    CancellationScope,
    CancellationToken,
    CancelledException,
    clear_interrupt,
    is_interrupt_requested,
    is_shutdown_requested,
    register_cleanup,
    request_interrupt,
    request_shutdown,
    reset_state,
    should_stop,
    unregister_cleanup,
)


class TestShutdownState:
    """Tests for shutdown state management."""

    def setup_method(self):
        """Reset state before each test."""
        reset_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_state()

    def test_initial_state(self):
        """Test that initial state is not shutdown."""
        assert is_shutdown_requested() is False
        assert is_interrupt_requested() is False
        assert should_stop() is False

    def test_request_shutdown(self):
        """Test requesting shutdown."""
        request_shutdown()
        assert is_shutdown_requested() is True
        assert should_stop() is True

    def test_request_interrupt(self):
        """Test requesting interrupt."""
        request_interrupt()
        assert is_interrupt_requested() is True
        assert should_stop() is True

    def test_clear_interrupt(self):
        """Test clearing interrupt."""
        request_interrupt()
        assert is_interrupt_requested() is True

        clear_interrupt()
        assert is_interrupt_requested() is False

    def test_shutdown_persists_after_clear_interrupt(self):
        """Test that shutdown state isn't affected by clear_interrupt."""
        request_shutdown()
        request_interrupt()

        clear_interrupt()
        assert is_shutdown_requested() is True
        assert is_interrupt_requested() is False


class TestCleanupCallbacks:
    """Tests for cleanup callback registration."""

    def setup_method(self):
        reset_state()

    def teardown_method(self):
        reset_state()

    def test_register_cleanup(self):
        """Test registering cleanup callbacks."""
        called = []

        def callback1():
            called.append(1)

        def callback2():
            called.append(2)

        register_cleanup(callback1)
        register_cleanup(callback2)

        # Callbacks aren't called until shutdown
        assert called == []

    def test_unregister_cleanup(self):
        """Test unregistering cleanup callbacks."""
        called = []

        def callback():
            called.append(1)

        register_cleanup(callback)
        unregister_cleanup(callback)

        # Reset and verify callback was removed
        reset_state()


class TestCancellationToken:
    """Tests for CancellationToken."""

    def setup_method(self):
        reset_state()

    def teardown_method(self):
        reset_state()

    def test_initial_state(self):
        """Test initial token state."""
        token = CancellationToken()
        assert token.is_cancelled() is False
        assert token.reason is None

    def test_cancel(self):
        """Test cancelling token."""
        token = CancellationToken()
        token.cancel("test reason")

        assert token.is_cancelled() is True
        assert token.reason == "test reason"

    def test_cancel_default_reason(self):
        """Test cancelling with default reason."""
        token = CancellationToken()
        token.cancel()

        assert token.is_cancelled() is True
        assert token.reason == "cancelled"

    def test_is_cancelled_on_shutdown(self):
        """Test that token is cancelled when shutdown requested."""
        token = CancellationToken()
        request_shutdown()

        assert token.is_cancelled() is True
        assert token.reason == "shutdown"

    def test_reset(self):
        """Test resetting token."""
        token = CancellationToken()
        token.cancel("test")

        token.reset()
        assert token.is_cancelled() is False
        assert token.reason is None

    def test_wait_timeout(self):
        """Test wait with timeout."""
        token = CancellationToken()

        # Should timeout (not cancelled)
        result = token.wait(timeout=0.01)
        assert result is False

    def test_wait_cancelled(self):
        """Test wait when cancelled."""
        token = CancellationToken()

        # Cancel in background thread
        def cancel_later():
            time.sleep(0.01)
            token.cancel()

        thread = threading.Thread(target=cancel_later)
        thread.start()

        # Should return True when cancelled
        result = token.wait(timeout=1.0)
        assert result is True

        thread.join()


class TestCancellationScope:
    """Tests for CancellationScope."""

    def setup_method(self):
        reset_state()

    def teardown_method(self):
        reset_state()

    def test_scope_not_cancelled(self):
        """Test scope that completes normally."""
        with CancellationScope() as scope:
            assert scope.cancelled is False

    def test_scope_cancelled(self):
        """Test cancelling scope."""
        with CancellationScope() as scope:
            scope.cancel("test")
            assert scope.cancelled is True

    def test_scope_cleanup(self):
        """Test scope cleanup callbacks."""
        cleaned = []

        with CancellationScope() as scope:
            scope.on_cleanup(lambda: cleaned.append(1))
            scope.on_cleanup(lambda: cleaned.append(2))

        # Cleanup should run in reverse order
        assert cleaned == [2, 1]

    def test_scope_check_raises(self):
        """Test that check() raises when cancelled."""
        with CancellationScope() as scope:
            scope.cancel("test reason")

            with pytest.raises(CancelledException) as exc_info:
                scope.check()

            assert "test reason" in str(exc_info.value)

    def test_scope_check_ok(self):
        """Test that check() doesn't raise when not cancelled."""
        with CancellationScope() as scope:
            # Should not raise
            scope.check()

    def test_scope_with_custom_token(self):
        """Test scope with custom token."""
        token = CancellationToken()
        token.cancel("pre-cancelled")

        with CancellationScope(token=token) as scope:
            assert scope.cancelled is True


class TestThreadSafety:
    """Tests for thread safety."""

    def setup_method(self):
        reset_state()

    def teardown_method(self):
        reset_state()

    def test_concurrent_requests(self):
        """Test concurrent shutdown requests."""
        errors = []

        def request_many():
            try:
                for _ in range(100):
                    request_shutdown()
                    request_interrupt()
                    is_shutdown_requested()
                    is_interrupt_requested()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=request_many) for _ in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert errors == []
        assert is_shutdown_requested() is True
