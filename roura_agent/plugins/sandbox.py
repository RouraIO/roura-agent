"""
Roura Agent Plugin Sandbox - Isolated execution environment.

Provides sandboxed execution for plugins with:
- Resource limits (CPU, memory, time)
- File system isolation
- Network restrictions
- Environment isolation

© Roura.io
"""
from __future__ import annotations

import os
import resource
import signal
import sys
import tempfile
import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from ..logging import get_logger
from .permissions import Permission, PermissionManager, get_permission_manager

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    # Time limits (seconds)
    max_execution_time: float = 30.0
    max_cpu_time: float = 10.0

    # Memory limits (bytes)
    max_memory: int = 256 * 1024 * 1024  # 256MB
    max_stack_size: int = 8 * 1024 * 1024  # 8MB

    # File system
    allowed_paths: list[Path] = field(default_factory=list)
    temp_dir: Optional[Path] = None
    read_only: bool = False

    # Network
    allow_network: bool = False
    allowed_hosts: list[str] = field(default_factory=list)

    # Environment
    inherit_env: bool = False
    env_whitelist: list[str] = field(default_factory=lambda: ["PATH", "HOME", "USER"])
    extra_env: dict[str, str] = field(default_factory=dict)

    # Process
    allow_subprocess: bool = False
    max_open_files: int = 100

    def to_dict(self) -> dict:
        return {
            "max_execution_time": self.max_execution_time,
            "max_cpu_time": self.max_cpu_time,
            "max_memory": self.max_memory,
            "max_stack_size": self.max_stack_size,
            "allowed_paths": [str(p) for p in self.allowed_paths],
            "temp_dir": str(self.temp_dir) if self.temp_dir else None,
            "read_only": self.read_only,
            "allow_network": self.allow_network,
            "allowed_hosts": self.allowed_hosts,
            "inherit_env": self.inherit_env,
            "env_whitelist": self.env_whitelist,
            "extra_env": self.extra_env,
            "allow_subprocess": self.allow_subprocess,
            "max_open_files": self.max_open_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxConfig":
        return cls(
            max_execution_time=data.get("max_execution_time", 30.0),
            max_cpu_time=data.get("max_cpu_time", 10.0),
            max_memory=data.get("max_memory", 256 * 1024 * 1024),
            max_stack_size=data.get("max_stack_size", 8 * 1024 * 1024),
            allowed_paths=[Path(p) for p in data.get("allowed_paths", [])],
            temp_dir=Path(data["temp_dir"]) if data.get("temp_dir") else None,
            read_only=data.get("read_only", False),
            allow_network=data.get("allow_network", False),
            allowed_hosts=data.get("allowed_hosts", []),
            inherit_env=data.get("inherit_env", False),
            env_whitelist=data.get("env_whitelist", ["PATH", "HOME", "USER"]),
            extra_env=data.get("extra_env", {}),
            allow_subprocess=data.get("allow_subprocess", False),
            max_open_files=data.get("max_open_files", 100),
        )

    @classmethod
    def permissive(cls) -> "SandboxConfig":
        """Create a permissive sandbox config (for trusted plugins)."""
        return cls(
            max_execution_time=300.0,
            max_cpu_time=60.0,
            max_memory=1024 * 1024 * 1024,  # 1GB
            allow_network=True,
            inherit_env=True,
            allow_subprocess=True,
        )

    @classmethod
    def restrictive(cls) -> "SandboxConfig":
        """Create a restrictive sandbox config (for untrusted plugins)."""
        return cls(
            max_execution_time=5.0,
            max_cpu_time=2.0,
            max_memory=64 * 1024 * 1024,  # 64MB
            read_only=True,
            allow_network=False,
            allow_subprocess=False,
        )


class SandboxError(Exception):
    """Error during sandboxed execution."""
    pass


class SandboxTimeoutError(SandboxError):
    """Execution exceeded time limit."""
    pass


class SandboxMemoryError(SandboxError):
    """Execution exceeded memory limit."""
    pass


class SandboxPermissionError(SandboxError):
    """Permission denied in sandbox."""
    pass


@dataclass
class SandboxResult:
    """Result of sandboxed execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    execution_time: float = 0.0
    memory_used: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "error_type": self.error_type,
            "traceback": self.traceback,
            "execution_time": self.execution_time,
            "memory_used": self.memory_used,
        }


class Sandbox:
    """
    Sandboxed execution environment for plugins.

    Provides isolation and resource limits for plugin code execution.
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        plugin_id: Optional[str] = None,
        permission_manager: Optional[PermissionManager] = None,
    ):
        self.config = config or SandboxConfig()
        self.plugin_id = plugin_id
        self._permission_manager = permission_manager or get_permission_manager()
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._original_env: Optional[dict] = None

    def _check_permission(self, permission: str, scope: Optional[str] = None) -> bool:
        """Check if plugin has permission."""
        if not self.plugin_id:
            return True  # No plugin context, allow
        return self._permission_manager.check_permission(
            self.plugin_id, permission, scope
        )

    def _require_permission(self, permission: str, scope: Optional[str] = None) -> None:
        """Require permission, raise if not granted."""
        if not self._check_permission(permission, scope):
            raise SandboxPermissionError(
                f"Permission denied: {permission}" + (f" (scope: {scope})" if scope else "")
            )

    @contextmanager
    def _resource_limits(self):
        """Context manager for setting resource limits."""
        # Save original limits (best effort - some platforms don't support all)
        old_limits = {}
        limit_types = [
            (resource.RLIMIT_CPU, "cpu"),
            (resource.RLIMIT_AS, "as"),
            (resource.RLIMIT_STACK, "stack"),
            (resource.RLIMIT_NOFILE, "nofile"),
        ]

        for limit_type, name in limit_types:
            try:
                old_limits[name] = resource.getrlimit(limit_type)
            except (ValueError, resource.error, OSError):
                pass  # Platform doesn't support this limit

        try:
            # Set new limits (best effort - ignore failures on macOS/etc)
            if self.config.max_cpu_time > 0 and "cpu" in old_limits:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_CPU,
                        (int(self.config.max_cpu_time), int(self.config.max_cpu_time) + 1),
                    )
                except (ValueError, resource.error, OSError):
                    pass  # Can't set this limit on this platform

            if self.config.max_memory > 0 and "as" in old_limits:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (self.config.max_memory, self.config.max_memory),
                    )
                except (ValueError, resource.error, OSError):
                    pass  # Can't lower memory limit below current usage

            if self.config.max_stack_size > 0 and "stack" in old_limits:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_STACK,
                        (self.config.max_stack_size, self.config.max_stack_size),
                    )
                except (ValueError, resource.error, OSError):
                    pass

            if self.config.max_open_files > 0 and "nofile" in old_limits:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_NOFILE,
                        (self.config.max_open_files, self.config.max_open_files),
                    )
                except (ValueError, resource.error, OSError):
                    pass

            yield

        finally:
            # Restore original limits (best effort)
            for limit_type, name in limit_types:
                if name in old_limits:
                    try:
                        resource.setrlimit(limit_type, old_limits[name])
                    except (ValueError, resource.error, OSError):
                        pass

    @contextmanager
    def _environment(self):
        """Context manager for isolated environment."""
        self._original_env = os.environ.copy()

        try:
            if not self.config.inherit_env:
                # Clear environment except whitelisted vars
                for key in list(os.environ.keys()):
                    if key not in self.config.env_whitelist:
                        del os.environ[key]

            # Add extra environment variables
            os.environ.update(self.config.extra_env)

            yield

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(self._original_env)
            self._original_env = None

    @contextmanager
    def _temp_directory(self):
        """Context manager for temporary directory."""
        if self.config.temp_dir:
            yield self.config.temp_dir
        else:
            with tempfile.TemporaryDirectory(prefix="roura_sandbox_") as tmpdir:
                yield Path(tmpdir)

    def _validate_path(self, path: Path) -> bool:
        """Validate a path is allowed."""
        path = path.resolve()

        # Check allowed paths
        for allowed in self.config.allowed_paths:
            try:
                path.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue

        return False

    def execute(
        self,
        func: Callable[..., T],
        *args,
        **kwargs,
    ) -> SandboxResult:
        """
        Execute a function in the sandbox.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            SandboxResult with success/failure and result/error
        """
        import time

        start_time = time.time()
        result_container: dict[str, Any] = {"result": None, "error": None}

        def target():
            try:
                result_container["result"] = func(*args, **kwargs)
            except Exception as e:
                result_container["error"] = e
                result_container["traceback"] = traceback.format_exc()

        # Run in thread with timeout
        thread = threading.Thread(target=target, daemon=True)

        try:
            with self._resource_limits():
                with self._environment():
                    thread.start()
                    thread.join(timeout=self.config.max_execution_time)

                    if thread.is_alive():
                        # Timeout
                        execution_time = time.time() - start_time
                        return SandboxResult(
                            success=False,
                            error=f"Execution timed out after {self.config.max_execution_time}s",
                            error_type="SandboxTimeoutError",
                            execution_time=execution_time,
                        )

        except MemoryError as e:
            return SandboxResult(
                success=False,
                error=str(e) or "Memory limit exceeded",
                error_type="SandboxMemoryError",
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                execution_time=time.time() - start_time,
            )

        execution_time = time.time() - start_time

        if result_container["error"]:
            error = result_container["error"]
            return SandboxResult(
                success=False,
                error=str(error),
                error_type=type(error).__name__,
                traceback=result_container.get("traceback"),
                execution_time=execution_time,
            )

        return SandboxResult(
            success=True,
            result=result_container["result"],
            execution_time=execution_time,
        )

    async def execute_async(
        self,
        func: Callable[..., T],
        *args,
        **kwargs,
    ) -> SandboxResult:
        """
        Execute an async function in the sandbox.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            SandboxResult with success/failure and result/error
        """
        import asyncio
        import time

        start_time = time.time()

        try:
            with self._resource_limits():
                with self._environment():
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=self.config.max_execution_time,
                    )
                    execution_time = time.time() - start_time
                    return SandboxResult(
                        success=True,
                        result=result,
                        execution_time=execution_time,
                    )

        except asyncio.TimeoutError:
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {self.config.max_execution_time}s",
                error_type="SandboxTimeoutError",
                execution_time=time.time() - start_time,
            )
        except MemoryError as e:
            return SandboxResult(
                success=False,
                error=str(e) or "Memory limit exceeded",
                error_type="SandboxMemoryError",
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                execution_time=time.time() - start_time,
            )


