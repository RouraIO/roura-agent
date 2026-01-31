"""
Tests for the v2 sandboxed plugin system.

Tests permissions, sandbox execution, and structured logging.

© Roura.io
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from roura_agent.plugins.base import (
    PluginStatus,
    PluginType,
    ToolDefinition,
    ToolPlugin,
)
from roura_agent.plugins.base import PluginMetadata as BasePluginMetadata
from roura_agent.plugins.permissions import (
    Permission,
    PermissionGrant,
    PermissionManager,
    PermissionSet,
)
from roura_agent.plugins.sandbox import (
    Sandbox,
    SandboxConfig,
    SandboxResult,
)
from roura_agent.plugins.logging import (
    LogLevel,
    PluginLogAggregator,
    PluginLogEntry,
    PluginLogFilter,
    PluginLogger,
)


# ============================================================================
# Plugin Base Tests (v2)
# ============================================================================


class TestBasePluginMetadata:
    """Tests for v2 PluginMetadata."""

    def test_create_metadata(self):
        """Create basic plugin metadata."""
        meta = BasePluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"
        assert meta.plugin_type == PluginType.TOOL

    def test_metadata_to_dict(self):
        """Serialize metadata to dict."""
        meta = BasePluginMetadata(
            name="test-plugin",
            version="1.0.0",
            requires_permissions=["fs:read"],
            provides_tools=["tool1", "tool2"],
        )
        data = meta.to_dict()
        assert data["name"] == "test-plugin"
        assert data["requires_permissions"] == ["fs:read"]
        assert data["provides_tools"] == ["tool1", "tool2"]

    def test_metadata_from_dict(self):
        """Deserialize metadata from dict."""
        data = {
            "name": "test-plugin",
            "version": "2.0.0",
            "description": "From dict",
            "plugin_type": "provider",
        }
        meta = BasePluginMetadata.from_dict(data)
        assert meta.name == "test-plugin"
        assert meta.version == "2.0.0"
        assert meta.plugin_type == PluginType.PROVIDER

    def test_compute_checksum(self, tmp_path):
        """Compute checksum from source file."""
        plugin_file = tmp_path / "plugin.py"
        plugin_file.write_text("# test plugin\n")

        meta = BasePluginMetadata(
            name="test",
            version="1.0.0",
            source_path=plugin_file,
        )
        checksum = meta.compute_checksum()
        assert checksum
        assert len(checksum) == 64  # SHA256 hex


class TestToolDefinition:
    """Tests for ToolDefinition."""

    def test_create_tool_definition(self):
        """Create a tool definition."""
        def handler(x: int) -> int:
            return x * 2

        tool = ToolDefinition(
            name="double",
            description="Doubles a number",
            handler=handler,
            parameters={"x": {"type": "integer"}},
        )
        assert tool.name == "double"
        assert tool.handler(5) == 10

    def test_tool_to_dict(self):
        """Serialize tool definition."""
        tool = ToolDefinition(
            name="test_tool",
            description="Test",
            handler=lambda: None,
            requires_permissions=["fs:read"],
        )
        data = tool.to_dict()
        assert data["name"] == "test_tool"
        assert data["requires_permissions"] == ["fs:read"]
        assert "handler" not in data  # Handler not serialized


class DummyToolPlugin(ToolPlugin):
    """Dummy tool plugin for testing."""

    def __init__(self):
        super().__init__()
        self._metadata = BasePluginMetadata(
            name="dummy-tool",
            version="1.0.0",
            description="A dummy tool plugin",
            provides_tools=["greet"],
        )

    def _register_tools(self) -> None:
        self.register_tool(
            name="greet",
            handler=lambda name: f"Hello, {name}!",
            description="Greet someone",
            parameters={"name": {"type": "string"}},
        )


class TestToolPlugin:
    """Tests for ToolPlugin."""

    def test_activate_registers_tools(self):
        """Activating plugin registers tools."""
        plugin = DummyToolPlugin()
        assert plugin.status == PluginStatus.DISCOVERED

        plugin.activate()
        assert plugin.status == PluginStatus.ACTIVE

        tools = plugin.get_tool_definitions()
        assert len(tools) == 1
        assert tools[0].name == "greet"

    def test_tool_execution(self):
        """Execute registered tool."""
        plugin = DummyToolPlugin()
        plugin.activate()

        tool = plugin.get_tool("greet")
        assert tool is not None
        result = tool.handler(name="World")
        assert result == "Hello, World!"

    def test_deactivate_clears_tools(self):
        """Deactivating plugin clears tools."""
        plugin = DummyToolPlugin()
        plugin.activate()
        assert len(plugin.get_tools()) == 1

        plugin.deactivate()
        assert len(plugin.get_tools()) == 0


# ============================================================================
# Permission Tests
# ============================================================================


class TestPermissionGrant:
    """Tests for PermissionGrant."""

    def test_create_grant(self):
        """Create a permission grant."""
        grant = PermissionGrant(
            permission="fs:read",
            granted_at=datetime.now(),
        )
        assert grant.permission == "fs:read"
        assert grant.is_valid()

    def test_expired_grant(self):
        """Expired grants are invalid."""
        grant = PermissionGrant(
            permission="fs:read",
            granted_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert not grant.is_valid()

    def test_revoked_grant(self):
        """Revoked grants are invalid."""
        grant = PermissionGrant(
            permission="fs:read",
            granted_at=datetime.now(),
            revoked=True,
        )
        assert not grant.is_valid()

    def test_matches_exact(self):
        """Exact permission matching."""
        grant = PermissionGrant(
            permission="fs:read",
            granted_at=datetime.now(),
        )
        assert grant.matches("fs:read")
        assert not grant.matches("fs:write")

    def test_matches_wildcard(self):
        """Wildcard permission matching."""
        grant = PermissionGrant(
            permission=Permission.ALL,
            granted_at=datetime.now(),
        )
        assert grant.matches("fs:read")
        assert grant.matches("net:outbound")

    def test_matches_scope(self):
        """Scoped permission matching."""
        grant = PermissionGrant(
            permission="fs:read",
            granted_at=datetime.now(),
            scope="/home/user",
        )
        assert grant.matches("fs:read", "/home/user/docs")
        assert not grant.matches("fs:read", "/tmp")


class TestPermissionSet:
    """Tests for PermissionSet."""

    def test_grant_permission(self):
        """Grant a permission."""
        ps = PermissionSet(plugin_id="test")
        ps.grant("fs:read")
        assert ps.has_permission("fs:read")

    def test_revoke_permission(self):
        """Revoke a permission."""
        ps = PermissionSet(plugin_id="test")
        ps.grant("fs:read")
        assert ps.has_permission("fs:read")

        ps.revoke("fs:read")
        assert not ps.has_permission("fs:read")

    def test_revoke_all(self):
        """Revoke all permissions."""
        ps = PermissionSet(plugin_id="test")
        ps.grant("fs:read")
        ps.grant("fs:write")
        ps.grant("net:outbound")

        count = ps.revoke_all()
        assert count == 3
        assert not ps.has_permission("fs:read")

    def test_list_active(self):
        """List active grants."""
        ps = PermissionSet(plugin_id="test")
        ps.grant("fs:read")
        ps.grant("fs:write")
        ps.revoke("fs:write")

        active = ps.list_active()
        assert len(active) == 1
        assert active[0].permission == "fs:read"


class TestPermissionManager:
    """Tests for PermissionManager."""

    def test_check_permission(self, tmp_path):
        """Check permission via manager."""
        manager = PermissionManager(storage_path=tmp_path / "perms.json")
        manager.grant_permission("plugin1", "fs:read")

        assert manager.check_permission("plugin1", "fs:read")
        assert not manager.check_permission("plugin1", "fs:write")
        assert not manager.check_permission("plugin2", "fs:read")

    def test_persistence(self, tmp_path):
        """Permissions persist to storage."""
        path = tmp_path / "perms.json"

        # Create and grant
        manager1 = PermissionManager(storage_path=path)
        manager1.grant_permission("plugin1", "fs:read")

        # Reload and check
        manager2 = PermissionManager(storage_path=path)
        assert manager2.check_permission("plugin1", "fs:read")


# ============================================================================
# Sandbox Tests
# ============================================================================


class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_default_config(self):
        """Default configuration values."""
        config = SandboxConfig()
        assert config.max_execution_time == 30.0
        assert not config.allow_network
        assert not config.allow_subprocess

    def test_permissive_config(self):
        """Permissive configuration."""
        config = SandboxConfig.permissive()
        assert config.max_execution_time == 300.0
        assert config.allow_network
        assert config.allow_subprocess

    def test_restrictive_config(self):
        """Restrictive configuration."""
        config = SandboxConfig.restrictive()
        assert config.max_execution_time == 5.0
        assert config.read_only
        assert not config.allow_network

    def test_to_dict_from_dict(self):
        """Serialization round-trip."""
        config1 = SandboxConfig(
            max_execution_time=60.0,
            allow_network=True,
        )
        data = config1.to_dict()
        config2 = SandboxConfig.from_dict(data)

        assert config2.max_execution_time == 60.0
        assert config2.allow_network


class TestSandbox:
    """Tests for Sandbox execution."""

    def test_execute_success(self):
        """Execute function successfully."""
        sandbox = Sandbox()

        def add(a, b):
            return a + b

        result = sandbox.execute(add, 2, 3)
        assert result.success
        assert result.result == 5
        assert result.execution_time > 0

    def test_execute_exception(self):
        """Handle function exceptions."""
        sandbox = Sandbox()

        def failing():
            raise ValueError("test error")

        result = sandbox.execute(failing)
        assert not result.success
        assert "test error" in result.error
        assert result.error_type == "ValueError"

    def test_execute_timeout(self):
        """Handle execution timeout."""
        config = SandboxConfig(max_execution_time=0.1)
        sandbox = Sandbox(config)

        def slow():
            time.sleep(1)
            return "done"

        result = sandbox.execute(slow)
        assert not result.success
        assert "timed out" in result.error.lower()

    def test_result_to_dict(self):
        """Serialize result to dict."""
        result = SandboxResult(
            success=True,
            result="test",
            execution_time=0.5,
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["result"] == "test"


# ============================================================================
# Logging Tests
# ============================================================================


class TestLogLevel:
    """Tests for LogLevel."""

    def test_from_string(self):
        """Parse level from string."""
        assert LogLevel.from_string("debug") == LogLevel.DEBUG
        assert LogLevel.from_string("ERROR") == LogLevel.ERROR

    def test_numeric_ordering(self):
        """Numeric values maintain ordering."""
        assert LogLevel.DEBUG.numeric() < LogLevel.INFO.numeric()
        assert LogLevel.INFO.numeric() < LogLevel.WARNING.numeric()
        assert LogLevel.WARNING.numeric() < LogLevel.ERROR.numeric()
        assert LogLevel.ERROR.numeric() < LogLevel.CRITICAL.numeric()


class TestPluginLogEntry:
    """Tests for PluginLogEntry."""

    def test_create_entry(self):
        """Create a log entry."""
        entry = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            plugin_id="test-id",
            plugin_name="test-plugin",
            message="Test message",
        )
        assert entry.level == LogLevel.INFO
        assert entry.message == "Test message"

    def test_to_json_from_dict(self):
        """Serialization round-trip."""
        entry1 = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.WARNING,
            plugin_id="test-id",
            plugin_name="test-plugin",
            message="Warning message",
            context={"key": "value"},
        )
        data = json.loads(entry1.to_json())
        entry2 = PluginLogEntry.from_dict(data)

        assert entry2.level == LogLevel.WARNING
        assert entry2.message == "Warning message"
        assert entry2.context == {"key": "value"}

    def test_format(self):
        """Format entry as string."""
        entry = PluginLogEntry(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            level=LogLevel.INFO,
            plugin_id="test-id",
            plugin_name="test-plugin",
            message="Test message",
        )
        formatted = entry.format()
        assert "test-plugin" in formatted
        assert "INFO" in formatted
        assert "Test message" in formatted


class TestPluginLogFilter:
    """Tests for PluginLogFilter."""

    def test_filter_by_level(self):
        """Filter by minimum level."""
        filter = PluginLogFilter(min_level=LogLevel.WARNING)

        debug_entry = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.DEBUG,
            plugin_id="test",
            plugin_name="test",
            message="Debug",
        )
        warning_entry = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.WARNING,
            plugin_id="test",
            plugin_name="test",
            message="Warning",
        )

        assert not filter.matches(debug_entry)
        assert filter.matches(warning_entry)

    def test_filter_by_plugin(self):
        """Filter by plugin ID."""
        filter = PluginLogFilter(plugin_ids=["plugin1"])

        entry1 = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            plugin_id="plugin1",
            plugin_name="Plugin 1",
            message="Test",
        )
        entry2 = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            plugin_id="plugin2",
            plugin_name="Plugin 2",
            message="Test",
        )

        assert filter.matches(entry1)
        assert not filter.matches(entry2)

    def test_filter_by_content(self):
        """Filter by message content."""
        filter = PluginLogFilter(contains="error")

        entry1 = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            plugin_id="test",
            plugin_name="test",
            message="An error occurred",
        )
        entry2 = PluginLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            plugin_id="test",
            plugin_name="test",
            message="Success",
        )

        assert filter.matches(entry1)
        assert not filter.matches(entry2)


class TestPluginLogAggregator:
    """Tests for PluginLogAggregator."""

    def test_add_and_get_entries(self):
        """Add and retrieve entries."""
        aggregator = PluginLogAggregator(max_entries=100)
        logger = aggregator.create_logger("test-id", "test-plugin")

        logger.info("Message 1")
        logger.info("Message 2")
        logger.warning("Warning")

        entries = aggregator.get_entries()
        assert len(entries) == 3

    def test_max_entries_limit(self):
        """Respect max entries limit."""
        aggregator = PluginLogAggregator(max_entries=5)
        logger = aggregator.create_logger("test-id", "test-plugin")

        for i in range(10):
            logger.info(f"Message {i}")

        entries = aggregator.get_entries(limit=100)
        assert len(entries) == 5

    def test_filter_entries(self):
        """Filter entries on retrieval."""
        aggregator = PluginLogAggregator()
        logger1 = aggregator.create_logger("plugin1", "Plugin 1")
        logger2 = aggregator.create_logger("plugin2", "Plugin 2")

        logger1.info("Info 1")
        logger1.error("Error 1")
        logger2.info("Info 2")

        filter = PluginLogFilter(plugin_ids=["plugin1"])
        entries = aggregator.get_entries(filter)
        assert len(entries) == 2

    def test_get_recent_errors(self):
        """Get recent error entries."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test", "test")

        logger.info("Info")
        logger.warning("Warning")
        logger.error("Error")
        logger.critical("Critical")

        errors = aggregator.get_recent_errors()
        assert len(errors) == 2
        assert errors[0].level == LogLevel.ERROR
        assert errors[1].level == LogLevel.CRITICAL

    def test_callback_notification(self):
        """Callbacks receive new entries."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test", "test")

        received = []
        aggregator.register_callback(lambda e: received.append(e))

        logger.info("Test")

        assert len(received) == 1
        assert received[0].message == "Test"

    def test_export_logs(self, tmp_path):
        """Export logs to file."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test", "test")

        logger.info("Message 1")
        logger.info("Message 2")

        export_path = tmp_path / "logs.jsonl"
        count = aggregator.export(export_path)

        assert count == 2
        assert export_path.exists()

        lines = export_path.read_text().strip().split("\n")
        assert len(lines) == 2


