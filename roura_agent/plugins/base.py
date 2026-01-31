"""
Roura Agent Plugin Base - Core plugin classes and interfaces.

© Roura.io
"""
from __future__ import annotations

import abc
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from ..logging import get_logger

logger = get_logger(__name__)


class PluginStatus(str, Enum):
    """Plugin lifecycle status."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    VALIDATED = "validated"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ERROR = "error"
    UNLOADED = "unloaded"


class PluginType(str, Enum):
    """Types of plugins."""
    TOOL = "tool"  # Provides callable tools
    PROVIDER = "provider"  # AI provider integration
    FORMATTER = "formatter"  # Output formatting
    HOOK = "hook"  # Lifecycle hooks
    MCP_SERVER = "mcp_server"  # MCP protocol server


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    plugin_type: PluginType = PluginType.TOOL

    # Requirements
    requires_permissions: list[str] = field(default_factory=list)
    requires_python: str = ">=3.10"
    requires_packages: list[str] = field(default_factory=list)

    # Capabilities
    provides_tools: list[str] = field(default_factory=list)
    provides_hooks: list[str] = field(default_factory=list)

    # Runtime info
    plugin_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_path: Optional[Path] = None
    checksum: Optional[str] = None
    loaded_at: Optional[datetime] = None

    def compute_checksum(self) -> str:
        """Compute checksum of plugin source."""
        if self.source_path and self.source_path.exists():
            content = self.source_path.read_bytes()
            self.checksum = hashlib.sha256(content).hexdigest()
        return self.checksum or ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "plugin_type": self.plugin_type.value,
            "requires_permissions": self.requires_permissions,
            "requires_python": self.requires_python,
            "requires_packages": self.requires_packages,
            "provides_tools": self.provides_tools,
            "provides_hooks": self.provides_hooks,
            "plugin_id": self.plugin_id,
            "source_path": str(self.source_path) if self.source_path else None,
            "checksum": self.checksum,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PluginMetadata":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            homepage=data.get("homepage", ""),
            plugin_type=PluginType(data.get("plugin_type", "tool")),
            requires_permissions=data.get("requires_permissions", []),
            requires_python=data.get("requires_python", ">=3.10"),
            requires_packages=data.get("requires_packages", []),
            provides_tools=data.get("provides_tools", []),
            provides_hooks=data.get("provides_hooks", []),
            plugin_id=data.get("plugin_id", str(uuid.uuid4())),
            source_path=Path(data["source_path"]) if data.get("source_path") else None,
            checksum=data.get("checksum"),
            loaded_at=datetime.fromisoformat(data["loaded_at"]) if data.get("loaded_at") else None,
        )


class Plugin(abc.ABC):
    """
    Base class for all plugins.

    Plugins must implement:
    - metadata: Property returning PluginMetadata
    - activate(): Called when plugin is activated
    - deactivate(): Called when plugin is deactivated

    Optional:
    - validate(): Validate plugin can run
    - get_tools(): Return list of callable tools
    - on_event(): Handle plugin events
    """

    def __init__(self):
        self._status = PluginStatus.DISCOVERED
        self._error: Optional[str] = None
        self._context: dict[str, Any] = {}

    @property
    @abc.abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        ...

    @property
    def status(self) -> PluginStatus:
        """Get current status."""
        return self._status

    @property
    def error(self) -> Optional[str]:
        """Get error message if any."""
        return self._error

    @property
    def name(self) -> str:
        """Get plugin name."""
        return self.metadata.name

    @property
    def version(self) -> str:
        """Get plugin version."""
        return self.metadata.version

    def set_context(self, key: str, value: Any) -> None:
        """Set context value."""
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context value."""
        return self._context.get(key, default)

    def validate(self) -> bool:
        """
        Validate plugin can run.

        Override to add custom validation.
        Returns True if valid, False otherwise.
        """
        return True

    @abc.abstractmethod
    def activate(self) -> bool:
        """
        Activate the plugin.

        Returns True if successful.
        """
        ...

    @abc.abstractmethod
    def deactivate(self) -> bool:
        """
        Deactivate the plugin.

        Returns True if successful.
        """
        ...

    def get_tools(self) -> list[Callable]:
        """
        Return list of callable tools provided by this plugin.

        Override to provide tools.
        """
        return []

    def on_event(self, event: str, data: dict[str, Any]) -> None:
        """
        Handle plugin event.

        Override to handle events like:
        - "pre_execute": Before tool execution
        - "post_execute": After tool execution
        - "error": On error
        - "config_changed": Configuration updated
        """
        pass

    def _set_status(self, status: PluginStatus, error: Optional[str] = None) -> None:
        """Set plugin status."""
        self._status = status
        self._error = error
        logger.debug(f"Plugin {self.name} status: {status.value}")


T = TypeVar("T", bound=Plugin)


@dataclass
class ToolDefinition:
    """Definition of a plugin-provided tool."""
    name: str
    description: str
    handler: Callable
    parameters: dict[str, Any] = field(default_factory=dict)
    returns: Optional[str] = None
    requires_permissions: list[str] = field(default_factory=list)
    plugin_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "returns": self.returns,
            "requires_permissions": self.requires_permissions,
        }


class ToolPlugin(Plugin):
    """
    Base class for plugins that provide tools.

    Subclass and implement:
    - _metadata: Set plugin metadata
    - _register_tools(): Register tools with self.register_tool()
    """

    def __init__(self):
        super().__init__()
        self._tools: dict[str, ToolDefinition] = {}
        self._metadata: Optional[PluginMetadata] = None

    @property
    def metadata(self) -> PluginMetadata:
        if not self._metadata:
            raise ValueError("Plugin metadata not set")
        return self._metadata

    def register_tool(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        parameters: Optional[dict[str, Any]] = None,
        returns: Optional[str] = None,
        requires_permissions: Optional[list[str]] = None,
    ) -> None:
        """Register a tool."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters or {},
            returns=returns,
            requires_permissions=requires_permissions or [],
            plugin_id=self.metadata.plugin_id,
        )
        logger.debug(f"Registered tool: {name}")

    def get_tools(self) -> list[Callable]:
        """Return tool handlers."""
        return [t.handler for t in self._tools.values()]

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Return tool definitions."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name."""
        return self._tools.get(name)

    def activate(self) -> bool:
        """Activate and register tools."""
        try:
            self._register_tools()
            self._set_status(PluginStatus.ACTIVE)
            return True
        except Exception as e:
            self._set_status(PluginStatus.ERROR, str(e))
            logger.error(f"Failed to activate plugin {self.name}: {e}")
            return False

    def deactivate(self) -> bool:
        """Deactivate and unregister tools."""
        self._tools.clear()
        self._set_status(PluginStatus.UNLOADED)
        return True

    @abc.abstractmethod
    def _register_tools(self) -> None:
        """Register tools. Called during activation."""
        ...