class SandboxedFileAccess:
    """
    Sandboxed file access with path validation.

    Wraps file operations to validate paths against allowed paths.
    """

    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox

    def _validate_read(self, path: Path) -> None:
        """Validate read access."""
        self.sandbox._require_permission(Permission.READ_FILES, str(path))
        if not self.sandbox._validate_path(path):
            raise SandboxPermissionError(f"Path not allowed: {path}")

    def _validate_write(self, path: Path) -> None:
        """Validate write access."""
        if self.sandbox.config.read_only:
            raise SandboxPermissionError("Sandbox is read-only")
        self.sandbox._require_permission(Permission.WRITE_FILES, str(path))
        if not self.sandbox._validate_path(path):
            raise SandboxPermissionError(f"Path not allowed: {path}")

    def read_text(self, path: Path) -> str:
        """Read text file."""
        self._validate_read(path)
        return path.read_text()

    def read_bytes(self, path: Path) -> bytes:
        """Read binary file."""
        self._validate_read(path)
        return path.read_bytes()

    def write_text(self, path: Path, content: str) -> None:
        """Write text file."""
        self._validate_write(path)
        path.write_text(content)

    def write_bytes(self, path: Path, content: bytes) -> None:
        """Write binary file."""
        self._validate_write(path)
        path.write_bytes(content)

    def exists(self, path: Path) -> bool:
        """Check if path exists."""
        self._validate_read(path)
        return path.exists()

    def list_dir(self, path: Path) -> list[Path]:
        """List directory contents."""
        self._validate_read(path)
        return list(path.iterdir())
