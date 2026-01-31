"""
Tests for v2.5 Memory features: encryption, consent, project scoping.

© Roura.io
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from roura_agent.memory.encryption import (
    EncryptionKey,
    EncryptedStore,
    generate_key,
    derive_key,
    CRYPTO_AVAILABLE,
)
from roura_agent.memory.consent import (
    ConsentStatus,
    ConsentRecord,
    ConsentPreferences,
    ConsentManager,
    MemoryType,
)
from roura_agent.memory.project import (
    ProjectScope,
    ProjectMemoryEntry,
    ProjectMemory,
)


# ============================================================================
# Encryption Tests
# ============================================================================


class TestEncryptionKey:
    """Tests for EncryptionKey."""

    def test_generate_key(self):
        """Generate random key."""
        key = generate_key()
        assert len(key.key) == 32  # 256 bits
        assert len(key.salt) == 16
        assert key.key_id

    def test_derive_key(self):
        """Derive key from password."""
        key1 = derive_key("test-password")
        key2 = derive_key("test-password", salt=key1.salt)

        # Same password + salt = same key
        assert key1.key == key2.key

    def test_derive_key_different_passwords(self):
        """Different passwords produce different keys."""
        key1 = derive_key("password1")
        key2 = derive_key("password2", salt=key1.salt)

        assert key1.key != key2.key

    def test_key_to_dict(self):
        """Serialize key metadata."""
        key = generate_key()
        data = key.to_dict()

        assert "salt" in data
        assert "key_id" in data
        assert "key" not in data  # Key should not be in serialized data


class TestEncryptedStore:
    """Tests for EncryptedStore."""

    def test_encrypt_decrypt(self):
        """Encrypt and decrypt data."""
        key = generate_key()
        store = EncryptedStore(key)

        original = b"Hello, World!"
        encrypted = store.encrypt(original)
        decrypted = store.decrypt(encrypted)

        assert decrypted == original
        assert encrypted != original

    def test_encrypt_decrypt_json(self):
        """Encrypt and decrypt JSON data."""
        key = generate_key()
        store = EncryptedStore(key)

        data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        encrypted = store.encrypt_json(data)
        decrypted = store.decrypt_json(encrypted)

        assert decrypted == data

    def test_save_load_encrypted(self, tmp_path):
        """Save and load encrypted file."""
        key = generate_key()
        store = EncryptedStore(key)

        data = {"secret": "data", "items": ["a", "b", "c"]}
        file_path = tmp_path / "encrypted.dat"

        store.save_encrypted(file_path, data)
        assert file_path.exists()

        loaded = store.load_encrypted(file_path)
        assert loaded == data

    def test_wrong_key_fails(self, tmp_path):
        """Decryption with wrong key fails."""
        key1 = generate_key()
        key2 = generate_key()

        store1 = EncryptedStore(key1)
        store2 = EncryptedStore(key2)

        data = {"secret": "data"}
        file_path = tmp_path / "encrypted.dat"

        store1.save_encrypted(file_path, data)

        with pytest.raises(Exception):
            store2.load_encrypted(file_path)

    def test_create_with_password(self):
        """Create store with password."""
        store, key = EncryptedStore.create_with_password("my-password")

        data = b"test data"
        encrypted = store.encrypt(data)
        decrypted = store.decrypt(encrypted)

        assert decrypted == data

    def test_keyfile_save_load(self, tmp_path):
        """Save and load keyfile."""
        key = generate_key()
        store = EncryptedStore(key)

        keyfile = tmp_path / "test.key"
        store.save_keyfile(keyfile)
        assert keyfile.exists()

        loaded_store = EncryptedStore.from_keyfile(keyfile)
        assert loaded_store is not None

        # Should be able to decrypt same data
        data = b"test data"
        encrypted = store.encrypt(data)
        decrypted = loaded_store.decrypt(encrypted)
        assert decrypted == data


# ============================================================================
# Consent Tests
# ============================================================================


class TestConsentRecord:
    """Tests for ConsentRecord."""

    def test_create_record(self):
        """Create consent record."""
        record = ConsentRecord(
            memory_type=MemoryType.PROJECT_NOTES,
            status=ConsentStatus.GRANTED,
        )
        assert record.status == ConsentStatus.GRANTED
        assert record.memory_type == MemoryType.PROJECT_NOTES

    def test_to_dict_from_dict(self):
        """Serialize and deserialize record."""
        record1 = ConsentRecord(
            memory_type=MemoryType.SESSION_HISTORY,
            status=ConsentStatus.DENIED,
            reason="Privacy concerns",
        )
        data = record1.to_dict()
        record2 = ConsentRecord.from_dict(data)

        assert record2.memory_type == record1.memory_type
        assert record2.status == record1.status
        assert record2.reason == record1.reason


class TestConsentPreferences:
    """Tests for ConsentPreferences."""

    def test_initial_state(self):
        """Initial state denies access (safe default)."""
        prefs = ConsentPreferences()
        # Global disabled returns DENIED as safe default
        assert prefs.get_status(MemoryType.PROJECT_NOTES) == ConsentStatus.DENIED
        assert not prefs.is_allowed(MemoryType.PROJECT_NOTES)

    def test_grant_consent(self):
        """Grant consent."""
        prefs = ConsentPreferences()
        prefs.global_enabled = True
        prefs.grant(MemoryType.PROJECT_NOTES)

        assert prefs.get_status(MemoryType.PROJECT_NOTES) == ConsentStatus.GRANTED
        assert prefs.is_allowed(MemoryType.PROJECT_NOTES)

    def test_deny_consent(self):
        """Deny consent."""
        prefs = ConsentPreferences()
        prefs.global_enabled = True
        prefs.deny(MemoryType.PROJECT_NOTES)

        assert prefs.get_status(MemoryType.PROJECT_NOTES) == ConsentStatus.DENIED
        assert not prefs.is_allowed(MemoryType.PROJECT_NOTES)

    def test_revoke_consent(self):
        """Revoke previously granted consent."""
        prefs = ConsentPreferences()
        prefs.global_enabled = True
        prefs.grant(MemoryType.PROJECT_NOTES)
        prefs.revoke(MemoryType.PROJECT_NOTES)

        assert prefs.get_status(MemoryType.PROJECT_NOTES) == ConsentStatus.REVOKED
        assert not prefs.is_allowed(MemoryType.PROJECT_NOTES)

    def test_global_disabled(self):
        """Global disabled overrides individual grants."""
        prefs = ConsentPreferences()
        prefs.global_enabled = True
        prefs.grant(MemoryType.PROJECT_NOTES)

        prefs.global_enabled = False
        assert not prefs.is_allowed(MemoryType.PROJECT_NOTES)

    def test_grant_all(self):
        """Grant all memory types."""
        prefs = ConsentPreferences()
        prefs.grant_all()

        assert prefs.global_enabled
        for mt in MemoryType:
            assert prefs.is_allowed(mt)

    def test_deny_all(self):
        """Deny all memory types."""
        prefs = ConsentPreferences()
        prefs.grant_all()
        prefs.deny_all()

        assert not prefs.global_enabled
        for mt in MemoryType:
            assert not prefs.is_allowed(mt)

    def test_audit_trail(self):
        """Audit trail records changes."""
        prefs = ConsentPreferences()
        prefs.grant(MemoryType.PROJECT_NOTES)
        prefs.deny(MemoryType.SESSION_HISTORY)
        prefs.revoke(MemoryType.PROJECT_NOTES)

        assert len(prefs.audit_trail) == 3
        assert prefs.audit_trail[0].status == ConsentStatus.GRANTED
        assert prefs.audit_trail[1].status == ConsentStatus.DENIED
        assert prefs.audit_trail[2].status == ConsentStatus.REVOKED


class TestConsentManager:
    """Tests for ConsentManager."""

    def test_check_consent(self, tmp_path):
        """Check consent status."""
        manager = ConsentManager(storage_path=tmp_path / "consent.json")
        manager._preferences.global_enabled = True
        manager.grant_consent(MemoryType.PROJECT_NOTES)

        assert manager.check_consent(MemoryType.PROJECT_NOTES)
        assert not manager.check_consent(MemoryType.SESSION_HISTORY)

    def test_persistence(self, tmp_path):
        """Consent persists to storage."""
        path = tmp_path / "consent.json"

        manager1 = ConsentManager(storage_path=path)
        manager1._preferences.global_enabled = True
        manager1.grant_consent(MemoryType.PROJECT_NOTES)

        manager2 = ConsentManager(storage_path=path)
        assert manager2.check_consent(MemoryType.PROJECT_NOTES)

    def test_enable_disable_all(self, tmp_path):
        """Enable and disable all memory."""
        manager = ConsentManager(storage_path=tmp_path / "consent.json")

        manager.enable_all_memory()
        assert manager.is_memory_enabled
        assert manager.check_consent(MemoryType.PROJECT_NOTES)

        manager.disable_all_memory()
        assert not manager.is_memory_enabled
        assert not manager.check_consent(MemoryType.PROJECT_NOTES)

    def test_consent_summary(self, tmp_path):
        """Get consent summary."""
        manager = ConsentManager(storage_path=tmp_path / "consent.json")
        manager._preferences.global_enabled = True
        manager.grant_consent(MemoryType.PROJECT_NOTES)

        summary = manager.get_consent_summary()
        assert "global_enabled" in summary
        assert "consents" in summary


# ============================================================================
# Project Scoping Tests
# ============================================================================


class TestProjectScope:
    """Tests for ProjectScope."""

    def test_create_scope(self, tmp_path):
        """Create project scope."""
        scope = ProjectScope(root_path=tmp_path)
        assert scope.root_path == tmp_path
        assert scope.name == tmp_path.name
        assert scope.project_id

    def test_unique_id(self, tmp_path):
        """Different paths have different IDs."""
        dir1 = tmp_path / "project1"
        dir2 = tmp_path / "project2"
        dir1.mkdir()
        dir2.mkdir()

        scope1 = ProjectScope(root_path=dir1)
        scope2 = ProjectScope(root_path=dir2)

        assert scope1.project_id != scope2.project_id

    def test_memory_paths(self, tmp_path):
        """Memory paths are correct."""
        scope = ProjectScope(root_path=tmp_path)
        assert scope.memory_dir == tmp_path / ".roura"
        assert scope.memory_file == tmp_path / ".roura" / "memory.json"

    def test_detect_git_project(self, tmp_path):
        """Detect project with .git directory."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        scope = ProjectScope.detect(project_dir)
        assert scope is not None
        assert scope.root_path == project_dir

    def test_detect_pyproject(self, tmp_path):
        """Detect project with pyproject.toml."""
        project_dir = tmp_path / "python-project"
        project_dir.mkdir()
        (project_dir / "pyproject.toml").touch()

        scope = ProjectScope.detect(project_dir)
        assert scope is not None
        assert scope.root_path == project_dir

    def test_detect_nested(self, tmp_path):
        """Detect project from nested directory."""
        project_dir = tmp_path / "project"
        nested_dir = project_dir / "src" / "package"
        nested_dir.mkdir(parents=True)
        (project_dir / ".git").mkdir()

        scope = ProjectScope.detect(nested_dir)
        assert scope is not None
        assert scope.root_path == project_dir


