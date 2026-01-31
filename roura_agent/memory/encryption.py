"""
Roura Agent Memory Encryption - Secure local storage.

Provides:
- AES-256-GCM encryption for memory data
- Key derivation from password
- Secure key storage
- Encrypted file operations

© Roura.io
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..logging import get_logger

logger = get_logger(__name__)

# Try to import cryptography, fall back to basic encoding if not available
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography not installed, using basic encoding (not secure)")


@dataclass
class EncryptionKey:
    """
    Encryption key for memory storage.

    Stores the raw key bytes and associated metadata.
    """
    key: bytes
    salt: bytes
    created_at: str = field(default_factory=lambda: __import__("datetime").datetime.now().isoformat())
    key_id: str = field(default_factory=lambda: secrets.token_hex(8))

    def to_dict(self) -> dict:
        """Serialize key metadata (not the key itself)."""
        return {
            "salt": base64.b64encode(self.salt).decode(),
            "created_at": self.created_at,
            "key_id": self.key_id,
        }

    @classmethod
    def from_dict(cls, data: dict, key: bytes) -> "EncryptionKey":
        """Create from dict with provided key."""
        return cls(
            key=key,
            salt=base64.b64decode(data["salt"]),
            created_at=data.get("created_at", ""),
            key_id=data.get("key_id", ""),
        )


def generate_key() -> EncryptionKey:
    """
    Generate a new random encryption key.

    Returns:
        EncryptionKey with random 256-bit key and salt
    """
    key = secrets.token_bytes(32)  # 256 bits
    salt = secrets.token_bytes(16)
    return EncryptionKey(key=key, salt=salt)


def derive_key(password: str, salt: Optional[bytes] = None) -> EncryptionKey:
    """
    Derive encryption key from password.

    Uses PBKDF2 with SHA256, 480000 iterations (OWASP recommendation).

    Args:
        password: User password
        salt: Optional salt (generated if not provided)

    Returns:
        EncryptionKey derived from password
    """
    if salt is None:
        salt = secrets.token_bytes(16)

    if CRYPTO_AVAILABLE:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = kdf.derive(password.encode())
    else:
        # Fallback: simple PBKDF2 using hashlib
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            480000,
            dklen=32,
        )

    return EncryptionKey(key=key, salt=salt)


class EncryptedStore:
    """
    Encrypted file storage for memory data.

    Uses AES-256-GCM for authenticated encryption.
    Falls back to base64 encoding if cryptography not available.
    """

    def __init__(self, encryption_key: EncryptionKey):
        self._key = encryption_key
        if CRYPTO_AVAILABLE:
            self._cipher = AESGCM(self._key.key)
        else:
            self._cipher = None

    def encrypt(self, data: bytes) -> bytes:
        """
        Encrypt data.

        Args:
            data: Plaintext bytes

        Returns:
            Encrypted bytes (nonce + ciphertext)
        """
        if CRYPTO_AVAILABLE and self._cipher:
            nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
            ciphertext = self._cipher.encrypt(nonce, data, None)
            return nonce + ciphertext
        else:
            # Fallback: XOR with key hash (NOT SECURE - just obfuscation)
            key_hash = hashlib.sha256(self._key.key).digest()
            xored = bytes(a ^ b for a, b in zip(data, (key_hash * (len(data) // 32 + 1))[:len(data)]))
            return b"\x00" + xored  # Prefix with 0x00 to indicate fallback mode

    def decrypt(self, data: bytes) -> bytes:
        """
        Decrypt data.

        Args:
            data: Encrypted bytes (nonce + ciphertext)

        Returns:
            Decrypted plaintext bytes
        """
        if CRYPTO_AVAILABLE and self._cipher:
            if len(data) < 12:
                raise ValueError("Invalid ciphertext")
            nonce = data[:12]
            ciphertext = data[12:]
            return self._cipher.decrypt(nonce, ciphertext, None)
        else:
            # Fallback: XOR with key hash
            if not data or data[0] != 0:
                raise ValueError("Invalid encrypted data")
            key_hash = hashlib.sha256(self._key.key).digest()
            return bytes(a ^ b for a, b in zip(data[1:], (key_hash * (len(data) // 32 + 1))[:len(data) - 1]))

    def encrypt_json(self, data: Any) -> bytes:
        """Encrypt JSON-serializable data."""
        json_bytes = json.dumps(data).encode("utf-8")
        return self.encrypt(json_bytes)

    def decrypt_json(self, data: bytes) -> Any:
        """Decrypt data and parse as JSON."""
        decrypted = self.decrypt(data)
        return json.loads(decrypted.decode("utf-8"))

    def save_encrypted(self, path: Path, data: Any) -> None:
        """
        Save data to encrypted file.

        Args:
            path: File path
            data: JSON-serializable data
        """
        encrypted = self.encrypt_json(data)

        # Write with magic header and metadata
        header = {
            "version": 1,
            "key_id": self._key.key_id,
            "salt": base64.b64encode(self._key.salt).decode(),
        }

        with path.open("wb") as f:
            # Write header as JSON line
            header_line = json.dumps(header).encode() + b"\n"
            f.write(header_line)
            # Write encrypted data
            f.write(base64.b64encode(encrypted))

    def load_encrypted(self, path: Path) -> Any:
        """
        Load data from encrypted file.

        Args:
            path: File path

        Returns:
            Decrypted data
        """
        with path.open("rb") as f:
            # Read header
            header_line = f.readline()
            header = json.loads(header_line.decode())

            # Read encrypted data
            encrypted_b64 = f.read()
            encrypted = base64.b64decode(encrypted_b64)

        return self.decrypt_json(encrypted)

    @classmethod
    def create_with_password(cls, password: str) -> tuple["EncryptedStore", EncryptionKey]:
        """
        Create encrypted store with password-derived key.

        Args:
            password: User password

        Returns:
            Tuple of (EncryptedStore, EncryptionKey)
        """
        key = derive_key(password)
        return cls(key), key

    @classmethod
    def from_keyfile(cls, keyfile_path: Path) -> Optional["EncryptedStore"]:
        """
        Load encrypted store from keyfile.

        Keyfile contains encrypted key bytes.

        Args:
            keyfile_path: Path to keyfile

        Returns:
            EncryptedStore or None if keyfile not found
        """
        if not keyfile_path.exists():
            return None

        try:
            with keyfile_path.open("rb") as f:
                data = json.load(f)

            key_bytes = base64.b64decode(data["key"])
            salt = base64.b64decode(data["salt"])
            enc_key = EncryptionKey(
                key=key_bytes,
                salt=salt,
                created_at=data.get("created_at", ""),
                key_id=data.get("key_id", ""),
            )
            return cls(enc_key)
        except Exception as e:
            logger.error(f"Failed to load keyfile: {e}")
            return None

    def save_keyfile(self, keyfile_path: Path) -> None:
        """
        Save key to keyfile.

        WARNING: Keyfile contains unencrypted key. Protect with file permissions.

        Args:
            keyfile_path: Path to save keyfile
        """
        data = {
            "key": base64.b64encode(self._key.key).decode(),
            "salt": base64.b64encode(self._key.salt).decode(),
            "created_at": self._key.created_at,
            "key_id": self._key.key_id,
        }

        # Ensure parent directory exists
        keyfile_path.parent.mkdir(parents=True, exist_ok=True)

        with keyfile_path.open("w") as f:
            json.dump(data, f)

        # Set restrictive permissions (owner read/write only)
        try:
            keyfile_path.chmod(0o600)
        except OSError:
            pass  # Windows doesn't support chmod


def get_default_keyfile_path() -> Path:
    """Get the default keyfile path."""
    return Path.home() / ".config" / "roura-agent" / "memory.key"


def get_or_create_store(password: Optional[str] = None) -> EncryptedStore:
    """
    Get or create an encrypted store.

    If keyfile exists, load from it.
    If password provided, derive key.
    Otherwise, generate new random key.

    Args:
        password: Optional password for key derivation

    Returns:
        EncryptedStore
    """
    keyfile = get_default_keyfile_path()

    # Try loading from keyfile
    store = EncryptedStore.from_keyfile(keyfile)
    if store:
        return store

    # Create new key
    if password:
        key = derive_key(password)
    else:
        key = generate_key()

    store = EncryptedStore(key)

    # Save keyfile for future use
    store.save_keyfile(keyfile)

    return store
