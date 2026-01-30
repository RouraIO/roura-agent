"""
Tests for the centralized configuration system.

© Roura.io
"""
import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from roura_agent.config import (
    ConfigSource,
    ConfigValue,
    LLMConfig,
    ToolsConfig,
    MemoryConfig,
    MCPConfig,
    LoggingConfig,
    UIConfig,
    SecurityConfig,
    RouraConfig,
    ConfigManager,
    load_config_file,
    _deep_merge,
    _env_to_config,
    get_config_manager,
    reset_config_manager,
)


class TestConfigDataclasses:
    """Tests for configuration dataclasses."""

    def test_llm_config_defaults(self):
        """Test LLMConfig default values."""
        config = LLMConfig()
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.api_key is None
        assert config.max_tokens == 4096
        assert config.temperature == 0.7

    def test_llm_config_custom_values(self):
        """Test LLMConfig with custom values."""
        config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="sk-test",
            max_tokens=8192,
            temperature=0.9,
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.api_key == "sk-test"
        assert config.max_tokens == 8192
        assert config.temperature == 0.9

    def test_tools_config_defaults(self):
        """Test ToolsConfig default values."""
        config = ToolsConfig()
        assert config.enabled == ["all"]
        assert config.disabled == []
        assert "shell_exec" in config.require_approval
        assert config.timeout == 30.0

    def test_memory_config_defaults(self):
        """Test MemoryConfig default values."""
        config = MemoryConfig()
        assert config.enabled is True
        assert config.max_entries == 1000
        assert config.similarity_threshold == 0.7

    def test_mcp_config_defaults(self):
        """Test MCPConfig default values."""
        config = MCPConfig()
        assert config.enabled is True
        assert config.servers == {}
        assert config.auto_connect == []

    def test_logging_config_defaults(self):
        """Test LoggingConfig default values."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.file is None
        assert config.json_format is False

    def test_ui_config_defaults(self):
        """Test UIConfig default values."""
        config = UIConfig()
        assert config.color is True
        assert config.spinner is True
        assert config.show_tokens is False

    def test_security_config_defaults(self):
        """Test SecurityConfig default values."""
        config = SecurityConfig()
        assert config.allow_network is True
        assert config.allow_shell is True
        assert config.sandbox_mode is False
        assert config.max_file_size == 10 * 1024 * 1024


class TestRouraConfig:
    """Tests for RouraConfig main container."""

    def test_default_construction(self):
        """Test default RouraConfig construction."""
        config = RouraConfig()
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.tools, ToolsConfig)
        assert isinstance(config.memory, MemoryConfig)
        assert isinstance(config.mcp, MCPConfig)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = RouraConfig()
        data = config.to_dict()
        assert "llm" in data
        assert "tools" in data
        assert "memory" in data
        assert data["llm"]["provider"] == "anthropic"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "llm": {"provider": "openai", "model": "gpt-4"},
            "tools": {"timeout": 60.0},
        }
        config = RouraConfig.from_dict(data)
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4"
        assert config.tools.timeout == 60.0

    def test_from_dict_partial(self):
        """Test from_dict with partial data uses defaults."""
        data = {"llm": {"model": "custom-model"}}
        config = RouraConfig.from_dict(data)
        # Custom value
        assert config.llm.model == "custom-model"
        # Default values still present
        assert config.llm.provider == "anthropic"
        assert config.tools.timeout == 30.0


class TestConfigSource:
    """Tests for ConfigSource enum."""

    def test_priority_ordering(self):
        """Test that CLI has highest priority (lowest value)."""
        assert ConfigSource.CLI.value < ConfigSource.ENV.value
        assert ConfigSource.ENV.value < ConfigSource.PROJECT.value
        assert ConfigSource.PROJECT.value < ConfigSource.USER.value
        assert ConfigSource.USER.value < ConfigSource.DEFAULT.value


class TestDeepMerge:
    """Tests for _deep_merge function."""

    def test_simple_merge(self):
        """Test simple dictionary merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test nested dictionary merge."""
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 20, "z": 30}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}

    def test_deeply_nested_merge(self):
        """Test deeply nested merge."""
        base = {"a": {"b": {"c": 1}}}
        override = {"a": {"b": {"d": 2}}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 2}}}

    def test_override_non_dict_with_dict(self):
        """Test overriding non-dict with dict."""
        base = {"a": 1}
        override = {"a": {"x": 2}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 2}}


class TestEnvToConfig:
    """Tests for _env_to_config function."""

    def test_llm_env_vars(self):
        """Test LLM environment variables."""
        with patch.dict(os.environ, {
            "ROURA_LLM_PROVIDER": "openai",
            "ROURA_LLM_MODEL": "gpt-4",
        }):
            config = _env_to_config()
            assert config["llm"]["provider"] == "openai"
            assert config["llm"]["model"] == "gpt-4"

    def test_anthropic_api_key(self):
        """Test ANTHROPIC_API_KEY is mapped."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            # Clear any existing key
            orig = os.environ.pop("ROURA_LLM_API_KEY", None)
            try:
                config = _env_to_config()
                assert config.get("llm", {}).get("api_key") == "sk-test"
            finally:
                if orig:
                    os.environ["ROURA_LLM_API_KEY"] = orig

    def test_boolean_env_vars(self):
        """Test boolean environment variable parsing."""
        with patch.dict(os.environ, {
            "ROURA_COLOR": "false",
            "ROURA_SANDBOX_MODE": "true",
        }):
            config = _env_to_config()
            assert config["ui"]["color"] is False
            assert config["security"]["sandbox_mode"] is True

    def test_numeric_env_vars(self):
        """Test numeric environment variable parsing."""
        with patch.dict(os.environ, {
            "ROURA_LLM_MAX_TOKENS": "8192",
            "ROURA_LLM_TEMPERATURE": "0.5",
        }):
            config = _env_to_config()
            assert config["llm"]["max_tokens"] == 8192
            assert config["llm"]["temperature"] == 0.5


