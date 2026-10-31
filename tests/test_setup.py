"""Tests for setup module — template rendering and dependency checking."""
import re
from unittest.mock import MagicMock, patch

from jinja2 import Environment, FileSystemLoader

from src.config import get_project_dir, load_config
from src.setup import SKILLS, _check_dependencies, _copy_interest_profile, _install_cron


def _default_template_vars():
    """Return template variables using defaults — same structure as _render_templates."""
    config = load_config()
    config["vault"] = {"path": "/tmp/test-vault"}
    project_dir = get_project_dir()
    return {
        "vault_path": "/tmp/test-vault",
        "project_dir": str(project_dir),
        "home_dir": "/tmp/test-home",
        "folders": config["folders"],
        "profile": config["profile"],
        "schedule": config.get("schedule", {"hour": 6, "minute": 0}),
    }


def test_all_skill_templates_render_without_error():
    """Every skill template should render with default config values."""
    project_dir = get_project_dir()
    skills_template_dir = project_dir / "skills" / "_templates"

    env = Environment(
        loader=FileSystemLoader(str(skills_template_dir)),
        keep_trailing_newline=True,
    )
    template_vars = _default_template_vars()

    for skill in SKILLS:
        skill_dir = skills_template_dir / skill
        assert skill_dir.exists(), f"Template directory missing: {skill}"

        for template_file in skill_dir.iterdir():
            if template_file.is_file() and template_file.suffix == ".md":
                rel_path = f"{skill}/{template_file.name}"
                template = env.get_template(rel_path)
                rendered = template.render(**template_vars)
                assert len(rendered) > 0, f"Rendered {rel_path} is empty"


def test_rendered_skills_contain_no_jinja_artifacts():
    """Rendered skill templates should have no leftover {{ }} or {%% %%} tags."""
    project_dir = get_project_dir()
    skills_template_dir = project_dir / "skills" / "_templates"

    env = Environment(
        loader=FileSystemLoader(str(skills_template_dir)),
        keep_trailing_newline=True,
    )
    template_vars = _default_template_vars()

    jinja_pattern = re.compile(r"\{\{.*?\}\}|\{%.*?%\}")

    for skill in SKILLS:
        skill_dir = skills_template_dir / skill
        for template_file in skill_dir.iterdir():
            if template_file.is_file() and template_file.suffix == ".md":
                rel_path = f"{skill}/{template_file.name}"
                template = env.get_template(rel_path)
                rendered = template.render(**template_vars)
                matches = jinja_pattern.findall(rendered)
                assert not matches, (
                    f"Jinja artifacts in rendered {rel_path}: {matches}"
                )


def test_rendered_skills_contain_configured_folders():
    """Rendered skills should reference the configured folder paths, not defaults."""
    project_dir = get_project_dir()
    skills_template_dir = project_dir / "skills" / "_templates"

    env = Environment(
        loader=FileSystemLoader(str(skills_template_dir)),
        keep_trailing_newline=True,
    )
    template_vars = _default_template_vars()
    template_vars["folders"] = {
        **template_vars["folders"],
        "youtube": "Custom/YouTube Folder",
        "article": "Custom/Articles",
    }

    # YouTube skill should reference custom folder
    template = env.get_template("youtube/SKILL.md")
    rendered = template.render(**template_vars)
    assert "Custom/YouTube Folder" in rendered

    # Article skill should reference custom folder
    template = env.get_template("article/SKILL.md")
    rendered = template.render(**template_vars)
    assert "Custom/Articles" in rendered


def test_infra_templates_render_without_error():
    """Infrastructure templates (plist) should render with defaults."""
    project_dir = get_project_dir()
    template_vars = _default_template_vars()

    env = Environment(
        loader=FileSystemLoader(str(project_dir / "templates")),
        keep_trailing_newline=True,
    )

    infra_templates = [
        "com.claude.ai-research-assistant.plist.j2",
    ]

    for name in infra_templates:
        template = env.get_template(name)
        rendered = template.render(**template_vars)
        assert len(rendered) > 0, f"Rendered {name} is empty"


