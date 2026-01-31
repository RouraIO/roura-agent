"""
Roura Agent Plugin Manager - Backward-compatible plugin management.

Provides the legacy plugin API while integrating with the new
sandboxed plugin system.

© Roura.io
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from ..logging import get_logger
from ..tools.base import Tool, ToolRegistry

logger = get_logger(__name__)


class PluginState(str, Enum):
    """Plugin lifecycle state."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


class HookType(str, Enum):
    """Types of lifecycle hooks."""
    # Lifecycle
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Processing
    PRE_PROCESS = "pre_process"
    POST_PROCESS = "post_process"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str = ""
    requires: List[str] = field(default_factory=list)
    provides_tools: List[str] = field(default_factory=list)
    provides_hooks: List[str] = field(default_factory=list)


@dataclass
class HookResult:
    """Result from executing a hook."""
    plugin_name: str
    hook_type: HookType
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PluginContext:
    """
    Context provided to plugins during activation.

    Provides access to tool registration and hook registration.
    """

    def __init__(
        self,
        manager: "PluginManager",
        registry: Optional[ToolRegistry] = None,
    ):
        self._manager = manager
        self._registry = registry or ToolRegistry()
        self._tools_registered: List[str] = []
        self._hooks_registered: List[tuple] = []

    @property
    def tools_registered(self) -> List[str]:
        """List of tool names registered by this plugin."""
        return self._tools_registered

    @property
    def hooks_registered(self) -> List[tuple]:
        """List of (hook_type, callback) registered by this plugin."""
        return self._hooks_registered

    def register_tool(self, tool: Tool) -> None:
        """Register a tool with the registry."""
        self._registry.register(tool)
        self._tools_registered.append(tool.name)
        logger.debug(f"Registered tool: {tool.name}")

    def register_hook(self, hook_type: HookType, callback: Callable) -> None:
        """Register a hook callback."""
        self._manager.register_hook(hook_type, callback)
        self._hooks_registered.append((hook_type, callback))
        logger.debug(f"Registered hook: {hook_type.value}")


class Plugin:
    """
    Base class for plugins (legacy API).

    Plugins must implement:
    - metadata: Property returning PluginMetadata
    - activate(context): Called when plugin is activated
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        raise NotImplementedError

    def activate(self, context: PluginContext) -> None:
        """Activate the plugin."""
        raise NotImplementedError

    def deactivate(self) -> None:
        """Deactivate the plugin."""
        pass

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the plugin."""
        pass


@dataclass
class LoadedPlugin:
    """A loaded plugin instance."""
    plugin: Plugin
    metadata: PluginMetadata
    state: PluginState = PluginState.LOADED
    error: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    context: Optional[PluginContext] = None


