"""
Roura Agent Plugin Registry - Central plugin management.

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ..logging import get_logger
from .base import Plugin, PluginMetadata, PluginStatus, PluginType, ToolDefinition, ToolPlugin
from .loader import PluginLoader, discover_plugins
from .permissions import Permission, PermissionManager, get_permission_manager
from .sandbox import Sandbox, SandboxConfig, SandboxResult

logger = get_logger(__name__)


@dataclass
class ToolExecutionContext:
    """Context for tool execution."""
    plugin_id: str
    tool_name: str
    sandbox_config: Optional[SandboxConfig] = None
    user_approved: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


class PluginRegistry:
    """
    Central registry for plugins and tools.

    Manages:
    - Plugin discovery and loading
    - Tool registration and lookup
    - Sandboxed tool execution
    - Permission checking
    """

    def __init__(
        self,
        permission_manager: Optional[PermissionManager] = None,
        auto_discover: bool = True,
    ):
        self._loader = PluginLoader()
        self._permission_manager = permission_manager or get_permission_manager()
        self._tools: dict[str, ToolDefinition] = {}
        self._tool_plugins: dict[str, str] = {}  # tool_name -> plugin_id
        self._execution_log: list[dict] = []

        if auto_discover:
            self.discover_and_load()

    def discover_and_load(
        self,
        search_paths: Optional[list[Path]] = None,
        auto_activate: bool = False,
    ) -> list[Plugin]:
        """
        Discover and load plugins.

        Args:
            search_paths: Additional paths to search
            auto_activate: Automatically activate discovered plugins

        Returns:
            List of loaded plugins
        """
        results = discover_plugins(search_paths)
        loaded: list[Plugin] = []

        for result in results:
            if not result.is_valid:
                logger.warning(f"Skipping invalid plugin at {result.path}: {result.error}")
                continue

            plugin = self._loader.load(result)
            if plugin:
                loaded.append(plugin)
                if auto_activate:
                    self.activate_plugin(plugin.metadata.plugin_id)

        return loaded

    def load_plugin(self, path: Path) -> Optional[Plugin]:
        """Load a plugin from path."""
        return self._loader.load_from_path(path)

    def activate_plugin(self, plugin_id: str) -> bool:
        """Activate a plugin and register its tools."""
        if not self._loader.activate(plugin_id):
            return False

        plugin = self._loader.get(plugin_id)
        if not plugin:
            return False

        # Register tools from tool plugins
        if isinstance(plugin, ToolPlugin):
            for tool_def in plugin.get_tool_definitions():
                self._register_tool(tool_def, plugin_id)

        return True

    def deactivate_plugin(self, plugin_id: str) -> bool:
        """Deactivate a plugin and unregister its tools."""
        plugin = self._loader.get(plugin_id)
        if not plugin:
            return False

        # Unregister tools
        tools_to_remove = [
            name for name, pid in self._tool_plugins.items()
            if pid == plugin_id
        ]
        for tool_name in tools_to_remove:
            del self._tools[tool_name]
            del self._tool_plugins[tool_name]

        return self._loader.deactivate(plugin_id)

    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin completely."""
        self.deactivate_plugin(plugin_id)
        return self._loader.unload(plugin_id)

    def _register_tool(self, tool_def: ToolDefinition, plugin_id: str) -> None:
        """Register a tool from a plugin."""
        if tool_def.name in self._tools:
            logger.warning(f"Tool {tool_def.name} already registered, overwriting")

        self._tools[tool_def.name] = tool_def
        self._tool_plugins[tool_def.name] = plugin_id
        logger.debug(f"Registered tool: {tool_def.name} from plugin {plugin_id}")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_tools_for_api(self) -> list[dict]:
        """List tools in API-compatible format."""
        return [tool.to_dict() for tool in self._tools.values()]

    def execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        sandbox_config: Optional[SandboxConfig] = None,
        require_approval: bool = True,
    ) -> SandboxResult:
        """
        Execute a tool in a sandboxed environment.

        Args:
            name: Tool name
            args: Tool arguments
            sandbox_config: Optional sandbox configuration
            require_approval: Whether to require user approval

        Returns:
            SandboxResult with execution result
        """
        tool_def = self.get_tool(name)
        if not tool_def:
            return SandboxResult(
                success=False,
                error=f"Tool not found: {name}",
                error_type="ToolNotFoundError",
            )

        plugin_id = self._tool_plugins.get(name)
        if not plugin_id:
            return SandboxResult(
                success=False,
                error=f"Plugin not found for tool: {name}",
                error_type="PluginNotFoundError",
            )

        # Check permissions
        for perm in tool_def.requires_permissions:
            if not self._permission_manager.check_permission(plugin_id, perm):
                if require_approval:
                    return SandboxResult(
                        success=False,
                        error=f"Permission denied: {perm}",
                        error_type="PermissionError",
                    )

        # Create execution context
        context = ToolExecutionContext(
            plugin_id=plugin_id,
            tool_name=name,
            sandbox_config=sandbox_config,
        )

        # Execute in sandbox
        config = sandbox_config or SandboxConfig()
        sandbox = Sandbox(config, plugin_id, self._permission_manager)

        result = sandbox.execute(tool_def.handler, **args)

        # Log execution
        self._log_execution(context, result)

        return result

    async def execute_tool_async(
        self,
        name: str,
        args: dict[str, Any],
        sandbox_config: Optional[SandboxConfig] = None,
        require_approval: bool = True,
    ) -> SandboxResult:
        """Execute a tool asynchronously in a sandbox."""
        tool_def = self.get_tool(name)
        if not tool_def:
            return SandboxResult(
                success=False,
                error=f"Tool not found: {name}",
                error_type="ToolNotFoundError",
            )

        plugin_id = self._tool_plugins.get(name)
        if not plugin_id:
            return SandboxResult(
                success=False,
                error=f"Plugin not found for tool: {name}",
                error_type="PluginNotFoundError",
            )

        # Check permissions
        for perm in tool_def.requires_permissions:
            if not self._permission_manager.check_permission(plugin_id, perm):
                if require_approval:
                    return SandboxResult(
                        success=False,
                        error=f"Permission denied: {perm}",
                        error_type="PermissionError",
                    )

        # Create execution context
        context = ToolExecutionContext(
            plugin_id=plugin_id,
            tool_name=name,
            sandbox_config=sandbox_config,
        )

        # Execute in sandbox
        config = sandbox_config or SandboxConfig()
        sandbox = Sandbox(config, plugin_id, self._permission_manager)

        import asyncio
        if asyncio.iscoroutinefunction(tool_def.handler):
            result = await sandbox.execute_async(tool_def.handler, **args)
        else:
            result = sandbox.execute(tool_def.handler, **args)

        # Log execution
        self._log_execution(context, result)

        return result

    def _log_execution(self, context: ToolExecutionContext, result: SandboxResult) -> None:
        """Log tool execution."""
        entry = {
            "timestamp": context.timestamp.isoformat(),
            "plugin_id": context.plugin_id,
            "tool_name": context.tool_name,
            "success": result.success,
            "execution_time": result.execution_time,
            "error": result.error,
        }
        self._execution_log.append(entry)

        # Keep only last 1000 entries
        if len(self._execution_log) > 1000:
            self._execution_log = self._execution_log[-1000:]

        logger.debug(
            f"Tool execution: {context.tool_name} "
            f"({'success' if result.success else 'failed'}) "
            f"in {result.execution_time:.3f}s"
        )

    def get_execution_log(self, limit: int = 100) -> list[dict]:
        """Get recent tool execution log."""
        return self._execution_log[-limit:]

    # Plugin queries

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """Get a plugin by ID."""
        return self._loader.get(plugin_id)

    def get_plugin_by_name(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._loader.get_by_name(name)

    def list_plugins(self) -> list[Plugin]:
        """List all loaded plugins."""
        return self._loader.list_loaded()

    def list_active_plugins(self) -> list[Plugin]:
        """List all active plugins."""
        return self._loader.list_active()

    def list_plugins_for_api(self) -> list[dict]:
        """List plugins in API-compatible format."""
        return [
            {
                "id": p.metadata.plugin_id,
                "name": p.name,
                "version": p.version,
                "status": p.status.value,
                "description": p.metadata.description,
                "tools": p.metadata.provides_tools,
            }
            for p in self._loader.list_loaded()
        ]

    # Utility methods

    def grant_permission(
        self,
        plugin_id: str,
        permission: str,
        scope: Optional[str] = None,
    ) -> bool:
        """Grant a permission to a plugin."""
        try:
            self._permission_manager.grant_permission(plugin_id, permission, scope=scope)
            return True
        except Exception as e:
            logger.error(f"Failed to grant permission: {e}")
            return False

    def revoke_permission(
        self,
        plugin_id: str,
        permission: str,
        scope: Optional[str] = None,
    ) -> bool:
        """Revoke a permission from a plugin."""
        try:
            self._permission_manager.revoke_permission(plugin_id, permission, scope)
            return True
        except Exception as e:
            logger.error(f"Failed to revoke permission: {e}")
            return False

    def save_state(self, path: Optional[Path] = None) -> None:
        """Save registry state to file."""
        path = path or self._default_state_path()
        state = {
            "loaded_plugins": [
                {
                    "id": p.metadata.plugin_id,
                    "name": p.name,
                    "status": p.status.value,
                    "source": str(p.metadata.source_path) if p.metadata.source_path else None,
                }
                for p in self._loader.list_loaded()
            ],
            "execution_log": self._execution_log[-100:],
        }
        path.write_text(json.dumps(state, indent=2))

    @staticmethod
    def _default_state_path() -> Path:
        """Get default state file path."""
        path = Path.home() / ".config" / "roura-agent" / "plugin_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


# Global registry instance
_registry: Optional[PluginRegistry] = None


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry(auto_discover=False)
    return _registry


def initialize_plugins(
    search_paths: Optional[list[Path]] = None,
    auto_activate: bool = False,
) -> PluginRegistry:
    """Initialize the plugin system."""
    global _registry
    _registry = PluginRegistry(auto_discover=False)
    _registry.discover_and_load(search_paths, auto_activate)
    return _registry
