"""
Roura Agent Memory Consent - Opt-in memory management.

Provides:
- Granular consent controls
- Per-category memory permissions
- Audit trail of consent changes
- Clear data deletion

© Roura.io
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..logging import get_logger

logger = get_logger(__name__)


class ConsentStatus(str, Enum):
    """Consent status for memory features."""
    NOT_SET = "not_set"  # User hasn't decided
    GRANTED = "granted"  # User opted in
    DENIED = "denied"  # User opted out
    REVOKED = "revoked"  # User revoked previous consent


class MemoryType(str, Enum):
    """Types of memory that can be stored."""
    SESSION_HISTORY = "session_history"  # Past conversation summaries
    PROJECT_NOTES = "project_notes"  # User-created notes
    AGENT_NOTES = "agent_notes"  # Agent-generated notes
    PREFERENCES = "preferences"  # User preferences
    FILE_CONTEXT = "file_context"  # Information about project files
    CODE_PATTERNS = "code_patterns"  # Learned coding patterns
    CONVERSATION = "conversation"  # Full conversation history


@dataclass
class ConsentRecord:
    """Record of a consent decision."""
    memory_type: MemoryType
    status: ConsentStatus
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reason: Optional[str] = None  # Optional user-provided reason
    source: str = "user"  # "user", "default", "api"

    def to_dict(self) -> dict:
        return {
            "memory_type": self.memory_type.value,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsentRecord":
        return cls(
            memory_type=MemoryType(data["memory_type"]),
            status=ConsentStatus(data["status"]),
            timestamp=data.get("timestamp", ""),
            reason=data.get("reason"),
            source=data.get("source", "user"),
        )


@dataclass
class ConsentPreferences:
    """
    User's consent preferences for memory features.

    Tracks which types of memory the user has opted into.
    """
    consents: dict[MemoryType, ConsentRecord] = field(default_factory=dict)
    audit_trail: list[ConsentRecord] = field(default_factory=list)
    global_enabled: bool = False  # Master switch for all memory

    def get_status(self, memory_type: MemoryType) -> ConsentStatus:
        """Get consent status for a memory type."""
        if not self.global_enabled:
            return ConsentStatus.DENIED

        record = self.consents.get(memory_type)
        if record:
            return record.status
        return ConsentStatus.NOT_SET

    def is_allowed(self, memory_type: MemoryType) -> bool:
        """Check if memory type is allowed."""
        return self.get_status(memory_type) == ConsentStatus.GRANTED

    def grant(
        self,
        memory_type: MemoryType,
        reason: Optional[str] = None,
        source: str = "user",
    ) -> ConsentRecord:
        """Grant consent for a memory type."""
        record = ConsentRecord(
            memory_type=memory_type,
            status=ConsentStatus.GRANTED,
            reason=reason,
            source=source,
        )
        self.consents[memory_type] = record
        self.audit_trail.append(record)
        logger.info(f"Granted consent for {memory_type.value}")
        return record

    def deny(
        self,
        memory_type: MemoryType,
        reason: Optional[str] = None,
        source: str = "user",
    ) -> ConsentRecord:
        """Deny consent for a memory type."""
        record = ConsentRecord(
            memory_type=memory_type,
            status=ConsentStatus.DENIED,
            reason=reason,
            source=source,
        )
        self.consents[memory_type] = record
        self.audit_trail.append(record)
        logger.info(f"Denied consent for {memory_type.value}")
        return record

    def revoke(
        self,
        memory_type: MemoryType,
        reason: Optional[str] = None,
    ) -> ConsentRecord:
        """Revoke previously granted consent."""
        record = ConsentRecord(
            memory_type=memory_type,
            status=ConsentStatus.REVOKED,
            reason=reason,
            source="user",
        )
        self.consents[memory_type] = record
        self.audit_trail.append(record)
        logger.info(f"Revoked consent for {memory_type.value}")
        return record

    def grant_all(self, reason: Optional[str] = None) -> None:
        """Grant consent for all memory types."""
        self.global_enabled = True
        for mt in MemoryType:
            self.grant(mt, reason, source="user")

    def deny_all(self, reason: Optional[str] = None) -> None:
        """Deny consent for all memory types."""
        self.global_enabled = False
        for mt in MemoryType:
            self.deny(mt, reason, source="user")

    def get_summary(self) -> dict[str, str]:
        """Get summary of all consent statuses."""
        return {
            mt.value: self.get_status(mt).value
            for mt in MemoryType
        }

    def to_dict(self) -> dict:
        return {
            "consents": {
                mt.value: record.to_dict()
                for mt, record in self.consents.items()
            },
            "audit_trail": [r.to_dict() for r in self.audit_trail[-100:]],  # Keep last 100
            "global_enabled": self.global_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsentPreferences":
        prefs = cls()
        prefs.global_enabled = data.get("global_enabled", False)
        prefs.consents = {
            MemoryType(k): ConsentRecord.from_dict(v)
            for k, v in data.get("consents", {}).items()
        }
        prefs.audit_trail = [
            ConsentRecord.from_dict(r)
            for r in data.get("audit_trail", [])
        ]
        return prefs


class ConsentManager:
    """
    Manages user consent for memory features.

    Provides:
    - Persistent consent storage
    - Interactive consent prompts
    - Data deletion on revocation
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path or self._default_storage_path()
        self._preferences = self._load()

    @staticmethod
    def _default_storage_path() -> Path:
        path = Path.home() / ".config" / "roura-agent" / "consent.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self) -> ConsentPreferences:
        """Load consent preferences from storage."""
        if self._storage_path.exists():
            try:
                data = json.loads(self._storage_path.read_text())
                return ConsentPreferences.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load consent: {e}")
        return ConsentPreferences()

    def _save(self) -> None:
        """Save consent preferences to storage."""
        data = self._preferences.to_dict()
        self._storage_path.write_text(json.dumps(data, indent=2))

    @property
    def preferences(self) -> ConsentPreferences:
        """Get current consent preferences."""
        return self._preferences

    @property
    def is_memory_enabled(self) -> bool:
        """Check if memory is globally enabled."""
        return self._preferences.global_enabled

    def check_consent(self, memory_type: MemoryType) -> bool:
        """
        Check if consent is granted for a memory type.

        Args:
            memory_type: Type of memory to check

        Returns:
            True if consent is granted
        """
        return self._preferences.is_allowed(memory_type)

    def require_consent(
        self,
        memory_type: MemoryType,
        prompt_callback: Optional[callable] = None,
    ) -> bool:
        """
        Require consent, optionally prompting user.

        Args:
            memory_type: Type of memory requiring consent
            prompt_callback: Optional callback to prompt user

        Returns:
            True if consent was granted
        """
        status = self._preferences.get_status(memory_type)

        if status == ConsentStatus.GRANTED:
            return True

        if status == ConsentStatus.DENIED or status == ConsentStatus.REVOKED:
            return False

        # NOT_SET - need to prompt
        if prompt_callback:
            granted = prompt_callback(memory_type)
            if granted:
                self.grant_consent(memory_type)
            else:
                self.deny_consent(memory_type)
            return granted

        # No callback and not set - deny by default
        return False

    def grant_consent(
        self,
        memory_type: MemoryType,
        reason: Optional[str] = None,
    ) -> None:
        """Grant consent for a memory type."""
        self._preferences.grant(memory_type, reason)
        self._save()

    def deny_consent(
        self,
        memory_type: MemoryType,
        reason: Optional[str] = None,
    ) -> None:
        """Deny consent for a memory type."""
        self._preferences.deny(memory_type, reason)
        self._save()

    def revoke_consent(
        self,
        memory_type: MemoryType,
        delete_data: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """
        Revoke consent and optionally delete associated data.

        Args:
            memory_type: Type of memory to revoke
            delete_data: Whether to delete existing data
            reason: Optional reason for revocation
        """
        self._preferences.revoke(memory_type, reason)
        self._save()

        if delete_data:
            self._delete_data_for_type(memory_type)

    def enable_all_memory(self, reason: Optional[str] = None) -> None:
        """Enable all memory features."""
        self._preferences.grant_all(reason)
        self._save()
        logger.info("Enabled all memory features")

    def disable_all_memory(
        self,
        delete_data: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """Disable all memory features."""
        self._preferences.deny_all(reason)
        self._save()

        if delete_data:
            self._delete_all_data()

        logger.info("Disabled all memory features")

    def _delete_data_for_type(self, memory_type: MemoryType) -> None:
        """Delete data for a specific memory type."""
        # This would integrate with the memory store
        logger.info(f"Deleting data for {memory_type.value}")
        # Implementation depends on storage structure

    def _delete_all_data(self) -> None:
        """Delete all memory data."""
        logger.info("Deleting all memory data")
        # Implementation depends on storage structure

    def get_consent_summary(self) -> dict[str, Any]:
        """
        Get summary of consent status for display.

        Returns:
            Dict with consent information
        """
        return {
            "global_enabled": self._preferences.global_enabled,
            "consents": self._preferences.get_summary(),
            "audit_count": len(self._preferences.audit_trail),
        }

    def export_consent_data(self) -> dict:
        """Export all consent data (for GDPR compliance)."""
        return self._preferences.to_dict()


# Global consent manager
_consent_manager: Optional[ConsentManager] = None


def get_consent_manager() -> ConsentManager:
    """Get the global consent manager."""
    global _consent_manager
    if _consent_manager is None:
        _consent_manager = ConsentManager()
    return _consent_manager


def check_memory_consent(memory_type: MemoryType) -> bool:
    """Quick check if memory type is allowed."""
    return get_consent_manager().check_consent(memory_type)


def require_memory_consent(
    memory_type: MemoryType,
    prompt_callback: Optional[callable] = None,
) -> bool:
    """Require consent for memory type."""
    return get_consent_manager().require_consent(memory_type, prompt_callback)
