"""Claude Code skill invocation."""
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from src.models import Entry


@dataclass
class SkillResult:
    """Result from running a skill."""

    success: bool
    note_path: Path | None
    error: str | None
    stdout: str
    stderr: str


class SkillRunner:
    """Invoke Claude Code skills via CLI."""

    SKILL_CONFIG = {
        "articles": {
            "skill": "article",
            "timeout": 120,
            "output_folder": "Clippings",
        },
        "youtube": {
            "skill": "youtube",
            "timeout": 300,
            "output_folder": "Clippings/Youtube extractions",
        },
        "podcasts": {
            "skill": "podcast",
            "timeout": 600,
            "output_folder": "Clippings",
        },
    }

    VAULT_PATH = Path.home() / "Obsidian" / "Professional vault"

    def run_skill(self, entry: Entry) -> SkillResult:
        """Invoke appropriate skill for entry and verify output."""
        config = self.SKILL_CONFIG[entry.category]
        skill_name = config["skill"]
        timeout = config["timeout"]
        output_folder = config["output_folder"]

        try:
            result = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--dangerously-skip-permissions",
                    f"/{skill_name} {entry.url}",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill timed out after {timeout} seconds",
                stdout="",
                stderr="",
            )
        except FileNotFoundError:
            return SkillResult(
                success=False,
                note_path=None,
                error="Claude CLI not found. Ensure 'claude' is in PATH.",
                stdout="",
                stderr="",
            )

        if result.returncode != 0:
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill exited with code {result.returncode}: {result.stderr}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Verify note was created
        note_path = self._find_created_note(entry.title, output_folder)

        if note_path is None:
            return SkillResult(
                success=False,
                note_path=None,
                error="Skill completed but no note found in expected location",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        return SkillResult(
            success=True,
            note_path=note_path,
            error=None,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _find_created_note(self, title: str, folder: str) -> Path | None:
        """Find the note created by the skill."""
        output_dir = self.VAULT_PATH / folder
        safe_title = self._sanitize_filename(title)

        # Check for exact match
        expected_path = output_dir / f"{safe_title}.md"
        if expected_path.exists():
            return expected_path

        # Check for recently modified files (within last 60 seconds)
        now = time.time()
        for path in output_dir.glob("*.md"):
            if now - path.stat().st_mtime < 60:
                return path

        return None

    def _sanitize_filename(self, title: str) -> str:
        """Remove/replace characters invalid in filenames."""
        replacements = {
            "/": "-",
            "\\": "-",
            ":": " -",
            "*": "",
            "?": "",
            '"': "'",
            "<": "",
            ">": "",
            "|": "-",
        }
        result = title
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result.strip()[:100]