class TestLoadConfigFile:
    """Tests for load_config_file function."""

    def test_load_json_file(self, tmp_path):
        """Test loading JSON config file."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"llm": {"model": "test-model"}}')

        data = load_config_file(config_file)
        assert data["llm"]["model"] == "test-model"

    def test_load_toml_file(self, tmp_path):
        """Test loading TOML config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[llm]\nmodel = "test-model"')

        data = load_config_file(config_file)
        assert data["llm"]["model"] == "test-model"

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading nonexistent file returns empty dict."""
        config_file = tmp_path / "nonexistent.json"
        data = load_config_file(config_file)
        assert data == {}

    def test_unsupported_format(self, tmp_path):
        """Test unsupported format raises error."""
        config_file = tmp_path / "config.xyz"
        config_file.write_text("data")

        with pytest.raises(ValueError, match="Unsupported config file format"):
            load_config_file(config_file)


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_default_construction(self):
        """Test default ConfigManager construction."""
        manager = ConfigManager()
        assert manager._project_root == Path.cwd()
        assert manager._loaded is False

    def test_load_returns_config(self):
        """Test load returns RouraConfig."""
        manager = ConfigManager()
        config = manager.load()
        assert isinstance(config, RouraConfig)
        assert manager._loaded is True

    def test_config_property_auto_loads(self):
        """Test config property auto-loads."""
        manager = ConfigManager()
        assert manager._loaded is False
        _ = manager.config
        assert manager._loaded is True

    def test_llm_property(self):
        """Test llm property returns LLMConfig."""
        manager = ConfigManager()
        assert isinstance(manager.llm, LLMConfig)

    def test_tools_property(self):
        """Test tools property returns ToolsConfig."""
        manager = ConfigManager()
        assert isinstance(manager.tools, ToolsConfig)

    def test_get_by_key(self):
        """Test getting config value by key."""
        manager = ConfigManager()
        manager.load()
        assert manager.get("llm.provider") == "anthropic"
        assert manager.get("llm.model") == "claude-sonnet-4-20250514"

    def test_get_nested_key(self):
        """Test getting nested config value."""
        manager = ConfigManager()
        manager.load()
        assert manager.get("tools.timeout") == 30.0

    def test_get_with_default(self):
        """Test get with default value."""
        manager = ConfigManager()
        manager.load()
        assert manager.get("nonexistent.key", "default") == "default"

    def test_set_cli_override(self):
        """Test setting CLI override."""
        manager = ConfigManager()
        manager.load()
        manager.set_cli_override("llm.model", "custom-model")
        assert manager.get("llm.model") == "custom-model"

    def test_cli_override_highest_priority(self):
        """Test CLI overrides have highest priority."""
        with patch.dict(os.environ, {"ROURA_LLM_MODEL": "env-model"}):
            manager = ConfigManager()
            manager.load()
            manager.set_cli_override("llm.model", "cli-model")
            assert manager.get("llm.model") == "cli-model"

    def test_validate_valid_config(self):
        """Test validation of valid config."""
        manager = ConfigManager()
        manager.load()
        errors = manager.validate()
        assert errors == []

    def test_validate_invalid_temperature(self):
        """Test validation catches invalid temperature."""
        manager = ConfigManager()
        manager.load()
        manager._config.llm.temperature = 3.0
        errors = manager.validate()
        assert any("temperature" in e for e in errors)

    def test_validate_invalid_max_tokens(self):
        """Test validation catches invalid max_tokens."""
        manager = ConfigManager()
        manager.load()
        manager._config.llm.max_tokens = 0
        errors = manager.validate()
        assert any("max_tokens" in e for e in errors)

    def test_show_masks_secrets(self):
        """Test show masks sensitive values."""
        manager = ConfigManager()
        manager.load()
        manager._config.llm.api_key = "sk-secret-key"

        display = manager.show(show_secrets=False)
        assert display["llm"]["api_key"] == "***"

    def test_show_reveals_secrets(self):
        """Test show reveals secrets when requested."""
        manager = ConfigManager()
        manager.load()
        manager._config.llm.api_key = "sk-secret-key"

        display = manager.show(show_secrets=True)
        assert display["llm"]["api_key"] == "sk-secret-key"

    def test_reload_config(self):
        """Test reload forces config reload."""
        manager = ConfigManager()
        manager.load()
        original_model = manager.get("llm.model")

        # Modify loaded config
        manager._config.llm.model = "modified"

        # Reload should restore original
        manager.load(reload=True)
        assert manager.get("llm.model") == original_model


class TestConfigManagerFileSources:
    """Tests for ConfigManager with file sources."""

    @pytest.fixture
    def temp_config_dirs(self, tmp_path):
        """Create temporary config directories."""
        user_dir = tmp_path / ".config" / "roura"
        user_dir.mkdir(parents=True)

        project_dir = tmp_path / "project" / ".roura"
        project_dir.mkdir(parents=True)

        return {
            "user": user_dir,
            "project": project_dir,
            "project_root": tmp_path / "project",
        }

    def test_load_user_config(self, temp_config_dirs):
        """Test loading user config file."""
        user_config = temp_config_dirs["user"] / "config.json"
        user_config.write_text('{"llm": {"model": "user-model"}}')

        with patch.object(ConfigManager, "USER_CONFIG_DIR", temp_config_dirs["user"]):
            manager = ConfigManager(temp_config_dirs["project_root"])
            manager.load()
            assert manager.get("llm.model") == "user-model"

    def test_load_project_config(self, temp_config_dirs):
        """Test loading project config file."""
        project_config = temp_config_dirs["project"] / "config.json"
        project_config.write_text('{"llm": {"model": "project-model"}}')

        manager = ConfigManager(temp_config_dirs["project_root"])
        manager.load()
        assert manager.get("llm.model") == "project-model"

    def test_project_overrides_user(self, temp_config_dirs):
        """Test project config overrides user config."""
        user_config = temp_config_dirs["user"] / "config.json"
        user_config.write_text('{"llm": {"model": "user-model", "provider": "user-provider"}}')

        project_config = temp_config_dirs["project"] / "config.json"
        project_config.write_text('{"llm": {"model": "project-model"}}')

        with patch.object(ConfigManager, "USER_CONFIG_DIR", temp_config_dirs["user"]):
            manager = ConfigManager(temp_config_dirs["project_root"])
            manager.load()
            # Project overrides user
            assert manager.get("llm.model") == "project-model"
            # User value preserved for non-overridden keys
            assert manager.get("llm.provider") == "user-provider"

    def test_env_overrides_files(self, temp_config_dirs):
        """Test env vars override file configs."""
        project_config = temp_config_dirs["project"] / "config.json"
        project_config.write_text('{"llm": {"model": "file-model"}}')

        with patch.dict(os.environ, {"ROURA_LLM_MODEL": "env-model"}):
            manager = ConfigManager(temp_config_dirs["project_root"])
            manager.load()
            assert manager.get("llm.model") == "env-model"


class TestConfigManagerProjectInit:
    """Tests for project config initialization."""

    def test_init_project_config(self, tmp_path):
        """Test initializing project config."""
        manager = ConfigManager(tmp_path)
        manager.load()

        config_file = manager.init_project_config()

        assert config_file.exists()
        assert config_file.parent.name == ".roura"

    def test_init_project_config_already_exists(self, tmp_path):
        """Test init raises if config exists."""
        config_dir = tmp_path / ".roura"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("[llm]")

        manager = ConfigManager(tmp_path)

        with pytest.raises(FileExistsError):
            manager.init_project_config()


class TestGlobalConfigManager:
    """Tests for global config manager singleton."""

    def test_get_config_manager_singleton(self):
        """Test get_config_manager returns singleton."""
        reset_config_manager()
        m1 = get_config_manager()
        m2 = get_config_manager()
        assert m1 is m2

    def test_reset_config_manager(self):
        """Test reset_config_manager clears singleton."""
        m1 = get_config_manager()
        reset_config_manager()
        m2 = get_config_manager()
        assert m1 is not m2


class TestConfigSourceTracking:
    """Tests for tracking config value sources."""

    def test_track_default_source(self):
        """Test tracking default values."""
        manager = ConfigManager()
        manager.load()
        # Defaults are not tracked since they're built into the dataclass
        # Only loaded values are tracked

    def test_track_env_source(self):
        """Test tracking env var source."""
        with patch.dict(os.environ, {"ROURA_LLM_MODEL": "env-model"}):
            manager = ConfigManager()
            manager.load()
            source = manager.get_source("llm.model")
            assert source == ConfigSource.ENV

    def test_track_cli_source(self):
        """Test tracking CLI override source."""
        manager = ConfigManager()
        manager.load()
        manager.set_cli_override("llm.model", "cli-model")
        source = manager.get_source("llm.model")
        assert source == ConfigSource.CLI
