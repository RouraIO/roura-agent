"""
Roura Agent Licensing - Feature tiers and license management.

This module provides:
- License tier definitions (FREE, PRO, ENTERPRISE)
- Feature gating based on license tier
- License key validation

Usage:
    from roura_agent.licensing import get_current_tier, is_feature_enabled, Tier

    if not is_feature_enabled("provider.openai"):
        print("Upgrade to Pro for OpenAI support")

"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional


class Tier(Enum):
    """License tier levels."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Features that require Pro tier
PRO_FEATURES: set[str] = {
    # Cloud providers
    "provider.openai",
    "provider.anthropic",
    # Autonomous fix loops
    "tool.test.fix",
    "tool.build.fix",
    "tool.typecheck.fix",
    # Advanced integrations
    "tool.github.*",
    "tool.jira.*",
}

# Features that require Enterprise tier
ENTERPRISE_FEATURES: set[str] = {
    "team.collaboration",
    "team.shared_sessions",
    "audit.advanced",
    "sso.saml",
    "sso.oidc",
}


@dataclass
class License:
    """A license key and its metadata."""
    key: str
    tier: Tier
    valid_until: Optional[datetime]
    email: str
    organization: Optional[str] = None
    seats: int = 1
    features: set[str] = None  # Additional features beyond tier

    def __post_init__(self):
        if self.features is None:
            self.features = set()

    @property
    def is_valid(self) -> bool:
        """Check if license is currently valid."""
        if self.valid_until is None:
            return True  # Perpetual license
        return datetime.utcnow() < self.valid_until

    @property
    def is_expired(self) -> bool:
        """Check if license has expired."""
        return not self.is_valid


def _load_license_key() -> Optional[str]:
    """Load license key from environment or config file."""
    # Check environment first
    if key := os.getenv("ROURA_LICENSE_KEY"):
        return key

    # Check config file
    config_path = Path.home() / ".config" / "roura-agent" / "license.key"
    if config_path.exists():
        return config_path.read_text().strip()

    return None


def _parse_license_key(key: str) -> Optional[License]:
    """
    Parse and validate a license key.

    In production, this would validate against a license server.
    For now, we use a simple format for development.
    """
    # Development/testing: Simple format TIER-EMAIL-EXPIRY
    # e.g., "PRO-user@example.com-2026-12-31" or "FREE-user@example.com-PERPETUAL"
    try:
        parts = key.split("-", 2)
        if len(parts) < 2:
            return None

        tier_str = parts[0].upper()
        email = parts[1] if len(parts) > 1 else ""
        expiry_str = parts[2] if len(parts) > 2 else "PERPETUAL"

        # Parse tier
        try:
            tier = Tier(tier_str.lower())
        except ValueError:
            return None

        # Parse expiry
        if expiry_str == "PERPETUAL":
            valid_until = None
        else:
            try:
                valid_until = datetime.strptime(expiry_str, "%Y-%m-%d")
            except ValueError:
                return None

        return License(
            key=key,
            tier=tier,
            valid_until=valid_until,
            email=email,
        )
    except Exception:
        return None


# Cached license
_cached_license: Optional[License] = None
_cache_checked: bool = False


def get_current_license() -> Optional[License]:
    """Get the current license, if any."""
    global _cached_license, _cache_checked

    if _cache_checked:
        return _cached_license

    _cache_checked = True
    key = _load_license_key()
    if key:
        _cached_license = _parse_license_key(key)

    return _cached_license


def get_current_tier() -> Tier:
    """
    Get the current license tier.

    Returns FREE if no valid license is found.
    """
    license = get_current_license()
    if license and license.is_valid:
        return license.tier
    return Tier.FREE


def is_feature_enabled(feature: str) -> bool:
    """
    Check if a feature is enabled for the current license tier.

    Args:
        feature: Feature identifier (e.g., "provider.openai", "tool.test.fix")

    Returns:
        True if feature is available, False otherwise

    Examples:
        >>> is_feature_enabled("provider.ollama")  # Always True
        True
        >>> is_feature_enabled("provider.openai")  # Requires Pro
        False  # (if on Free tier)
    """
    tier = get_current_tier()
    license = get_current_license()

    # Check if feature is in custom license features
    if license and feature in license.features:
        return True

    # Check tier-based access
    if tier == Tier.ENTERPRISE:
        return True  # Enterprise has access to everything

    if tier == Tier.PRO:
        # Pro has access to everything except Enterprise features
        return not _matches_feature_set(feature, ENTERPRISE_FEATURES)

    # Free tier - check if feature requires paid tier
    if _matches_feature_set(feature, PRO_FEATURES):
        return False
    if _matches_feature_set(feature, ENTERPRISE_FEATURES):
        return False

    return True


def _matches_feature_set(feature: str, feature_set: set[str]) -> bool:
    """Check if a feature matches any pattern in a feature set."""
    for pattern in feature_set:
        if fnmatch(feature, pattern):
            return True
    return False


def validate_license_key(key: str) -> Optional[License]:
    """
    Validate a license key.

    In production, this would call a license server.
    For development, it parses the key format directly.

    Args:
        key: License key to validate

    Returns:
        License object if valid, None otherwise
    """
    return _parse_license_key(key)


def require_feature(feature: str) -> None:
    """
    Assert that a feature is enabled, raising an error if not.

    Args:
        feature: Feature identifier

    Raises:
        LicenseError: If feature is not enabled
    """
    if not is_feature_enabled(feature):
        tier = get_current_tier()
        required_tier = _get_required_tier(feature)
        raise LicenseError(
            f"Feature '{feature}' requires {required_tier.value} tier. "
            f"Current tier: {tier.value}. "
            "Upgrade at https://roura.io/pricing"
        )


def _get_required_tier(feature: str) -> Tier:
    """Get the minimum tier required for a feature."""
    if _matches_feature_set(feature, ENTERPRISE_FEATURES):
        return Tier.ENTERPRISE
    if _matches_feature_set(feature, PRO_FEATURES):
        return Tier.PRO
    return Tier.FREE


class LicenseError(Exception):
    """Raised when a feature is not available due to licensing."""
    pass


def get_tier_features(tier: Tier) -> list[str]:
    """Get list of features available for a tier."""
    features = [
        "provider.ollama",
        "tool.fs.*",
        "tool.git.*",
        "tool.shell.*",
        "tool.search.*",
        "session.persistence",
        "safety.controls",
    ]

    if tier in (Tier.PRO, Tier.ENTERPRISE):
        features.extend([
            "provider.openai",
            "provider.anthropic",
            "tool.test.fix",
            "tool.build.fix",
            "tool.typecheck.fix",
            "tool.github.*",
            "tool.jira.*",
        ])

    if tier == Tier.ENTERPRISE:
        features.extend([
            "team.collaboration",
            "team.shared_sessions",
            "audit.advanced",
            "sso.saml",
            "sso.oidc",
        ])

    return features


def clear_license_cache() -> None:
    """Clear the cached license (for testing)."""
    global _cached_license, _cache_checked
    _cached_license = None
    _cache_checked = False
