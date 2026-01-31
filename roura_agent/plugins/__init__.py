"""
Roura Agent Plugin System - Sandboxed tools and MCP integration.

Features:
- Plugin discovery and loading
- Sandboxed execution environment
- Permission management
- MCP (Model Context Protocol) server support
- Structured logging

© Roura.io
"""
from __future__ import annotations

# New sandboxed plugin system
from .base import Plugin as BasePlugin
from .base import PluginMetadata as BasePluginMetadata
from .base import PluginStatus, PluginType, ToolDefinition, ToolPlugin
from .loader import PluginLoader, discover_plugins
from .permissions import Permission, PermissionSet, PermissionManager
from .sandbox import Sandbox, SandboxConfig, SandboxResult
from .registry import PluginRegistry, get_plugin_registry, initialize_plugins

# Legacy plugin manager API (backward compatible)
from .manager import (
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

__all__ = [
    # Legacy API (backward compatible)
    "Plugin",
    "PluginMetadata",
    "PluginState",
    "PluginContext",
    "PluginManager",
    "LoadedPlugin",
    "HookType",
    "HookResult",
    "plugin",
    "get_plugin_manager",
    "reset_plugin_manager",
    # New sandboxed plugin system
    "BasePlugin",
    "BasePluginMetadata",
    "PluginStatus",
    "PluginType",
    "ToolDefinition",
    "ToolPlugin",
    "PluginLoader",
    "discover_plugins",
    "Permission",
    "PermissionSet",
    "PermissionManager",
    "Sandbox",
    "SandboxConfig",
    "SandboxResult",
    "PluginRegistry",
    "get_plugin_registry",
    "initialize_plugins",
]
