"""
Roura Agent Plugin System - Extensible plugin architecture.

Provides:
- Plugin discovery and loading
- Hook system for extending functionality
- Plugin lifecycle management
- Tool registration from plugins

© Roura.io
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from .tools.base import Tool, ToolRegistry, registry as global_registry

logger = logging.getLogger(__name__)

T = TypeVar('T')


class PluginState(Enum):
    """Plugin lifecycle states."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


class HookType(Enum):
    """Available hook points in the agent lifecycle."""
    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    # Message processing
    PRE_PROCESS = "pre_process"
    POST_PROCESS = "post_process"
    # Tool execution
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    # LLM interaction
    PRE_LLM_CALL = "pre_llm_call"
    POST_LLM_CALL = "post_llm_call"
    # Session
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    # Custom
    CUSTOM = "custom"


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""
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
    """Result from a hook execution."""
    plugin_name: str
    hook_type: HookType
    success: bool
    data: Any = None
    error: Optional[str] = None


class Plugin(ABC):
    """
    Base class for Roura Agent plugins.

    Plugins can:
    - Register custom tools
    - Hook into the agent lifecycle
    - Provide additional functionality

    Example:
        class MyPlugin(Plugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="my-plugin",
                    version="1.0.0",
                    description="My custom plugin",
                )

            def activate(self, context: PluginContext) -> None:
                # Register tools
                context.register_tool(MyCustomTool())

                # Register hooks
                context.register_hook(
                    HookType.PRE_TOOL_CALL,
                    self.on_pre_tool_call,
                )

            def on_pre_tool_call(self, data: dict) -> dict:
                # Modify or inspect tool call
                return data
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        pass

    @abstractmethod
    def activate(self, context: "PluginContext") -> None:
        """
        Activate the plugin.

        Called when the plugin is loaded and ready to use.
        Register tools, hooks, and initialize resources here.

        Args:
            context: Plugin context for registration
        """
        pass

    def deactivate(self) -> None:
        """
        Deactivate the plugin.

        Called when the plugin is being unloaded.
        Clean up resources here.
        """
        pass

    def configure(self, config: Dict[str, Any]) -> None:
        """
        Configure the plugin with settings.

        Args:
            config: Configuration dictionary
        """
        pass


class PluginContext:
    """
    Context provided to plugins during activation.

    Provides access to:
    - Tool registration
    - Hook registration
    - Plugin manager
    """

    def __init__(
        self,
        manager: "PluginManager",
        registry: ToolRegistry,
    ):
        self._manager = manager
        self._registry = registry
        self._registered_tools: List[str] = []
        self._registered_hooks: List[tuple[HookType, Callable]] = []

    def register_tool(self, tool: Tool) -> None:
        """
        Register a tool from the plugin.

        Args:
            tool: Tool instance to register
        """
        self._registry.register(tool)
        self._registered_tools.append(tool.name)
        logger.debug(f"Plugin registered tool: {tool.name}")

    def register_hook(
        self,
        hook_type: HookType,
        callback: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        Register a hook callback.

        Args:
            hook_type: Type of hook to register
            callback: Function to call when hook fires
        """
        self._manager.register_hook(hook_type, callback)
        self._registered_hooks.append((hook_type, callback))
        logger.debug(f"Plugin registered hook: {hook_type.value}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._manager.get_plugin_config(key, default)

    @property
    def tools_registered(self) -> List[str]:
        """Get list of registered tool names."""
        return self._registered_tools.copy()

    @property
    def hooks_registered(self) -> List[tuple[HookType, Callable]]:
        """Get list of registered hooks."""
        return self._registered_hooks.copy()


@dataclass
class LoadedPlugin:
    """A loaded plugin instance."""
    plugin: Plugin
    metadata: PluginMetadata
    state: PluginState
    context: Optional[PluginContext] = None
    error: Optional[str] = None


class PluginManager:
    """
    Central manager for all plugins.

    Handles:
    - Plugin discovery
    - Plugin loading and activation
    - Hook management
    - Plugin configuration

    Example:
        manager = PluginManager()
        manager.discover_plugins()
        manager.load_all()
        manager.activate_all()

        # Execute hooks
        data = manager.execute_hook(HookType.PRE_TOOL_CALL, {"tool": "fs.read"})
    """

    # Standard plugin directories
    PLUGIN_DIRS = [
        Path.home() / ".config" / "roura" / "plugins",
        Path.cwd() / ".roura" / "plugins",
    ]

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        plugin_dirs: Optional[List[Path]] = None,
    ):
        self._registry = registry or global_registry
        self._plugin_dirs = plugin_dirs or self.PLUGIN_DIRS
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._hooks: Dict[HookType, List[Callable]] = {ht: [] for ht in HookType}
        self._config: Dict[str, Any] = {}

    @property
    def plugins(self) -> Dict[str, LoadedPlugin]:
        """Get all loaded plugins."""
        return self._plugins.copy()

    @property
    def active_plugins(self) -> List[str]:
        """Get names of active plugins."""
        return [
            name for name, lp in self._plugins.items()
            if lp.state == PluginState.ACTIVATED
        ]

    def discover_plugins(self) -> List[Path]:
        """
        Discover plugin files in standard directories.

        Returns:
            List of discovered plugin paths
        """
        discovered = []

        for plugin_dir in self._plugin_dirs:
            if not plugin_dir.exists():
                continue

            # Look for Python files
            for py_file in plugin_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                discovered.append(py_file)
                logger.debug(f"Discovered plugin file: {py_file}")

            # Look for plugin packages (directories with __init__.py)
            for subdir in plugin_dir.iterdir():
                if subdir.is_dir() and (subdir / "__init__.py").exists():
                    discovered.append(subdir)
                    logger.debug(f"Discovered plugin package: {subdir}")

        return discovered

    def load_plugin_from_file(self, path: Path) -> Optional[LoadedPlugin]:
        """
        Load a plugin from a file path.

        Args:
            path: Path to plugin file or package

        Returns:
            LoadedPlugin or None if loading failed
        """
        try:
            # Generate module name
            module_name = f"roura_plugin_{path.stem}"

            # Load module
            if path.is_file():
                spec = importlib.util.spec_from_file_location(module_name, path)
            else:
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    path / "__init__.py",
                )

            if spec is None or spec.loader is None:
                logger.warning(f"Could not load plugin spec: {path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find Plugin subclass
            plugin_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                ):
                    plugin_class = obj
                    break

            if plugin_class is None:
                logger.warning(f"No Plugin subclass found in: {path}")
                return None

            # Instantiate plugin
            plugin = plugin_class()
            metadata = plugin.metadata

            loaded = LoadedPlugin(
                plugin=plugin,
                metadata=metadata,
                state=PluginState.LOADED,
            )

            self._plugins[metadata.name] = loaded
            logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")

            return loaded

        except Exception as e:
            logger.error(f"Failed to load plugin from {path}: {e}")
            return LoadedPlugin(
                plugin=None,  # type: ignore
                metadata=PluginMetadata(name=path.stem, version="unknown"),
                state=PluginState.ERROR,
                error=str(e),
            )

    def load_plugin_class(self, plugin_class: Type[Plugin]) -> LoadedPlugin:
        """
        Load a plugin from a class.

        Args:
            plugin_class: Plugin class to instantiate

        Returns:
            LoadedPlugin instance
        """
        try:
            plugin = plugin_class()
            metadata = plugin.metadata

            loaded = LoadedPlugin(
                plugin=plugin,
                metadata=metadata,
                state=PluginState.LOADED,
            )

            self._plugins[metadata.name] = loaded
            logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")

            return loaded

        except Exception as e:
            logger.error(f"Failed to load plugin class: {e}")
            return LoadedPlugin(
                plugin=None,  # type: ignore
                metadata=PluginMetadata(name=plugin_class.__name__, version="unknown"),
                state=PluginState.ERROR,
                error=str(e),
            )

    def load_all(self) -> int:
        """
        Discover and load all plugins.

        Returns:
            Number of successfully loaded plugins
        """
        paths = self.discover_plugins()
        loaded = 0

        for path in paths:
            result = self.load_plugin_from_file(path)
            if result and result.state == PluginState.LOADED:
                loaded += 1

        return loaded

    def activate(self, name: str) -> bool:
        """
        Activate a loaded plugin.

        Args:
            name: Plugin name

        Returns:
            True if activation succeeded
        """
        if name not in self._plugins:
            logger.error(f"Plugin not found: {name}")
            return False

        loaded = self._plugins[name]

        if loaded.state != PluginState.LOADED:
            logger.warning(f"Plugin {name} is not in LOADED state: {loaded.state}")
            return False

        try:
            # Create context
            context = PluginContext(self, self._registry)
            loaded.context = context

            # Apply configuration
            plugin_config = self._config.get(name, {})
            if plugin_config:
                loaded.plugin.configure(plugin_config)

            # Activate
            loaded.plugin.activate(context)
            loaded.state = PluginState.ACTIVATED

            logger.info(f"Activated plugin: {name}")
            return True

        except Exception as e:
            loaded.state = PluginState.ERROR
            loaded.error = str(e)
            logger.error(f"Failed to activate plugin {name}: {e}")
            return False

    def deactivate(self, name: str) -> bool:
        """
        Deactivate an active plugin.

        Args:
            name: Plugin name

        Returns:
            True if deactivation succeeded
        """
        if name not in self._plugins:
            return False

        loaded = self._plugins[name]

        if loaded.state != PluginState.ACTIVATED:
            return False

        try:
            loaded.plugin.deactivate()

            # Unregister hooks
            if loaded.context:
                for hook_type, callback in loaded.context.hooks_registered:
                    if callback in self._hooks[hook_type]:
                        self._hooks[hook_type].remove(callback)

            loaded.state = PluginState.DEACTIVATED
            logger.info(f"Deactivated plugin: {name}")
            return True

        except Exception as e:
            logger.error(f"Error deactivating plugin {name}: {e}")
            return False

    def activate_all(self) -> int:
        """
        Activate all loaded plugins.

        Returns:
            Number of successfully activated plugins
        """
        activated = 0

        for name, loaded in self._plugins.items():
            if loaded.state == PluginState.LOADED:
                if self.activate(name):
                    activated += 1

        return activated

    def register_hook(
        self,
        hook_type: HookType,
        callback: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """Register a hook callback."""
        self._hooks[hook_type].append(callback)

    def execute_hook(
        self,
        hook_type: HookType,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute all callbacks for a hook type.

        Args:
            hook_type: Type of hook to execute
            data: Data to pass through callbacks

        Returns:
            Modified data after all callbacks
        """
        for callback in self._hooks[hook_type]:
            try:
                result = callback(data)
                if result is not None:
                    data = result
            except Exception as e:
                logger.error(f"Hook callback error: {e}")

        return data

    def execute_hook_all(
        self,
        hook_type: HookType,
        data: Dict[str, Any],
    ) -> List[HookResult]:
        """
        Execute all callbacks and collect results.

        Args:
            hook_type: Type of hook to execute
            data: Data to pass to callbacks

        Returns:
            List of HookResult from each callback
        """
        results = []

        for callback in self._hooks[hook_type]:
            try:
                result_data = callback(data)
                results.append(HookResult(
                    plugin_name=getattr(callback, "__self__", "unknown").__class__.__name__,
                    hook_type=hook_type,
                    success=True,
                    data=result_data,
                ))
            except Exception as e:
                results.append(HookResult(
                    plugin_name=getattr(callback, "__self__", "unknown").__class__.__name__,
                    hook_type=hook_type,
                    success=False,
                    error=str(e),
                ))

        return results

    def set_plugin_config(self, name: str, config: Dict[str, Any]) -> None:
        """Set configuration for a plugin."""
        self._config[name] = config

    def get_plugin_config(self, key: str, default: Any = None) -> Any:
        """Get plugin configuration value."""
        parts = key.split(".", 1)
        if len(parts) == 2:
            plugin_name, config_key = parts
            return self._config.get(plugin_name, {}).get(config_key, default)
        return default

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def list_tools(self) -> List[str]:
        """List all tools registered by plugins."""
        tools = []
        for loaded in self._plugins.values():
            if loaded.context:
                tools.extend(loaded.context.tools_registered)
        return tools


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def reset_plugin_manager() -> None:
    """Reset the global plugin manager."""
    global _plugin_manager
    _plugin_manager = None


# Decorator for creating simple plugins
def plugin(
    name: str,
    version: str = "1.0.0",
    description: str = "",
    **kwargs,
):
    """
    Decorator to create a plugin from a function.

    Example:
        @plugin("my-plugin", version="1.0.0")
        def my_plugin(context: PluginContext):
            context.register_tool(MyTool())
    """
    def decorator(func: Callable[[PluginContext], None]) -> Type[Plugin]:
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

        return DecoratedPlugin

    return decorator
