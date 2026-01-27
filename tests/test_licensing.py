"""
Tests for licensing module.
"""
import pytest
from datetime import datetime, timedelta

from roura_agent.licensing import (
    Tier,
    License,
    get_current_tier,
    is_feature_enabled,
    require_feature,
    validate_license_key,
    get_tier_features,
    clear_license_cache,
    LicenseError,
    PRO_FEATURES,
    ENTERPRISE_FEATURES,
)


class TestTier:
    """Tests for Tier enum."""

    def test_tier_values(self):
        """Test tier enum values."""
        assert Tier.FREE.value == "free"
        assert Tier.PRO.value == "pro"
        assert Tier.ENTERPRISE.value == "enterprise"


class TestLicense:
    """Tests for License dataclass."""

    def test_license_creation(self):
        """Test creating a license."""
        license = License(
            key="test-key",
            tier=Tier.PRO,
            valid_until=None,
            email="test@example.com",
        )
        assert license.tier == Tier.PRO
        assert license.is_valid is True

    def test_license_expired(self):
        """Test expired license detection."""
        past_date = datetime.utcnow() - timedelta(days=1)
        license = License(
            key="test-key",
            tier=Tier.PRO,
            valid_until=past_date,
            email="test@example.com",
        )
        assert license.is_valid is False
        assert license.is_expired is True

    def test_license_perpetual(self):
        """Test perpetual license (no expiry)."""
        license = License(
            key="test-key",
            tier=Tier.PRO,
            valid_until=None,
            email="test@example.com",
        )
        assert license.is_valid is True
        assert license.is_expired is False


class TestValidateLicenseKey:
    """Tests for license key validation."""

    def test_valid_pro_key(self):
        """Test valid pro license key."""
        license = validate_license_key("PRO-user@example.com-2030-12-31")
        assert license is not None
        assert license.tier == Tier.PRO
        assert license.email == "user@example.com"

    def test_valid_perpetual_key(self):
        """Test valid perpetual license key."""
        license = validate_license_key("PRO-user@example.com-PERPETUAL")
        assert license is not None
        assert license.valid_until is None

    def test_invalid_key_format(self):
        """Test invalid key format returns None."""
        assert validate_license_key("invalid") is None
        assert validate_license_key("") is None

    def test_invalid_tier(self):
        """Test invalid tier returns None."""
        assert validate_license_key("INVALID-user@example.com-PERPETUAL") is None


class TestGetCurrentTier:
    """Tests for get_current_tier."""

    def test_returns_free_without_license(self, monkeypatch):
        """Test returns FREE when no license is set."""
        monkeypatch.delenv("ROURA_LICENSE_KEY", raising=False)
        clear_license_cache()

        tier = get_current_tier()
        assert tier == Tier.FREE

    def test_returns_pro_with_valid_key(self, monkeypatch):
        """Test returns PRO with valid license key."""
        monkeypatch.setenv("ROURA_LICENSE_KEY", "PRO-user@example.com-PERPETUAL")
        clear_license_cache()

        tier = get_current_tier()
        assert tier == Tier.PRO

    def test_returns_free_with_expired_key(self, monkeypatch):
        """Test returns FREE with expired license key."""
        monkeypatch.setenv("ROURA_LICENSE_KEY", "PRO-user@example.com-2020-01-01")
        clear_license_cache()

        tier = get_current_tier()
        assert tier == Tier.FREE


class TestIsFeatureEnabled:
    """Tests for is_feature_enabled."""

    def test_free_features_always_enabled(self, monkeypatch):
        """Test free features are always enabled."""
        monkeypatch.delenv("ROURA_LICENSE_KEY", raising=False)
        clear_license_cache()

        assert is_feature_enabled("provider.ollama") is True
        assert is_feature_enabled("tool.fs.read") is True

    def test_pro_features_disabled_on_free(self, monkeypatch):
        """Test pro features are disabled on free tier."""
        monkeypatch.delenv("ROURA_LICENSE_KEY", raising=False)
        clear_license_cache()

        assert is_feature_enabled("provider.openai") is False
        assert is_feature_enabled("provider.anthropic") is False

    def test_pro_features_enabled_on_pro(self, monkeypatch):
        """Test pro features are enabled on pro tier."""
        monkeypatch.setenv("ROURA_LICENSE_KEY", "PRO-user@example.com-PERPETUAL")
        clear_license_cache()

        assert is_feature_enabled("provider.openai") is True
        assert is_feature_enabled("provider.anthropic") is True

    def test_enterprise_features_disabled_on_pro(self, monkeypatch):
        """Test enterprise features are disabled on pro tier."""
        monkeypatch.setenv("ROURA_LICENSE_KEY", "PRO-user@example.com-PERPETUAL")
        clear_license_cache()

        assert is_feature_enabled("team.collaboration") is False

    def test_all_features_enabled_on_enterprise(self, monkeypatch):
        """Test all features are enabled on enterprise tier."""
        monkeypatch.setenv("ROURA_LICENSE_KEY", "ENTERPRISE-user@example.com-PERPETUAL")
        clear_license_cache()

        assert is_feature_enabled("provider.openai") is True
        assert is_feature_enabled("team.collaboration") is True


class TestRequireFeature:
    """Tests for require_feature."""

    def test_raises_for_disabled_feature(self, monkeypatch):
        """Test raises LicenseError for disabled feature."""
        monkeypatch.delenv("ROURA_LICENSE_KEY", raising=False)
        clear_license_cache()

        with pytest.raises(LicenseError) as exc_info:
            require_feature("provider.openai")

        assert "pro" in str(exc_info.value).lower()

    def test_does_not_raise_for_enabled_feature(self, monkeypatch):
        """Test does not raise for enabled feature."""
        monkeypatch.setenv("ROURA_LICENSE_KEY", "PRO-user@example.com-PERPETUAL")
        clear_license_cache()

        # Should not raise
        require_feature("provider.openai")


class TestGetTierFeatures:
    """Tests for get_tier_features."""

    def test_free_tier_has_basic_features(self):
        """Test free tier has basic features."""
        features = get_tier_features(Tier.FREE)
        assert "provider.ollama" in features
        assert "tool.fs.*" in features

    def test_pro_tier_has_more_features(self):
        """Test pro tier has more features than free."""
        free_features = get_tier_features(Tier.FREE)
        pro_features = get_tier_features(Tier.PRO)

        assert len(pro_features) > len(free_features)
        assert "provider.openai" in pro_features

    def test_enterprise_tier_has_all_features(self):
        """Test enterprise tier has all features."""
        enterprise_features = get_tier_features(Tier.ENTERPRISE)

        assert "team.collaboration" in enterprise_features
        assert "sso.saml" in enterprise_features
