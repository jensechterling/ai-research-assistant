"""Setup wizard for first-time installation and upgrades."""
import os
import shutil
import stat
from pathlib import Path

import click
import yaml
from jinja2 import Environment, FileSystemLoader

from src.config import get_project_dir, is_configured, load_config


SKILLS = ["article", "youtube", "podcast", "evaluate-knowledge"]


def _render_templates(config: dict) -> None:
    """Render all Jinja2 templates using config values."""
    project_dir = get_project_dir()
    template_vars = {
        "vault_path": str(Path(config["vault"]["path"]).expanduser()),
        "project_dir": str(project_dir),
        "uv_path": shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv"),
        "home_dir": str(Path.home()),
        "folders": config["folders"],
        "profile": config["profile"],
        "schedule": config.get("schedule", {"hour": 6, "minute": 0}),
    }

    # Render skill templates
    skills_template_dir = project_dir / "skills" / "_templates"
    env = Environment(
        loader=FileSystemLoader(str(skills_template_dir)),
        keep_trailing_newline=True,
    )

    for skill in SKILLS:
        output_dir = project_dir / "skills" / skill
        output_dir.mkdir(parents=True, exist_ok=True)

        template_skill_dir = skills_template_dir / skill
        if not template_skill_dir.exists():
            click.echo(f"  Warning: template not found for {skill}, skipping")
            continue

        for template_file in template_skill_dir.iterdir():
            if template_file.is_file() and template_file.suffix == ".md":
                rel_path = f"{skill}/{template_file.name}"
                template = env.get_template(rel_path)
                rendered = template.render(**template_vars)
                (output_dir / template_file.name).write_text(rendered)

    # Render infrastructure templates
    infra_env = Environment(
        loader=FileSystemLoader(str(project_dir / "templates")),
        keep_trailing_newline=True,
    )

    # mcp-minimal.json
    template = infra_env.get_template("mcp-minimal.json.j2")
    rendered = template.render(**template_vars)
    (project_dir / "config" / "mcp-minimal.json").write_text(rendered)

    # run.sh
    template = infra_env.get_template("run.sh.j2")
    rendered = template.render(**template_vars)
    run_sh = project_dir / "scripts" / "run.sh"
    run_sh.write_text(rendered)
    run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

    # launchd plist
    template = infra_env.get_template("com.claude.ai-research-assistant.plist.j2")
    rendered = template.render(**template_vars)
    (project_dir / "templates" / "com.claude.ai-research-assistant.plist").write_text(rendered)


def _install_skills() -> None:
    """Create symlinks from generated skills to ~/.claude/skills/."""
    project_dir = get_project_dir()
    skills_dir = Path.home() / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    for skill in SKILLS:
        source = project_dir / "skills" / skill
        target = skills_dir / skill

        if not source.exists():
            click.echo(f"  Warning: {skill} not generated, skipping symlink")
            continue

        if target.is_symlink():
            target.unlink()
            click.echo(f"  Updating: {skill}")
        elif target.exists():
            click.echo(f"  Warning: {target} exists as directory, skipping")
            continue
        else:
            click.echo(f"  Installing: {skill}")

        target.symlink_to(source)


def _copy_interest_profile(config: dict) -> None:
    """Copy interest profile template to vault if it doesn't exist."""
    vault_path = Path(config["vault"]["path"]).expanduser()
    profile_name = config["profile"]["interest_profile"]
    profile_path = vault_path / profile_name

    if profile_path.exists():
        click.echo(f"  Interest profile already exists: {profile_path}")
        return

    template_path = get_project_dir() / "templates" / "interest-profile.md"
    if not template_path.exists():
        click.echo("  Warning: interest-profile.md template not found")
        return

    profile_path.write_text(template_path.read_text())
    click.echo(f"  Created interest profile: {profile_path}")
    click.echo("  Please fill in your work and personal context for personalized suggestions.")


def _check_dependencies() -> list[str]:
    """Check for required external tools. Returns list of warnings."""
    warnings = []

    if not shutil.which("claude"):
        warnings.append("claude CLI not found. Install from: https://docs.anthropic.com/en/docs/claude-code")

    if not shutil.which("yt-dlp"):
        warnings.append("yt-dlp not found (needed for YouTube skill). Install: brew install yt-dlp")

    if not shutil.which("npx"):
        warnings.append("npx not found (needed for Obsidian MCP). Install Node.js: brew install node")

    return warnings


def _install_cron(config: dict) -> None:
    """Install cron job for scheduled runs (Linux)."""
    import subprocess as sp

    project_dir = get_project_dir()
    template_vars = {
        "project_dir": str(project_dir),
        "home_dir": str(Path.home()),
        "schedule": config.get("schedule", {"hour": 6, "minute": 0}),
    }

    # Render cron entry from template
    env = Environment(
        loader=FileSystemLoader(str(project_dir / "templates")),
        keep_trailing_newline=True,
    )
    template = env.get_template("crontab-entry.j2")
    cron_entry = template.render(**template_vars).strip()

    # Read existing crontab
    marker = "# ai-research-assistant scheduled run"
    try:
        result = sp.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        click.echo("  Warning: crontab not found. Cannot install cron job.")
        return

    # Replace or append
    lines = existing.splitlines()
    new_lines = []
    skip_next = False
    for line in lines:
        if marker in line:
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        new_lines.append(line)

    new_lines.append(marker)
    new_lines.append(cron_entry.split("\n")[-1])  # The actual cron line (without marker)

    # Write back
    new_crontab = "\n".join(new_lines) + "\n"
    sp.run(["crontab", "-"], input=new_crontab, text=True, check=True)

    schedule = config.get("schedule", {"hour": 6, "minute": 0})
    click.echo(f"  Cron job installed: daily at {schedule['hour']:02d}:{schedule['minute']:02d}")


