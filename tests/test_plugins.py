"""
Tests for the plugin system.

© Roura.io
"""
import pytest
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List

from roura_agent.plugins import (
    Plugin,
    PluginMetadata,
    PluginState,
    PluginContext,
    PluginManager,
    LoadedPlugin,
    HookType,
    HookResult,
    plugin,
    get_plugin_manager,
    reset_plugin_manager,
)
from roura_agent.tools.base import Tool, ToolResult, RiskLevel, ToolParam, ToolRegistry


# Test fixtures and helpers

@dataclass
class SimpleTestTool(Tool):
    """A simple test tool for plugin testing."""
    name: str = "test.simple"
    description: str = "A simple test tool"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list = field(default_factory=list)

    def execute(self) -> ToolResult:
        return ToolResult(success=True, output={"message": "Hello from test tool"})


class SamplePlugin(Plugin):
    """A test plugin implementation."""

    def __init__(self, name: str = "test-plugin"):
        self._name = name
        self.activated = False
        self.deactivated = False
        self.config = {}

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version="1.0.0",
            description="A test plugin",
            author="Test Author",
        )

    def activate(self, context: PluginContext) -> None:
        self.activated = True
        context.register_tool(SimpleTestTool())

    def deactivate(self) -> None:
        self.deactivated = True

    def configure(self, config: Dict[str, Any]) -> None:
        self.config = config


