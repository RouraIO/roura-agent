"""
Roura Agent Plugin Loader - Discovery and loading of plugins.

© Roura.io
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Type

from ..logging import get_logger
from .base import Plugin, PluginMetadata, PluginStatus, PluginType

logger = get_logger(__name__)


@dataclass
class PluginDiscoveryResult:
    """Result of plugin discovery."""
    path: Path
    metadata: Optional[PluginMetadata] = None
    plugin_class: Optional[Type[Plugin]] = None
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.metadata is not None and self.plugin_class is not None


def discover_plugins(
    search_paths: Optional[list[Path]] = None,
    include_builtin: bool = True,
) -> list[PluginDiscoveryResult]:
    """
    Discover available plugins.

    Args:
        search_paths: Additional paths to search for plugins
        include_builtin: Include built-in plugins

    Returns:
        List of discovery results
    """
    results: list[PluginDiscoveryResult] = []

    # Default search paths
    paths = [
        Path.home() / ".config" / "roura-agent" / "plugins",
        Path.home() / ".local" / "share" / "roura-agent" / "plugins",
    ]

    if search_paths:
        paths.extend(search_paths)

    # Search each path
    for base_path in paths:
        if not base_path.exists():
            continue

        # Look for plugin directories (with plugin.json)
        for plugin_dir in base_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest_path = plugin_dir / "plugin.json"
            if manifest_path.exists():
                result = _discover_from_manifest(plugin_dir, manifest_path)
                results.append(result)
                continue

            # Look for single-file plugins (*.py with Plugin class)
            for py_file in plugin_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                result = _discover_from_python(py_file)
                if result.is_valid:
                    results.append(result)

    logger.info(f"Discovered {len(results)} plugins")
    return results


def _discover_from_manifest(
    plugin_dir: Path,
    manifest_path: Path,
) -> PluginDiscoveryResult:
    """Discover plugin from manifest file."""
    try:
        data = json.loads(manifest_path.read_text())
        metadata = PluginMetadata.from_dict(data)
        metadata.source_path = plugin_dir

        # Find the plugin class
        entry_point = data.get("entry_point", "plugin.py")
        entry_path = plugin_dir / entry_point

        if not entry_path.exists():
            return PluginDiscoveryResult(
                path=plugin_dir,
                metadata=metadata,
                error=f"Entry point not found: {entry_point}",
            )

        plugin_class = _load_plugin_class(entry_path, data.get("class_name"))
        if plugin_class is None:
            return PluginDiscoveryResult(
                path=plugin_dir,
                metadata=metadata,
                error="No Plugin class found in entry point",
            )

        metadata.compute_checksum()

        return PluginDiscoveryResult(
            path=plugin_dir,
            metadata=metadata,
            plugin_class=plugin_class,
        )

    except json.JSONDecodeError as e:
        return PluginDiscoveryResult(
            path=plugin_dir,
            error=f"Invalid plugin.json: {e}",
        )
    except Exception as e:
        return PluginDiscoveryResult(
            path=plugin_dir,
            error=f"Failed to load plugin: {e}",
        )


def _discover_from_python(py_path: Path) -> PluginDiscoveryResult:
    """Discover plugin from Python file."""
    try:
        plugin_class = _load_plugin_class(py_path)
        if plugin_class is None:
            return PluginDiscoveryResult(
                path=py_path,
                error="No Plugin class found",
            )

        # Create a temporary instance to get metadata
        try:
            instance = plugin_class()
            metadata = instance.metadata
            metadata.source_path = py_path
            metadata.compute_checksum()
        except Exception as e:
            return PluginDiscoveryResult(
                path=py_path,
                error=f"Failed to instantiate plugin: {e}",
            )

        return PluginDiscoveryResult(
            path=py_path,
            metadata=metadata,
            plugin_class=plugin_class,
        )

    except Exception as e:
        return PluginDiscoveryResult(
            path=py_path,
            error=f"Failed to load plugin: {e}",
        )


def _load_plugin_class(
    py_path: Path,
    class_name: Optional[str] = None,
) -> Optional[Type[Plugin]]:
    """Load Plugin class from Python file."""
    try:
        # Create module spec
        module_name = f"roura_plugin_{py_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, py_path)
        if spec is None or spec.loader is None:
            return None

        # Load module
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find Plugin subclass
        if class_name:
            cls = getattr(module, class_name, None)
            if cls and issubclass(cls, Plugin):
                return cls
        else:
            # Find first Plugin subclass
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                ):
                    return obj

        return None

    except Exception as e:
        logger.warning(f"Failed to load plugin from {py_path}: {e}")
        return None


class PluginLoader:
    """
    Loads and manages plugin lifecycle.

    Handles:
    - Loading plugins from discovery results
    - Plugin validation
    - Plugin activation/deactivation
    - Dependency resolution
    """

    def __init__(self):
        self._loaded: dict[str, Plugin] = {}
        self._discovery_cache: dict[str, PluginDiscoveryResult] = {}

    def load(self, discovery_result: PluginDiscoveryResult) -> Optional[Plugin]:
        """
        Load a plugin from discovery result.

        Args:
            discovery_result: Result from plugin discovery

        Returns:
            Loaded plugin instance or None if failed
        """
        if not discovery_result.is_valid:
            logger.warning(f"Cannot load invalid plugin: {discovery_result.error}")
            return None

        metadata = discovery_result.metadata
        plugin_class = discovery_result.plugin_class

        # Check if already loaded
        if metadata.plugin_id in self._loaded:
            logger.debug(f"Plugin {metadata.name} already loaded")
            return self._loaded[metadata.plugin_id]

        try:
            # Instantiate plugin
            plugin = plugin_class()
            plugin._set_status(PluginStatus.LOADED)

            # Cache discovery result
            self._discovery_cache[metadata.plugin_id] = discovery_result

            # Store loaded plugin
            self._loaded[metadata.plugin_id] = plugin
            logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")

            return plugin

        except Exception as e:
            logger.error(f"Failed to load plugin {metadata.name}: {e}")
            return None

    def load_from_path(self, path: Path) -> Optional[Plugin]:
        """Load plugin from file or directory path."""
        if path.is_dir():
            manifest = path / "plugin.json"
            if manifest.exists():
                result = _discover_from_manifest(path, manifest)
            else:
                # Look for plugin.py
                plugin_py = path / "plugin.py"
                if plugin_py.exists():
                    result = _discover_from_python(plugin_py)
                else:
                    logger.warning(f"No plugin found in {path}")
                    return None
        else:
            result = _discover_from_python(path)

        return self.load(result)

    def unload(self, plugin_id: str) -> bool:
        """
        Unload a plugin.

        Args:
            plugin_id: ID of plugin to unload

        Returns:
            True if unloaded successfully
        """
        if plugin_id not in self._loaded:
            return False

        plugin = self._loaded[plugin_id]

        try:
            # Deactivate if active
            if plugin.status == PluginStatus.ACTIVE:
                plugin.deactivate()

            plugin._set_status(PluginStatus.UNLOADED)
            del self._loaded[plugin_id]

            # Clean up module cache
            if plugin_id in self._discovery_cache:
                del self._discovery_cache[plugin_id]

            logger.info(f"Unloaded plugin: {plugin.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin.name}: {e}")
            return False

    def validate(self, plugin_id: str) -> bool:
        """
        Validate a loaded plugin.

        Args:
            plugin_id: ID of plugin to validate

        Returns:
            True if valid
        """
        if plugin_id not in self._loaded:
            return False

        plugin = self._loaded[plugin_id]

        try:
            if plugin.validate():
                plugin._set_status(PluginStatus.VALIDATED)
                return True
            else:
                plugin._set_status(PluginStatus.ERROR, "Validation failed")
                return False
        except Exception as e:
            plugin._set_status(PluginStatus.ERROR, f"Validation error: {e}")
            return False

    def activate(self, plugin_id: str) -> bool:
        """
        Activate a loaded plugin.

        Args:
            plugin_id: ID of plugin to activate

        Returns:
            True if activated successfully
        """
        if plugin_id not in self._loaded:
            return False

        plugin = self._loaded[plugin_id]

        # Validate first if not already validated
        if plugin.status == PluginStatus.LOADED:
            if not self.validate(plugin_id):
                return False

        try:
            if plugin.activate():
                plugin._set_status(PluginStatus.ACTIVE)
                logger.info(f"Activated plugin: {plugin.name}")
                return True
            else:
                return False
        except Exception as e:
            plugin._set_status(PluginStatus.ERROR, f"Activation error: {e}")
            logger.error(f"Failed to activate plugin {plugin.name}: {e}")
            return False

    def deactivate(self, plugin_id: str) -> bool:
        """
        Deactivate an active plugin.

        Args:
            plugin_id: ID of plugin to deactivate

        Returns:
            True if deactivated successfully
        """
        if plugin_id not in self._loaded:
            return False

        plugin = self._loaded[plugin_id]

        if plugin.status != PluginStatus.ACTIVE:
            return True  # Already inactive

        try:
            if plugin.deactivate():
                plugin._set_status(PluginStatus.SUSPENDED)
                logger.info(f"Deactivated plugin: {plugin.name}")
                return True
            else:
                return False
        except Exception as e:
            plugin._set_status(PluginStatus.ERROR, f"Deactivation error: {e}")
            logger.error(f"Failed to deactivate plugin {plugin.name}: {e}")
            return False

    def get(self, plugin_id: str) -> Optional[Plugin]:
        """Get a loaded plugin by ID."""
        return self._loaded.get(plugin_id)

    def get_by_name(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name."""
        for plugin in self._loaded.values():
            if plugin.name == name:
                return plugin
        return None

    def list_loaded(self) -> list[Plugin]:
        """List all loaded plugins."""
        return list(self._loaded.values())

    def list_active(self) -> list[Plugin]:
        """List all active plugins."""
        return [p for p in self._loaded.values() if p.status == PluginStatus.ACTIVE]
