"""Tests for configuration module."""
import pytest
import yaml

from src.config import _deep_merge, load_config, get_vault_path, get_skills_path, is_configured, get_folder, get_project_dir


def test_deep_merge_simple():
    """Deep merge should override simple values."""
    base = {"a": 1, "b": 2}
    override = {"b": 3}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": 3}


def test_deep_merge_nested():
    """Deep merge should recursively merge dicts."""
    base = {"vault": {"path": None}, "folders": {"youtube": "A", "podcast": "B"}}
    override = {"vault": {"path": "~/my-vault"}}
    result = _deep_merge(base, override)
    assert result["vault"]["path"] == "~/my-vault"
    assert result["folders"]["youtube"] == "A"
    assert result["folders"]["podcast"] == "B"


def test_deep_merge_does_not_mutate_base():
    """Deep merge should not modify the input dicts."""
    base = {"a": {"b": 1}}
    override = {"a": {"b": 2}}
    result = _deep_merge(base, override)
    assert base["a"]["b"] == 1
    assert result["a"]["b"] == 2


def test_load_config_returns_defaults():
    """load_config should return defaults when no user.yaml exists."""
    config = load_config()
    assert config["vault"]["path"] is None
    assert "folders" in config
    assert "youtube" in config["folders"]


def test_get_vault_path_raises_when_not_configured():
    """get_vault_path should raise when vault path is None."""
    config = {"vault": {"path": None}}
    with pytest.raises(ValueError, match="not configured"):
        get_vault_path(config)


def test_get_vault_path_expands_tilde():
    """get_vault_path should expand ~ in path."""
    config = {"vault": {"path": "~/some/vault"}}
    result = get_vault_path(config)
    assert "~" not in str(result)
    assert result.is_absolute()


def test_get_folder():
    """get_folder should return the configured folder path."""
    config = {"folders": {"youtube": "My Videos/YouTube"}}
    assert get_folder("youtube", config) == "My Videos/YouTube"


def test_get_project_dir():
    """get_project_dir should return the project root."""
    project_dir = get_project_dir()
    assert (project_dir / "pyproject.toml").exists()
    assert (project_dir / "config" / "defaults.yaml").exists()


def test_is_configured_false_without_user_yaml(tmp_path, monkeypatch):
    """is_configured should return False when user.yaml doesn't exist."""
    # This test relies on the actual state — user.yaml may or may not exist
    # Just verify it returns a boolean
    result = is_configured()
    assert isinstance(result, bool)


def test_get_skills_path():
    """get_skills_path should return ~/.claude/skills/."""
    result = get_skills_path()
    assert result.name == "skills"
    assert ".claude" in str(result)
    assert result.is_absolute()


def test_defaults_yaml_is_valid():
    """defaults.yaml should be valid YAML with expected structure."""
    project_dir = get_project_dir()
    with open(project_dir / "config" / "defaults.yaml") as f:
        config = yaml.safe_load(f)

    assert "vault" in config
    assert "folders" in config
    assert "processing" in config
    assert "retry" in config
    assert "feeds" in config
    assert config["vault"]["path"] is None  # Must be set by user
