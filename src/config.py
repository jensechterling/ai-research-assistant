"""Configuration loading and access."""
import copy
from pathlib import Path

import yaml


def _get_project_dir() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base. Returns a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config() -> dict:
    """Load configuration from defaults.yaml, deep-merged with user.yaml if present."""
    project_dir = _get_project_dir()
    defaults_path = project_dir / "config" / "defaults.yaml"
    user_path = project_dir / "config" / "user.yaml"

    with open(defaults_path) as f:
        config = yaml.safe_load(f)

    if user_path.exists():
        with open(user_path) as f:
            user_config = yaml.safe_load(f)
            if user_config:
                config = _deep_merge(config, user_config)

    return config


def get_vault_path(config: dict | None = None) -> Path:
    """Return the expanded vault path from config."""
    if config is None:
        config = load_config()
    vault_path = config["vault"]["path"]
    if vault_path is None:
        raise ValueError("Vault path not configured. Run: ai-research-assistant setup")
    return Path(vault_path).expanduser()


def get_skills_path() -> Path:
    """Return the Claude Code skills directory."""
    return Path.home() / ".claude" / "skills"


def get_folder(name: str, config: dict | None = None) -> str:
    """Return a configured folder path by name (e.g., 'youtube', 'article')."""
    if config is None:
        config = load_config()
    return config["folders"][name]


def get_project_dir() -> Path:
    """Return the project root directory."""
    return _get_project_dir()


def is_configured() -> bool:
    """Check whether user.yaml exists (setup has been run)."""
    return (_get_project_dir() / "config" / "user.yaml").exists()