class HookTestPlugin(Plugin):
    """Plugin that registers hooks for testing."""

    def __init__(self):
        self.hook_calls = []

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="hook-test-plugin",
            version="1.0.0",
            description="Tests hook functionality",
        )

    def activate(self, context: PluginContext) -> None:
        context.register_hook(HookType.PRE_TOOL_CALL, self.on_pre_tool_call)
        context.register_hook(HookType.POST_TOOL_CALL, self.on_post_tool_call)

    def on_pre_tool_call(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.hook_calls.append(("pre_tool_call", data))
        data["modified"] = True
        return data

    def on_post_tool_call(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.hook_calls.append(("post_tool_call", data))
        return data


class TestPluginMetadata:
    """Tests for PluginMetadata."""

    def test_basic_metadata(self):
        """Test creating basic metadata."""
        meta = PluginMetadata(
            name="test",
            version="1.0.0",
        )
        assert meta.name == "test"
        assert meta.version == "1.0.0"
        assert meta.description == ""

    def test_full_metadata(self):
        """Test metadata with all fields."""
        meta = PluginMetadata(
            name="full-plugin",
            version="2.0.0",
            description="A full plugin",
            author="John Doe",
            homepage="https://example.com",
            requires=["dep1", "dep2"],
            provides_tools=["tool1", "tool2"],
            provides_hooks=["hook1"],
        )
        assert meta.author == "John Doe"
        assert len(meta.requires) == 2
        assert len(meta.provides_tools) == 2


class TestPluginState:
    """Tests for PluginState enum."""

    def test_all_states_exist(self):
        """Test all expected states exist."""
        assert PluginState.DISCOVERED
        assert PluginState.LOADED
        assert PluginState.ACTIVATED
        assert PluginState.DEACTIVATED
        assert PluginState.ERROR


class TestHookType:
    """Tests for HookType enum."""

    def test_lifecycle_hooks(self):
        """Test lifecycle hook types exist."""
        assert HookType.AGENT_START
        assert HookType.AGENT_STOP
        assert HookType.SESSION_START
        assert HookType.SESSION_END

    def test_processing_hooks(self):
        """Test processing hook types exist."""
        assert HookType.PRE_PROCESS
        assert HookType.POST_PROCESS
        assert HookType.PRE_TOOL_CALL
        assert HookType.POST_TOOL_CALL
        assert HookType.PRE_LLM_CALL
        assert HookType.POST_LLM_CALL


class TestPluginContext:
    """Tests for PluginContext."""

    def test_register_tool(self):
        """Test registering a tool through context."""
        registry = ToolRegistry()
        manager = PluginManager(registry=registry)
        context = PluginContext(manager, registry)

        tool = SimpleTestTool()
        context.register_tool(tool)

        assert "test.simple" in context.tools_registered
        assert registry.get("test.simple") is tool

    def test_register_hook(self):
        """Test registering a hook through context."""
        registry = ToolRegistry()
        manager = PluginManager(registry=registry)
        context = PluginContext(manager, registry)

        def callback(data):
            return data

        context.register_hook(HookType.PRE_TOOL_CALL, callback)

        hooks = context.hooks_registered
        assert len(hooks) == 1
        assert hooks[0][0] == HookType.PRE_TOOL_CALL


class TestPluginManager:
    """Tests for PluginManager."""

    def test_create_manager(self):
        """Test creating plugin manager."""
        manager = PluginManager()
        assert manager.plugins == {}
        assert manager.active_plugins == []

    def test_load_plugin_class(self):
        """Test loading a plugin from class."""
        manager = PluginManager()
        loaded = manager.load_plugin_class(SamplePlugin)

        assert loaded.state == PluginState.LOADED
        assert loaded.metadata.name == "test-plugin"
        assert "test-plugin" in manager.plugins

    def test_activate_plugin(self):
        """Test activating a loaded plugin."""
        registry = ToolRegistry()
        manager = PluginManager(registry=registry)

        manager.load_plugin_class(SamplePlugin)
        success = manager.activate("test-plugin")

        assert success
        loaded = manager.get_plugin("test-plugin")
        assert loaded.state == PluginState.ACTIVATED
        assert loaded.plugin.activated
        assert "test.simple" in manager.list_tools()

    def test_deactivate_plugin(self):
        """Test deactivating an active plugin."""
        manager = PluginManager()

        manager.load_plugin_class(SamplePlugin)
        manager.activate("test-plugin")
        success = manager.deactivate("test-plugin")

        assert success
        loaded = manager.get_plugin("test-plugin")
        assert loaded.state == PluginState.DEACTIVATED
        assert loaded.plugin.deactivated

    def test_activate_nonexistent(self):
        """Test activating nonexistent plugin fails."""
        manager = PluginManager()
        success = manager.activate("nonexistent")
        assert not success

    def test_deactivate_not_active(self):
        """Test deactivating non-active plugin fails."""
        manager = PluginManager()
        manager.load_plugin_class(SamplePlugin)
        success = manager.deactivate("test-plugin")
        assert not success

    def test_activate_all(self):
        """Test activating all plugins."""
        manager = PluginManager()

        # Load multiple plugins
        class Plugin1(SamplePlugin):
            def __init__(self):
                super().__init__("plugin1")

        class Plugin2(SamplePlugin):
            def __init__(self):
                super().__init__("plugin2")

        manager.load_plugin_class(Plugin1)
        manager.load_plugin_class(Plugin2)

        count = manager.activate_all()
        assert count == 2
        assert len(manager.active_plugins) == 2

    def test_plugin_config(self):
        """Test plugin configuration."""
        manager = PluginManager()
        manager.load_plugin_class(SamplePlugin)

        manager.set_plugin_config("test-plugin", {"key": "value"})
        manager.activate("test-plugin")

        loaded = manager.get_plugin("test-plugin")
        assert loaded.plugin.config == {"key": "value"}


class TestHookExecution:
    """Tests for hook execution."""

    def test_execute_hook(self):
        """Test executing a hook."""
        manager = PluginManager()
        manager.load_plugin_class(HookTestPlugin)
        manager.activate("hook-test-plugin")

        data = {"tool": "test"}
        result = manager.execute_hook(HookType.PRE_TOOL_CALL, data)

        assert result.get("modified") is True
        loaded = manager.get_plugin("hook-test-plugin")
        assert len(loaded.plugin.hook_calls) == 1

    def test_hook_chain(self):
        """Test multiple hooks in chain."""
        manager = PluginManager()

        results = []

        def hook1(data):
            results.append("hook1")
            data["hook1"] = True
            return data

        def hook2(data):
            results.append("hook2")
            data["hook2"] = True
            return data

        manager.register_hook(HookType.PRE_TOOL_CALL, hook1)
        manager.register_hook(HookType.PRE_TOOL_CALL, hook2)

        data = manager.execute_hook(HookType.PRE_TOOL_CALL, {})

        assert results == ["hook1", "hook2"]
        assert data["hook1"] is True
        assert data["hook2"] is True

    def test_execute_hook_all(self):
        """Test execute_hook_all returns all results."""
        manager = PluginManager()

        def hook1(data):
            return {"result": "from hook1"}

        def hook2(data):
            raise ValueError("Hook error")

        manager.register_hook(HookType.POST_TOOL_CALL, hook1)
        manager.register_hook(HookType.POST_TOOL_CALL, hook2)

        results = manager.execute_hook_all(HookType.POST_TOOL_CALL, {})

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert "Hook error" in results[1].error


class TestPluginDecorator:
    """Tests for the @plugin decorator."""

    def test_plugin_decorator(self):
        """Test creating plugin with decorator."""
        @plugin("decorated-plugin", version="1.0.0", description="A decorated plugin")
        def my_plugin(context: PluginContext):
            context.register_tool(SimpleTestTool())

        manager = PluginManager()
        loaded = manager.load_plugin_class(my_plugin)

        assert loaded.metadata.name == "decorated-plugin"
        assert loaded.metadata.version == "1.0.0"
        assert loaded.metadata.description == "A decorated plugin"

    def test_decorator_activation(self):
        """Test decorated plugin activation."""
        tool_registered = []

        @plugin("register-plugin")
        def register_plugin(context: PluginContext):
            tool = SimpleTestTool()
            context.register_tool(tool)
            tool_registered.append(tool.name)

        registry = ToolRegistry()
        manager = PluginManager(registry=registry)
        manager.load_plugin_class(register_plugin)
        manager.activate("register-plugin")

        assert "test.simple" in tool_registered


class TestGlobalPluginManager:
    """Tests for global plugin manager."""

    def test_get_plugin_manager_singleton(self):
        """Test get_plugin_manager returns singleton."""
        reset_plugin_manager()
        m1 = get_plugin_manager()
        m2 = get_plugin_manager()
        assert m1 is m2

    def test_reset_plugin_manager(self):
        """Test reset clears singleton."""
        m1 = get_plugin_manager()
        reset_plugin_manager()
        m2 = get_plugin_manager()
        assert m1 is not m2


class TestPluginDiscovery:
    """Tests for plugin file discovery."""

    def test_discover_in_empty_dir(self, tmp_path):
        """Test discovery with no plugins."""
        manager = PluginManager(plugin_dirs=[tmp_path])
        paths = manager.discover_plugins()
        assert paths == []

    def test_discover_python_files(self, tmp_path):
        """Test discovering .py plugin files."""
        # Create test plugin file
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("""
from roura_agent.plugins import Plugin, PluginMetadata

class MyPlugin(Plugin):
    @property
    def metadata(self):
        return PluginMetadata(name="file-plugin", version="1.0.0")

    def activate(self, context):
        pass
""")

        manager = PluginManager(plugin_dirs=[tmp_path])
        paths = manager.discover_plugins()

        assert len(paths) == 1
        assert paths[0] == plugin_file

    def test_discover_ignores_private(self, tmp_path):
        """Test that files starting with _ are ignored."""
        (tmp_path / "_private.py").write_text("# private")
        (tmp_path / "__init__.py").write_text("# init")

        manager = PluginManager(plugin_dirs=[tmp_path])
        paths = manager.discover_plugins()

        assert len(paths) == 0


class TestHookResult:
    """Tests for HookResult."""

    def test_success_result(self):
        """Test successful hook result."""
        result = HookResult(
            plugin_name="test",
            hook_type=HookType.PRE_TOOL_CALL,
            success=True,
            data={"key": "value"},
        )
        assert result.success
        assert result.error is None

    def test_error_result(self):
        """Test error hook result."""
        result = HookResult(
            plugin_name="test",
            hook_type=HookType.PRE_TOOL_CALL,
            success=False,
            error="Something went wrong",
        )
        assert not result.success
        assert result.error == "Something went wrong"


class TestPluginLifecycle:
    """Integration tests for plugin lifecycle."""

    def test_full_lifecycle(self):
        """Test complete plugin lifecycle."""
        registry = ToolRegistry()
        manager = PluginManager(registry=registry)

        # Load
        loaded = manager.load_plugin_class(SamplePlugin)
        assert loaded.state == PluginState.LOADED
        assert not loaded.plugin.activated

        # Configure
        manager.set_plugin_config("test-plugin", {"setting": "value"})

        # Activate
        manager.activate("test-plugin")
        assert loaded.state == PluginState.ACTIVATED
        assert loaded.plugin.activated
        assert loaded.plugin.config == {"setting": "value"}

        # Verify tool registered
        assert registry.get("test.simple") is not None

        # Deactivate
        manager.deactivate("test-plugin")
        assert loaded.state == PluginState.DEACTIVATED
        assert loaded.plugin.deactivated

    def test_error_handling(self):
        """Test error handling during activation."""
        class FailingPlugin(Plugin):
            @property
            def metadata(self):
                return PluginMetadata(name="failing", version="1.0.0")

            def activate(self, context):
                raise RuntimeError("Activation failed")

        manager = PluginManager()
        manager.load_plugin_class(FailingPlugin)

        success = manager.activate("failing")

        assert not success
        loaded = manager.get_plugin("failing")
        assert loaded.state == PluginState.ERROR
        assert "Activation failed" in loaded.error