class PluginManager:
    """
    Manages plugin lifecycle.

    Handles:
    - Plugin discovery
    - Loading/unloading
    - Activation/deactivation
    - Hook execution
    - Tool registration
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        plugin_dirs: Optional[List[Path]] = None,
    ):
        self._registry = registry or ToolRegistry()
        self._plugin_dirs = plugin_dirs or [
            Path.home() / ".config" / "roura-agent" / "plugins",
        ]
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._hooks: Dict[HookType, List[Callable]] = {ht: [] for ht in HookType}

    @property
    def plugins(self) -> Dict[str, LoadedPlugin]:
        """Get all loaded plugins."""
        return self._plugins

    @property
    def active_plugins(self) -> List[str]:
        """Get names of active plugins."""
        return [
            name for name, lp in self._plugins.items()
            if lp.state == PluginState.ACTIVATED
        ]

    def discover_plugins(self) -> List[Path]:
        """Discover plugin files in plugin directories."""
        paths = []
        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                continue
            for path in plugin_dir.glob("*.py"):
                if not path.name.startswith("_"):
                    paths.append(path)
        return paths

    def load_plugin_class(self, plugin_class: Type[Plugin]) -> LoadedPlugin:
        """Load a plugin from a class."""
        try:
            plugin = plugin_class()
            metadata = plugin.metadata
            loaded = LoadedPlugin(
                plugin=plugin,
                metadata=metadata,
                state=PluginState.LOADED,
            )
            self._plugins[metadata.name] = loaded
            logger.info(f"Loaded plugin: {metadata.name}")
            return loaded
        except Exception as e:
            logger.error(f"Failed to load plugin: {e}")
            raise

    def load_plugin_file(self, path: Path) -> Optional[LoadedPlugin]:
        """Load a plugin from a Python file."""
        try:
            module_name = f"roura_plugin_{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if not spec or not spec.loader:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find Plugin subclass
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                ):
                    return self.load_plugin_class(obj)

            return None
        except Exception as e:
            logger.error(f"Failed to load plugin from {path}: {e}")
            return None

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def set_plugin_config(self, name: str, config: Dict[str, Any]) -> bool:
        """Set configuration for a plugin."""
        loaded = self._plugins.get(name)
        if not loaded:
            return False
        loaded.config = config
        return True

    def activate(self, name: str) -> bool:
        """Activate a plugin."""
        loaded = self._plugins.get(name)
        if not loaded:
            logger.warning(f"Plugin not found: {name}")
            return False

        if loaded.state == PluginState.ACTIVATED:
            return True

        try:
            # Apply configuration
            if loaded.config:
                loaded.plugin.configure(loaded.config)

            # Create context and activate
            context = PluginContext(self, self._registry)
            loaded.plugin.activate(context)
            loaded.context = context
            loaded.state = PluginState.ACTIVATED
            logger.info(f"Activated plugin: {name}")
            return True
        except Exception as e:
            loaded.state = PluginState.ERROR
            loaded.error = str(e)
            logger.error(f"Failed to activate plugin {name}: {e}")
            return False

    def deactivate(self, name: str) -> bool:
        """Deactivate a plugin."""
        loaded = self._plugins.get(name)
        if not loaded:
            return False

        if loaded.state != PluginState.ACTIVATED:
            return False

        try:
            loaded.plugin.deactivate()
            loaded.state = PluginState.DEACTIVATED
            logger.info(f"Deactivated plugin: {name}")
            return True
        except Exception as e:
            loaded.state = PluginState.ERROR
            loaded.error = str(e)
            logger.error(f"Failed to deactivate plugin {name}: {e}")
            return False

    def activate_all(self) -> int:
        """Activate all loaded plugins. Returns count of activated."""
        count = 0
        for name in list(self._plugins.keys()):
            if self.activate(name):
                count += 1
        return count

    def deactivate_all(self) -> int:
        """Deactivate all active plugins. Returns count of deactivated."""
        count = 0
        for name in self.active_plugins:
            if self.deactivate(name):
                count += 1
        return count

    def list_tools(self) -> List[str]:
        """List all tools registered by plugins."""
        tools = []
        for loaded in self._plugins.values():
            if loaded.context:
                tools.extend(loaded.context.tools_registered)
        return tools

    def register_hook(self, hook_type: HookType, callback: Callable) -> None:
        """Register a hook callback."""
        self._hooks[hook_type].append(callback)

    def execute_hook(
        self,
        hook_type: HookType,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute hooks and return modified data."""
        for callback in self._hooks[hook_type]:
            try:
                result = callback(data)
                if result is not None:
                    data = result
            except Exception as e:
                logger.warning(f"Hook error: {e}")
        return data

    def execute_hook_all(
        self,
        hook_type: HookType,
        data: Dict[str, Any],
    ) -> List[HookResult]:
        """Execute all hooks and return individual results."""
        results = []
        for callback in self._hooks[hook_type]:
            try:
                result = callback(data)
                results.append(HookResult(
                    plugin_name=getattr(callback, "__name__", "unknown"),
                    hook_type=hook_type,
                    success=True,
                    data=result,
                ))
            except Exception as e:
                results.append(HookResult(
                    plugin_name=getattr(callback, "__name__", "unknown"),
                    hook_type=hook_type,
                    success=False,
                    error=str(e),
                ))
        return results


def plugin(
    name: str,
    version: str = "1.0.0",
    description: str = "",
    **kwargs,
) -> Callable:
    """
    Decorator to create a plugin from a function.

    Usage:
        @plugin("my-plugin", version="1.0.0")
        def my_plugin(context: PluginContext):
            context.register_tool(MyTool())
    """

    def decorator(func: Callable) -> Type[Plugin]:
        class DecoratedPlugin(Plugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name=name,
                    version=version,
                    description=description,
                    **kwargs,
                )

            def activate(self, context: PluginContext) -> None:
                func(context)

        DecoratedPlugin.__name__ = func.__name__
        DecoratedPlugin.__doc__ = func.__doc__
        return DecoratedPlugin

    return decorator


# Global plugin manager singleton
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager(
    registry: Optional[ToolRegistry] = None,
) -> PluginManager:
    """Get the global plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager(registry=registry)
    return _plugin_manager


def reset_plugin_manager() -> None:
    """Reset the global plugin manager."""
    global _plugin_manager
    _plugin_manager = None