@click.command()
@click.option("--install-schedule", is_flag=True, help="Install daily scheduling (launchd on macOS, cron on Linux)")
def setup(install_schedule: bool):
    """Set up the AI Research Assistant — configure vault, install skills, check dependencies."""
    project_dir = get_project_dir()

    if is_configured():
        # Upgrade mode: re-render from existing config
        click.echo("Existing configuration found. Re-rendering templates...")
        config = load_config()
        click.echo(f"  Vault: {config['vault']['path']}")
    else:
        # First-time setup
        click.echo("Welcome to AI Research Assistant for Obsidian!")
        click.echo()

        # Vault path (required)
        vault_path = click.prompt(
            "Path to your Obsidian vault",
            type=str,
        )
        vault_path = str(Path(vault_path).expanduser())

        if not Path(vault_path).exists():
            if not click.confirm(f"Directory {vault_path} does not exist. Continue anyway?"):
                raise click.Abort()

        # Folder customization
        click.echo()
        click.echo("Default folder structure:")
        defaults = load_config()
        for key, value in defaults["folders"].items():
            click.echo(f"  {key}: {value}")

        config = {"vault": {"path": vault_path}}

        if click.confirm("\nCustomize folder paths?", default=False):
            config["folders"] = {}
            for key, default_value in defaults["folders"].items():
                custom = click.prompt(f"  {key}", default=default_value)
                if custom != default_value:
                    config["folders"][key] = custom

        # Interest profile
        click.echo()
        if click.confirm("Do you have an existing interest profile in your vault?", default=False):
            while True:
                profile_path_str = click.prompt("  Vault-relative path to your profile (e.g., About Me.md)")
                full_path = Path(vault_path) / profile_path_str
                if full_path.exists():
                    config["profile"] = {"interest_profile": profile_path_str}
                    click.echo(f"  Linked: {profile_path_str}")
                    break
                else:
                    click.echo(f"  File not found: {full_path}")
                    if not click.confirm("  Try again?", default=True):
                        click.echo("  Skipping — you can set profile.interest_profile in config/user.yaml later.")
                        break

        # Write user config
        user_config_path = project_dir / "config" / "user.yaml"
        with open(user_config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        click.echo(f"\nConfiguration saved to: {user_config_path}")

        # Reload merged config
        config = load_config()

    # Render templates
    click.echo("\nRendering templates...")
    _render_templates(config)
    click.echo("  Templates rendered.")

    # Install skills
    click.echo("\nInstalling skills to ~/.claude/skills/...")
    _install_skills()

    # Copy interest profile
    click.echo("\nChecking interest profile...")
    _copy_interest_profile(config)

    # Check dependencies
    click.echo("\nChecking dependencies...")
    warnings = _check_dependencies()
    if warnings:
        for w in warnings:
            click.echo(f"  Warning: {w}")
    else:
        click.echo("  All dependencies found.")

    # Optional: install schedule
    if install_schedule:
        import sys

        click.echo("\nInstalling schedule...")

        if sys.platform == "darwin":
            # macOS: launchd plist
            plist_source = project_dir / "templates" / "com.claude.ai-research-assistant.plist"
            plist_target = Path.home() / "Library" / "LaunchAgents" / "com.claude.ai-research-assistant.plist"

            if plist_target.exists():
                os.system(f'launchctl unload "{plist_target}" 2>/dev/null')

            shutil.copy2(plist_source, plist_target)
            os.system(f'launchctl load "{plist_target}"')

            schedule = config.get("schedule", {"hour": 6, "minute": 0})
            click.echo(f"  Pipeline scheduled daily at {schedule['hour']:02d}:{schedule['minute']:02d}")

        elif sys.platform == "linux":
            _install_cron(config)

        else:
            click.echo("  Automated scheduling is not supported on this platform.")
            click.echo("  To run the pipeline on a schedule, set up a task manually:")
            click.echo(f"    Command: {project_dir}/scripts/run.sh")
            schedule = config.get("schedule", {"hour": 6, "minute": 0})
            click.echo(f"    Schedule: daily at {schedule['hour']:02d}:{schedule['minute']:02d}")
            click.echo("  On Windows, use Task Scheduler. See README for details.")

    # Done
    click.echo("\nSetup complete!")
    click.echo()
    click.echo("Next steps:")
    if not is_configured():
        click.echo("  1. Fill in your interest profile in the vault")
        click.echo("  2. Add feeds: ai-research-assistant feeds add URL -c articles")
        click.echo("  3. Run pipeline: ai-research-assistant run --dry-run")
    else:
        click.echo("  Templates re-rendered. Pipeline ready.")
    click.echo()
    click.echo("Upgrade: git pull && uv sync && ai-research-assistant setup")