class TestPluginLogger:
    """Tests for PluginLogger."""

    def test_log_levels(self):
        """Log at different levels."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test-id", "test-plugin")

        logger.debug("Debug")
        logger.info("Info")
        logger.warning("Warning")
        logger.error("Error")
        logger.critical("Critical")

        entries = aggregator.get_entries()
        assert len(entries) == 5
        assert [e.level for e in entries] == [
            LogLevel.DEBUG,
            LogLevel.INFO,
            LogLevel.WARNING,
            LogLevel.ERROR,
            LogLevel.CRITICAL,
        ]

    def test_log_with_context(self):
        """Log with additional context."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test-id", "test-plugin")

        logger.info("Request processed", context={"request_id": "123", "duration": 0.5})

        entries = aggregator.get_entries()
        assert entries[0].context["request_id"] == "123"
        assert entries[0].context["duration"] == 0.5

    def test_default_context(self):
        """Default context is merged."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test-id", "test-plugin")

        logger.set_context("session_id", "abc123")
        logger.info("Message", context={"extra": "value"})

        entries = aggregator.get_entries()
        assert entries[0].context["session_id"] == "abc123"
        assert entries[0].context["extra"] == "value"

    def test_log_with_exception(self):
        """Log with exception."""
        aggregator = PluginLogAggregator()
        logger = aggregator.create_logger("test-id", "test-plugin")

        try:
            raise ValueError("test error")
        except ValueError as e:
            logger.error("Operation failed", exception=e)

        entries = aggregator.get_entries()
        assert entries[0].exception == "test error"
        assert entries[0].stack_trace is not None