def test_render_templates_writes_plist_but_no_mcp_config(tmp_path, monkeypatch):
    """Setup renders the launchd plist and no longer creates config/mcp-minimal.json."""
    import shutil

    from src.setup import _render_templates

    project_dir = get_project_dir()
    shutil.copytree(project_dir / "skills" / "_templates", tmp_path / "skills" / "_templates")
    shutil.copytree(project_dir / "templates", tmp_path / "templates")
    (tmp_path / "config").mkdir()
    monkeypatch.setattr("src.setup.get_project_dir", lambda: tmp_path)

    _render_templates(load_config() | {"vault": {"path": "/Users/someone/Vault"}})

    assert not (tmp_path / "config" / "mcp-minimal.json").exists()
    plist = (tmp_path / "templates" / "com.claude.ai-research-assistant.plist").read_text()
    assert str(tmp_path) in plist


def test_rendered_skills_contain_no_personal_references():
    """Rendered skills should not contain personal references like HeyJobs."""
    project_dir = get_project_dir()
    skills_template_dir = project_dir / "skills" / "_templates"

    env = Environment(
        loader=FileSystemLoader(str(skills_template_dir)),
        keep_trailing_newline=True,
    )
    template_vars = _default_template_vars()

    personal_terms = ["HeyJobs", "Professional vault", "For Me Personally"]

    for skill in SKILLS:
        skill_dir = skills_template_dir / skill
        for template_file in skill_dir.iterdir():
            if template_file.is_file() and template_file.suffix == ".md":
                rel_path = f"{skill}/{template_file.name}"
                template = env.get_template(rel_path)
                rendered = template.render(**template_vars)
                for term in personal_terms:
                    assert term not in rendered, (
                        f"Personal reference '{term}' found in {rel_path}"
                    )


def test_check_dependencies_warns_for_manual_skill_tools_only():
    """Missing claude and yt-dlp are warnings about manual skills; npx is not checked."""
    with patch("shutil.which", return_value=None):
        warnings = _check_dependencies()

    assert len(warnings) == 2
    claude = next(w for w in warnings if "claude" in w)
    assert "manual" in claude and "scheduled pipeline does not" in claude
    yt = next(w for w in warnings if "yt-dlp" in w)
    assert "brew install yt-dlp" in yt and "manual" in yt
    assert not any("npx" in w for w in warnings)


def test_check_dependencies_returns_empty_when_all_present():
    """_check_dependencies should return empty list when all tools found."""
    with patch("shutil.which", return_value="/usr/local/bin/tool"):
        warnings = _check_dependencies()

    assert warnings == []


LLM = {"keychain_service": "melious-api-key", "model": "deepseek-v4.1-flash", "base_url": "https://x/v1"}
SECRET = "sk-secret-123"


class _FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def complete(self, messages, max_tokens):
        self.calls.append(messages)
        if self.error:
            raise self.error


def test_melious_check_warns_with_instructions_when_key_missing():
    from src.llm import FatalRunError
    from src.setup import _check_melious

    def no_key(service, env_file):
        raise FatalRunError("No Melious API key found.")

    ok, message = _check_melious({"llm": LLM}, resolve_key=no_key, make_client=lambda c, k: _FakeClient())

    assert ok is False
    assert "MELIOUS_API_KEY=" in message and ".env" in message
    assert "security add-generic-password" in message and "melious-api-key" in message


def test_melious_check_reports_accepted_key_without_printing_it():
    from src.setup import _check_melious

    client = _FakeClient()
    ok, message = _check_melious({"llm": LLM}, resolve_key=lambda s, e: SECRET, make_client=lambda c, k: client)

    assert ok is True
    assert "deepseek-v4.1-flash" in message
    assert SECRET not in message
    assert len(client.calls) == 1


def test_melious_check_reports_rejected_key_or_model():
    from src.llm import FatalRunError
    from src.setup import _check_melious

    client = _FakeClient(FatalRunError("Melious API rejected the request (HTTP 404): Model not found"))
    ok, message = _check_melious({"llm": LLM}, resolve_key=lambda s, e: SECRET, make_client=lambda c, k: client)

    assert ok is False
    assert "HTTP 404" in message
    assert SECRET not in message


def test_melious_check_reports_unreachable_api():
    from src.llm import LLMError
    from src.setup import _check_melious

    client = _FakeClient(LLMError("connection error: refused"))
    ok, message = _check_melious({"llm": LLM}, resolve_key=lambda s, e: SECRET, make_client=lambda c, k: client)

    assert ok is False
    assert "connection error" in message


