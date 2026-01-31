"""Claude Code skill invocation."""
import re
import subprocess
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
            "timeout": 300,
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
    SKILLS_PATH = Path.home() / ".claude" / "skills"
    # Minimal MCP config - only loads Obsidian server for faster startup
    MCP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp-minimal.json"

    def validate_skills(self) -> list[str]:
        """Check that all required skills are installed.

        Returns list of missing skill names. Empty list means all OK.
        """
        missing = []
        for category, config in self.SKILL_CONFIG.items():
            skill_name = config["skill"]
            skill_path = self.SKILLS_PATH / skill_name
            if not skill_path.exists():
                missing.append(skill_name)
        return missing

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
                    "--mcp-config",
                    str(self.MCP_CONFIG_PATH),
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
        output_dir = self.VAULT_PATH / folder

        # Pattern 1: **Folder/Filename.md** (bold markdown)
        bold_pattern = r"\*\*([^*]+\.md)\*\*"
        match = re.search(bold_pattern, stdout)
        if match:
            relative_path = match.group(1)
            if "/" in relative_path:
                return self.VAULT_PATH / relative_path
            return output_dir / relative_path

        # Pattern 2: `Folder/Filename.md` (backtick code format)
        backtick_pattern = r"`([^`]+\.md)`"
        match = re.search(backtick_pattern, stdout)
        if match:
            relative_path = match.group(1)
            if "/" in relative_path:
                return self.VAULT_PATH / relative_path
            return output_dir / relative_path

        # Pattern 3: Folder/path.md (allows spaces in filename, stops at .md)
        path_pattern = rf"({re.escape(folder)}/[^\n]+?\.md)"
        match = re.search(path_pattern, stdout)
        if match:
            return self.VAULT_PATH / match.group(1)

        # Pattern 4: "wrote/written/saved/created ... to/at/in path.md"
        action_pattern = r"(?:wrote|written|saved|created)[^\n]*?(?:to|at|in)\s+([A-Za-z][^\n]+?\.md)"
        match = re.search(action_pattern, stdout, re.IGNORECASE)
        if match:
            filename = match.group(1).strip()
            if "/" in filename:
                return self.VAULT_PATH / filename
            return output_dir / filename

        return None