class TestProjectMemoryEntry:
    """Tests for ProjectMemoryEntry."""

    def test_create_entry(self):
        """Create memory entry."""
        entry = ProjectMemoryEntry(
            content="Test content",
            category="note",
            tags=["test"],
        )
        assert entry.content == "Test content"
        assert entry.category == "note"
        assert entry.entry_id

    def test_to_dict_from_dict(self):
        """Serialize and deserialize entry."""
        entry1 = ProjectMemoryEntry(
            content="Test",
            category="fact",
            tags=["important"],
            source="agent",
            relevance=0.8,
        )
        data = entry1.to_dict()
        entry2 = ProjectMemoryEntry.from_dict(data)

        assert entry2.content == entry1.content
        assert entry2.category == entry1.category
        assert entry2.relevance == entry1.relevance


class TestProjectMemory:
    """Tests for ProjectMemory."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a test project directory."""
        project = tmp_path / "test-project"
        project.mkdir()
        (project / ".git").mkdir()
        return project

    @pytest.fixture
    def consent_manager(self, tmp_path):
        """Create a consent manager with all permissions."""
        manager = ConsentManager(storage_path=tmp_path / "consent.json")
        manager.enable_all_memory()
        return manager

    def test_add_entry(self, project_dir, consent_manager):
        """Add memory entry."""
        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent_manager)

        entry = memory.add("Test note", category="note")
        assert entry is not None
        assert len(memory) == 1

    def test_save_load(self, project_dir, consent_manager):
        """Save and load memory."""
        scope = ProjectScope(root_path=project_dir)

        # Create and save
        memory1 = ProjectMemory(scope, consent_manager=consent_manager)
        memory1.add("Note 1", tags=["tag1"])
        memory1.add("Note 2", category="fact")
        memory1.save()

        # Load and verify
        memory2 = ProjectMemory(scope, consent_manager=consent_manager)
        memory2.load()

        assert len(memory2) == 2

    def test_search(self, project_dir, consent_manager):
        """Search memory entries."""
        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent_manager)

        memory.add("Python uses pytest for testing")
        memory.add("JavaScript uses jest for testing")
        memory.add("Project uses React frontend")

        results = memory.search("testing")
        assert len(results) == 2

    def test_filter_by_category(self, project_dir, consent_manager):
        """Filter entries by category."""
        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent_manager)

        memory.add("Note 1", category="note")
        memory.add("Note 2", category="note")
        memory.add("Fact 1", category="fact")

        notes = memory.get_by_category("note")
        facts = memory.get_by_category("fact")

        assert len(notes) == 2
        assert len(facts) == 1

    def test_preferences(self, project_dir, consent_manager):
        """Store and retrieve preferences."""
        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent_manager)

        memory.set_preference("test_framework", "pytest")
        memory.set_preference("indent_style", "spaces")
        memory.save()

        # Reload
        memory2 = ProjectMemory(scope, consent_manager=consent_manager)
        memory2.load()

        assert memory2.get_preference("test_framework") == "pytest"
        assert memory2.get_preference("indent_style") == "spaces"

    def test_to_context(self, project_dir, consent_manager):
        """Generate context string."""
        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent_manager)

        memory.add("Uses Python 3.10+", category="fact", relevance=0.9)
        memory.add("Prefers functional style", category="preference", relevance=0.7)

        context = memory.to_context()
        assert "Python 3.10" in context
        assert "functional style" in context

    def test_encrypted_storage(self, project_dir, consent_manager):
        """Test encrypted memory storage."""
        scope = ProjectScope(root_path=project_dir)

        # Create with encryption
        memory1 = ProjectMemory(scope, encrypted=True, consent_manager=consent_manager)
        memory1.add("Secret note", tags=["secret"])
        memory1.save()

        # Encrypted file should exist
        assert scope.encrypted_memory_file.exists()

        # Load and verify
        memory2 = ProjectMemory(scope, encrypted=True, consent_manager=consent_manager)
        memory2.load()

        assert len(memory2) == 1
        entries = memory2.get_by_tags(["secret"])
        assert len(entries) == 1

    def test_consent_denied(self, project_dir, tmp_path):
        """Memory operations denied without consent."""
        consent = ConsentManager(storage_path=tmp_path / "consent.json")
        consent.disable_all_memory()

        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent)

        # Add should return None when denied
        entry = memory.add("Test")
        assert entry is None
        assert len(memory) == 0

    def test_clear_memory(self, project_dir, consent_manager):
        """Clear memory entries."""
        scope = ProjectScope(root_path=project_dir)
        memory = ProjectMemory(scope, consent_manager=consent_manager)

        memory.add("Note 1", category="note")
        memory.add("Note 2", category="note")
        memory.add("Fact 1", category="fact")

        # Clear specific category
        cleared = memory.clear(category="note")
        assert cleared == 2
        assert len(memory) == 1

        # Clear all
        memory.add("Another note")
        cleared = memory.clear()
        assert len(memory) == 0