def test_copy_interest_profile_skips_when_exists(tmp_path):
    """If interest profile already exists in vault, template should NOT be copied."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    existing_profile = vault_dir / "interest-profile.md"
    existing_profile.write_text("My existing profile content")

    config = {
        "vault": {"path": str(vault_dir)},
        "profile": {"interest_profile": "interest-profile.md"},
    }

    _copy_interest_profile(config)

    # Content should remain unchanged — template was not copied over it
    assert existing_profile.read_text() == "My existing profile content"


def test_copy_interest_profile_creates_when_missing(tmp_path):
    """If interest profile does not exist in vault, template should be copied."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    profile_path = vault_dir / "interest-profile.md"

    config = {
        "vault": {"path": str(vault_dir)},
        "profile": {"interest_profile": "interest-profile.md"},
    }

    _copy_interest_profile(config)

    assert profile_path.exists()
    # Should contain template content, not be empty
    assert len(profile_path.read_text()) > 0


def test_copy_interest_profile_uses_custom_name(tmp_path):
    """When config has a custom profile name, _copy_interest_profile should check that path."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    custom_profile = vault_dir / "About Me.md"
    custom_profile.write_text("Custom profile content")

    config = {
        "vault": {"path": str(vault_dir)},
        "profile": {"interest_profile": "About Me.md"},
    }

    _copy_interest_profile(config)

    # The custom profile should be untouched — not overwritten by template
    assert custom_profile.read_text() == "Custom profile content"
    # The default profile name should NOT have been created
    assert not (vault_dir / "interest-profile.md").exists()


def test_crontab_template_renders():
    """Crontab template should render with correct schedule values."""
    project_dir = get_project_dir()
    env = Environment(
        loader=FileSystemLoader(str(project_dir / "templates")),
        keep_trailing_newline=True,
    )

    template_vars = {
        "project_dir": "/opt/ai-research-assistant",
        "home_dir": "/home/testuser",
        "schedule": {"hour": 7, "minute": 30},
    }

    template = env.get_template("crontab-entry.j2")
    rendered = template.render(**template_vars)

    assert "30 7 * * *" in rendered
    assert "/opt/ai-research-assistant/scripts/run.sh" in rendered
    assert "/home/testuser/.claude/logs/ai-research-assistant.log" in rendered
    assert "# ai-research-assistant scheduled run" in rendered


def test_install_cron_appends_entry():
    """_install_cron should read existing crontab and append new entry."""
    config = {"schedule": {"hour": 8, "minute": 15}}

    existing_crontab = "0 * * * * /usr/bin/some-other-job\n"

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        if cmd == ["crontab", "-l"]:
            result.returncode = 0
            result.stdout = existing_crontab
            return result
        if cmd == ["crontab", "-"]:
            mock_subprocess_run.written = kwargs.get("input", "")
            result.returncode = 0
            return result
        return result

    mock_subprocess_run.written = None

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        _install_cron(config)

    written = mock_subprocess_run.written
    assert written is not None
    # Should contain original entry
    assert "/usr/bin/some-other-job" in written
    # Should contain new marker and cron entry
    assert "# ai-research-assistant scheduled run" in written
    assert "15 8 * * *" in written
    assert "scripts/run.sh" in written


def test_install_cron_replaces_existing_entry():
    """_install_cron should replace existing entry when marker is already present."""
    config = {"schedule": {"hour": 9, "minute": 45}}

    existing_crontab = (
        "0 * * * * /usr/bin/some-other-job\n"
        "# ai-research-assistant scheduled run\n"
        "0 6 * * * /old/path/scripts/run.sh >> /old/log 2>&1\n"
    )

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        if cmd == ["crontab", "-l"]:
            result.returncode = 0
            result.stdout = existing_crontab
            return result
        if cmd == ["crontab", "-"]:
            mock_subprocess_run.written = kwargs.get("input", "")
            result.returncode = 0
            return result
        return result

    mock_subprocess_run.written = None

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        _install_cron(config)

    written = mock_subprocess_run.written
    assert written is not None
    # Should still contain the other job
    assert "/usr/bin/some-other-job" in written
    # Old entry should be gone
    assert "/old/path/scripts/run.sh" not in written
    # New entry should be present
    assert "45 9 * * *" in written
    assert "# ai-research-assistant scheduled run" in written
    # Marker should appear exactly once
    assert written.count("# ai-research-assistant scheduled run") == 1
