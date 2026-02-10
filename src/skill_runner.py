"""Claude Code skill invocation."""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.config import get_folder, get_project_dir, get_skills_path, get_vault_path, load_config
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

    def __init__(self, config: dict | None = None):
        self._config = config or load_config()
        self._vault_path = get_vault_path(self._config)
        self._skills_path = get_skills_path()
        self._mcp_config_path = get_project_dir() / "config" / "mcp-minimal.json"
        self._skill_config = {
            "articles": {
                "skill": "article",
                "timeout": self._config["processing"]["article_timeout"],
                "output_folder": get_folder("article", self._config),
            },
            "youtube": {
                "skill": "youtube",
                "timeout": self._config["processing"]["youtube_timeout"],
                "output_folder": get_folder("youtube", self._config),
            },
            "podcasts": {
                "skill": "podcast",
                "timeout": self._config["processing"]["podcast_timeout"],
                "output_folder": get_folder("clippings", self._config),
            },
        }

    @property
    def vault_path(self) -> Path:
        return self._vault_path

    def validate_skills(self) -> list[str]:
        """Check that all required skills are installed.

        Returns list of missing skill names. Empty list means all OK.
        """
        missing = []
        for category, config in self._skill_config.items():
            skill_name = config["skill"]
            skill_path = self._skills_path / skill_name
            if not skill_path.exists():
                missing.append(skill_name)
        return missing

    def run_skill(self, entry: Entry) -> SkillResult:
        """Invoke appropriate skill for entry and verify output."""
        config = self._skill_config[entry.category]
        skill_name = config["skill"]
        timeout = config["timeout"]
        output_folder = config["output_folder"]

        try:
            result = subprocess.run(
                [
                    "claude",
                    "--mcp-config",
                    str(self._mcp_config_path),
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
            # Error might be in stdout or stderr depending on the CLI
            error_output = result.stderr.strip() or result.stdout.strip()
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill exited with code {result.returncode}: {error_output[:200]}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Extract note path from skill output
        note_path = self._extract_note_path(result.stdout, output_folder)

        if note_path is None:
            return SkillResult(
                success=False,
                note_path=None,
                error="Skill completed but no note path found in output",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        if not note_path.exists():
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill reported creating note but file not found: {note_path}",
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

    def _extract_note_path(self, stdout: str, folder: str) -> Path | None:
        """Extract note path from skill output.

        Skills typically output lines like:
        - "Done. I've saved the article analysis to **Clippings/Title.md**."
        - "Done. I've created the note at `Clippings/Title.md`."
        - "Note saved to Clippings/Youtube extractions/Title.md"
        - "Successfully wrote note to Clippings/Article extractions/Title.md"
        """
        output_dir = self._vault_path / folder

        # Pattern 1: **Folder/Filename.md** (bold markdown)
        bold_pattern = r"\*\*([^*]+\.md)\*\*"
        match = re.search(bold_pattern, stdout)
        if match:
            relative_path = match.group(1)
            if "/" in relative_path:
                return self._vault_path / relative_path
            return output_dir / relative_path

        # Pattern 2: `Folder/Filename.md` (backtick code format)
        backtick_pattern = r"`([^`]+\.md)`"
        match = re.search(backtick_pattern, stdout)
        if match:
            relative_path = match.group(1)
            if "/" in relative_path:
                return self._vault_path / relative_path
            return output_dir / relative_path

        # Pattern 3: Folder/path.md (allows spaces in filename, stops at .md)
        path_pattern = rf"({re.escape(folder)}/[^\n]+?\.md)"
        match = re.search(path_pattern, stdout)
        if match:
            return self._vault_path / match.group(1)

        # Pattern 4: "wrote/written/saved/created ... to/at/in path.md"
        action_pattern = r"(?:wrote|written|saved|created)[^\n]*?(?:to|at|in)\s+([A-Za-z][^\n]+?\.md)"
        match = re.search(action_pattern, stdout, re.IGNORECASE)
        if match:
            filename = match.group(1).strip()
            if "/" in filename:
                return self._vault_path / filename
            return output_dir / filename

        return None
