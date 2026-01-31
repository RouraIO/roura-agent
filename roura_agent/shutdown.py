"""
Roura Agent Shutdown - Race-free shutdown and cancellation handling.

Provides centralized signal handling and graceful shutdown for:
- SIGINT (Ctrl+C)
- SIGTERM (kill signal)
- ESC key interrupt

© Roura.io
"""
from __future__ import annotations

import atexit
import signal
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ShutdownState:
    """Global shutdown state tracking."""
    # Shutdown requested (second Ctrl+C or SIGTERM)
    shutdown_requested: bool = False
    # Interrupt requested (first Ctrl+C - stops current operation)
    interrupt_requested: bool = False
    # Lock for thread-safe access
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Registered cleanup callbacks
    _cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)
    # Original signal handlers (for restoration)
    _original_handlers: dict[int, Optional[signal.Handlers]] = field(default_factory=dict)
    # Whether handlers are installed
    _handlers_installed: bool = False
    # Time of last interrupt (for double Ctrl+C detection)
    _last_interrupt_time: float = 0.0


# Global singleton
_state = ShutdownState()


def request_shutdown() -> None:
    """Request graceful shutdown."""
    with _state._lock:
        _state.shutdown_requested = True


def request_interrupt() -> None:
    """Request interrupt (non-fatal, can continue)."""
    with _state._lock:
        _state.interrupt_requested = True


def clear_interrupt() -> None:
    """Clear interrupt flag (for resuming after interrupt)."""
    with _state._lock:
        _state.interrupt_requested = False


def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    with _state._lock:
        return _state.shutdown_requested


def is_interrupt_requested() -> bool:
    """Check if interrupt has been requested."""
    with _state._lock:
        return _state.interrupt_requested


def should_stop() -> bool:
    """Check if operation should stop (shutdown or interrupt)."""
    with _state._lock:
        return _state.shutdown_requested or _state.interrupt_requested


def register_cleanup(callback: Callable[[], None]) -> None:
    """
    Register a cleanup callback to run on shutdown.

    Callbacks are run in reverse order (LIFO).
    """
    with _state._lock:
        _state._cleanup_callbacks.append(callback)


def unregister_cleanup(callback: Callable[[], None]) -> None:
    """Remove a registered cleanup callback."""
    with _state._lock:
        if callback in _state._cleanup_callbacks:
            _state._cleanup_callbacks.remove(callback)


def _run_cleanup() -> None:
    """Run all registered cleanup callbacks."""
    with _state._lock:
        callbacks = list(reversed(_state._cleanup_callbacks))

    for callback in callbacks:
        try:
            callback()
        except Exception:
            pass  # Don't let cleanup errors prevent other cleanups


def _signal_handler(signum: int, frame) -> None:
    """
    Handle SIGINT/SIGTERM.

    For SIGINT (Ctrl+C):
    - First press: interrupt current operation (can continue)
    - Second press within 2 seconds: exit CLI
    - Third press: force exit

    For SIGTERM: always shutdown
    """
    import time

    if signum == signal.SIGTERM:
        # SIGTERM always triggers shutdown
        request_shutdown()
        sys.stderr.write("[Received SIGTERM, shutting down...]\n")
        return

    # SIGINT (Ctrl+C) handling
    current_time = time.time()

    if _state.shutdown_requested:
        # Already shutting down - force exit
        sys.stderr.write("\nForce exit.\n")
        sys.exit(128 + signum)

    if _state.interrupt_requested:
        # Second Ctrl+C within 2 seconds - shutdown
        if current_time - _state._last_interrupt_time < 2.0:
            request_shutdown()
            sys.stderr.write("\n[Exiting...]\n")
            return

    # First Ctrl+C - just interrupt current operation
    with _state._lock:
        _state.interrupt_requested = True
        _state._last_interrupt_time = current_time

    sys.stderr.write("\n[Interrupted - press Ctrl+C again to exit]\n")


def install_signal_handlers() -> None:
    """
    Install signal handlers for graceful shutdown.

    Safe to call multiple times - will only install once.
    """
    if _state._handlers_installed:
        return

    with _state._lock:
        if _state._handlers_installed:
            return

        # Only install on main thread
        if threading.current_thread() is not threading.main_thread():
            return

        try:
            # Save original handlers
            _state._original_handlers[signal.SIGINT] = signal.getsignal(signal.SIGINT)
            _state._original_handlers[signal.SIGTERM] = signal.getsignal(signal.SIGTERM)

            # Install our handlers
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)

            # Register atexit handler for cleanup
            atexit.register(_run_cleanup)

            _state._handlers_installed = True
        except (OSError, ValueError):
            # Can't install handlers (not main thread, or in unusual environment)
            pass


def uninstall_signal_handlers() -> None:
    """Restore original signal handlers."""
    if not _state._handlers_installed:
        return

    with _state._lock:
        if not _state._handlers_installed:
            return

        try:
            for signum, handler in _state._original_handlers.items():
                if handler is not None:
                    signal.signal(signum, handler)

            _state._handlers_installed = False
        except (OSError, ValueError):
            pass


def reset_state() -> None:
    """Reset shutdown state (for testing or restart)."""
    with _state._lock:
        _state.shutdown_requested = False
        _state.interrupt_requested = False
        _state._cleanup_callbacks.clear()


class CancellationToken:
    """
    A token that can be used to coordinate cancellation.

    Usage:
        token = CancellationToken()

        # In producer
        if token.is_cancelled():
            return

        # In consumer
        token.cancel()
    """

    def __init__(self):
        self._cancelled = threading.Event()
        self._reason: Optional[str] = None

    def cancel(self, reason: str = "cancelled") -> None:
        """Request cancellation."""
        self._reason = reason
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancelled.is_set() or is_shutdown_requested()

    @property
    def reason(self) -> Optional[str]:
        """Get the cancellation reason."""
        if is_shutdown_requested():
            return "shutdown"
        return self._reason if self._cancelled.is_set() else None

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for cancellation.

        Returns True if cancelled, False if timeout expired.
        """
        return self._cancelled.wait(timeout)

    def reset(self) -> None:
        """Reset the token (for reuse)."""
        self._cancelled.clear()
        self._reason = None


class CancellationScope:
    """
    Context manager for operations that can be cancelled.

    Usage:
        with CancellationScope() as scope:
            for item in items:
                if scope.cancelled:
                    break
                process(item)
    """

    def __init__(self, token: Optional[CancellationToken] = None):
        self._token = token or CancellationToken()
        self._cleanup_callbacks: list[Callable[[], None]] = []

    def __enter__(self) -> 'CancellationScope':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # Run cleanup
        for callback in reversed(self._cleanup_callbacks):
            try:
                callback()
            except Exception:
                pass

        # Don't suppress exceptions
        return False

    @property
    def cancelled(self) -> bool:
        """Check if scope is cancelled."""
        return self._token.is_cancelled()

    def cancel(self, reason: str = "cancelled") -> None:
        """Cancel this scope."""
        self._token.cancel(reason)

    def on_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a cleanup callback for this scope."""
        self._cleanup_callbacks.append(callback)

    def check(self) -> None:
        """
        Check if cancelled and raise if so.

        Raises:
            CancelledException: If scope is cancelled
        """
        if self.cancelled:
            raise CancelledException(self._token.reason or "cancelled")


class CancelledException(Exception):
    """Raised when an operation is cancelled."""
    pass
