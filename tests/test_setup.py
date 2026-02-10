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
        "uv_path": "/usr/local/bin/uv",
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
    """Infrastructure templates (mcp, run.sh, plist) should render with defaults."""
    project_dir = get_project_dir()
    template_vars = _default_template_vars()

    env = Environment(
        loader=FileSystemLoader(str(project_dir / "templates")),
        keep_trailing_newline=True,
    )

    infra_templates = [
        "mcp-minimal.json.j2",
        "run.sh.j2",
        "com.claude.ai-research-assistant.plist.j2",
    ]

    for name in infra_templates:
        template = env.get_template(name)
        rendered = template.render(**template_vars)
        assert len(rendered) > 0, f"Rendered {name} is empty"


def test_mcp_template_contains_vault_path():
    """Rendered MCP config should contain the configured vault path."""
    project_dir = get_project_dir()
    template_vars = _default_template_vars()
    template_vars["vault_path"] = "/Users/someone/Obsidian/Vault"

    env = Environment(
        loader=FileSystemLoader(str(project_dir / "templates")),
        keep_trailing_newline=True,
    )
    template = env.get_template("mcp-minimal.json.j2")
    rendered = template.render(**template_vars)

    assert "/Users/someone/Obsidian/Vault" in rendered


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


def test_check_dependencies_returns_warnings_for_missing():
    """_check_dependencies should return warnings for missing tools."""
    with patch("shutil.which", return_value=None):
        warnings = _check_dependencies()

    assert len(warnings) == 3
    assert any("claude" in w for w in warnings)
    assert any("yt-dlp" in w for w in warnings)
    assert any("npx" in w for w in warnings)


def test_check_dependencies_returns_empty_when_all_present():
    """_check_dependencies should return empty list when all tools found."""
    with patch("shutil.which", return_value="/usr/local/bin/tool"):
        warnings = _check_dependencies()

    assert warnings == []


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
