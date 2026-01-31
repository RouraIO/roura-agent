"""
Roura Agent Plugin Permissions - Security and access control.

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from ..logging import get_logger

logger = get_logger(__name__)


class Permission(str, Enum):
    """Standard permissions for plugins."""
    # File system
    READ_FILES = "fs:read"
    WRITE_FILES = "fs:write"
    DELETE_FILES = "fs:delete"
    EXECUTE_FILES = "fs:execute"

    # Network
    NETWORK_OUTBOUND = "net:outbound"
    NETWORK_INBOUND = "net:inbound"
    NETWORK_LOCAL = "net:local"

    # Process
    SPAWN_PROCESS = "proc:spawn"
    KILL_PROCESS = "proc:kill"
    SIGNAL_PROCESS = "proc:signal"

    # Environment
    READ_ENV = "env:read"
    WRITE_ENV = "env:write"

    # System
    SYSTEM_INFO = "sys:info"
    SYSTEM_MODIFY = "sys:modify"

    # Roura Agent specific
    AGENT_CONFIG = "agent:config"
    AGENT_MEMORY = "agent:memory"
    AGENT_TOOLS = "agent:tools"
    AGENT_PROVIDERS = "agent:providers"

    # All permissions (dangerous)
    ALL = "*"


@dataclass
class PermissionGrant:
    """A granted permission."""
    permission: str
    granted_at: datetime
    granted_by: str = "user"
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None  # e.g., specific path pattern
    revoked: bool = False

    def is_valid(self) -> bool:
        """Check if grant is still valid."""
        if self.revoked:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    def matches(self, permission: str, scope: Optional[str] = None) -> bool:
        """Check if this grant covers the requested permission."""
        if not self.is_valid():
            return False

        # Exact match
        if self.permission == permission:
            # Check scope if specified
            if scope and self.scope:
                return scope.startswith(self.scope)
            return True

        # Wildcard match
        if self.permission == Permission.ALL:
            return True

        # Category wildcard (e.g., "fs:*" matches "fs:read")
        if self.permission.endswith(":*"):
            category = self.permission[:-2]
            return permission.startswith(f"{category}:")

        return False

    def to_dict(self) -> dict:
        return {
            "permission": self.permission,
            "granted_at": self.granted_at.isoformat(),
            "granted_by": self.granted_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scope": self.scope,
            "revoked": self.revoked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PermissionGrant":
        return cls(
            permission=data["permission"],
            granted_at=datetime.fromisoformat(data["granted_at"]),
            granted_by=data.get("granted_by", "user"),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            scope=data.get("scope"),
            revoked=data.get("revoked", False),
        )


@dataclass
class PermissionSet:
    """Set of permissions for a plugin."""
    plugin_id: str
    grants: list[PermissionGrant] = field(default_factory=list)

    def has_permission(self, permission: str, scope: Optional[str] = None) -> bool:
        """Check if a permission is granted."""
        for grant in self.grants:
            if grant.matches(permission, scope):
                return True
        return False

    def grant(
        self,
        permission: str,
        granted_by: str = "user",
        expires_at: Optional[datetime] = None,
        scope: Optional[str] = None,
    ) -> PermissionGrant:
        """Grant a permission."""
        grant = PermissionGrant(
            permission=permission,
            granted_at=datetime.now(),
            granted_by=granted_by,
            expires_at=expires_at,
            scope=scope,
        )
        self.grants.append(grant)
        logger.info(f"Granted permission {permission} to plugin {self.plugin_id}")
        return grant

    def revoke(self, permission: str, scope: Optional[str] = None) -> int:
        """Revoke a permission. Returns number of grants revoked."""
        count = 0
        for grant in self.grants:
            if grant.permission == permission and grant.scope == scope:
                grant.revoked = True
                count += 1
        if count:
            logger.info(f"Revoked {count} grants of {permission} from plugin {self.plugin_id}")
        return count

    def revoke_all(self) -> int:
        """Revoke all permissions."""
        count = 0
        for grant in self.grants:
            if not grant.revoked:
                grant.revoked = True
                count += 1
        if count:
            logger.info(f"Revoked all ({count}) permissions from plugin {self.plugin_id}")
        return count

    def list_active(self) -> list[PermissionGrant]:
        """List active (non-revoked, non-expired) grants."""
        return [g for g in self.grants if g.is_valid()]

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "grants": [g.to_dict() for g in self.grants],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PermissionSet":
        return cls(
            plugin_id=data["plugin_id"],
            grants=[PermissionGrant.from_dict(g) for g in data.get("grants", [])],
        )


class PermissionManager:
    """
    Manages permissions for all plugins.

    Handles:
    - Permission storage and retrieval
    - Permission checking
    - Audit logging
    - Interactive permission prompts
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._permission_sets: dict[str, PermissionSet] = {}
        self._storage_path = storage_path or self._default_storage_path()
        self._load()

    @staticmethod
    def _default_storage_path() -> Path:
        """Get default storage path."""
        path = Path.home() / ".config" / "roura-agent" / "permissions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self) -> None:
        """Load permissions from storage."""
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text())
                for ps_data in data.get("permission_sets", []):
                    ps = PermissionSet.from_dict(ps_data)
                    self._permission_sets[ps.plugin_id] = ps
                logger.debug(f"Loaded {len(self._permission_sets)} permission sets")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load permissions: {e}")

    def _save(self) -> None:
        """Save permissions to storage."""
        data = {
            "permission_sets": [ps.to_dict() for ps in self._permission_sets.values()],
        }
        self._storage_path.write_text(json.dumps(data, indent=2))

    def get_permission_set(self, plugin_id: str) -> PermissionSet:
        """Get or create permission set for a plugin."""
        if plugin_id not in self._permission_sets:
            self._permission_sets[plugin_id] = PermissionSet(plugin_id=plugin_id)
        return self._permission_sets[plugin_id]

    def check_permission(
        self,
        plugin_id: str,
        permission: str,
        scope: Optional[str] = None,
    ) -> bool:
        """Check if a plugin has a permission."""
        ps = self.get_permission_set(plugin_id)
        return ps.has_permission(permission, scope)

    def require_permission(
        self,
        plugin_id: str,
        permission: str,
        scope: Optional[str] = None,
    ) -> bool:
        """
        Require a permission, prompting user if not granted.

        Returns True if permission is granted (existing or new).
        Returns False if user denies permission.
        """
        if self.check_permission(plugin_id, permission, scope):
            return True

        # In non-interactive mode, deny by default
        # TODO: Implement interactive prompt
        logger.warning(
            f"Plugin {plugin_id} requires permission {permission} "
            f"(scope={scope}) which is not granted"
        )
        return False

    def grant_permission(
        self,
        plugin_id: str,
        permission: str,
        granted_by: str = "user",
        expires_at: Optional[datetime] = None,
        scope: Optional[str] = None,
    ) -> PermissionGrant:
        """Grant a permission to a plugin."""
        ps = self.get_permission_set(plugin_id)
        grant = ps.grant(permission, granted_by, expires_at, scope)
        self._save()
        return grant

    def revoke_permission(
        self,
        plugin_id: str,
        permission: str,
        scope: Optional[str] = None,
    ) -> int:
        """Revoke a permission from a plugin."""
        ps = self.get_permission_set(plugin_id)
        count = ps.revoke(permission, scope)
        self._save()
        return count

    def revoke_all_permissions(self, plugin_id: str) -> int:
        """Revoke all permissions from a plugin."""
        ps = self.get_permission_set(plugin_id)
        count = ps.revoke_all()
        self._save()
        return count

    def list_permissions(self, plugin_id: str) -> list[PermissionGrant]:
        """List active permissions for a plugin."""
        ps = self.get_permission_set(plugin_id)
        return ps.list_active()

    def list_all_permissions(self) -> dict[str, list[PermissionGrant]]:
        """List all active permissions for all plugins."""
        return {
            plugin_id: ps.list_active()
            for plugin_id, ps in self._permission_sets.items()
        }

    def audit_log(
        self,
        plugin_id: str,
        permission: str,
        action: str,
        allowed: bool,
        scope: Optional[str] = None,
    ) -> None:
        """Log a permission check for auditing."""
        logger.info(
            f"Permission audit: plugin={plugin_id} permission={permission} "
            f"scope={scope} action={action} allowed={allowed}"
        )


# Global permission manager instance
_permission_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    """Get the global permission manager."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager
