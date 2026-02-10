"""Tests for skill runner module."""
from datetime import datetime
from pathlib import Path
import subprocess
from unittest.mock import patch, MagicMock

from src.models import Entry


def _test_config():
    """Return a minimal config for testing."""
    return {
        "vault": {"path": "/tmp/test-vault"},
        "folders": {
            "youtube": "Clippings/Youtube extractions",
            "podcast": "Clippings/Podcast extractions",
            "article": "Clippings/Article extractions",
            "knowledge_base": "Knowledge Base",
            "daily_notes": "Daily Notes",
            "clippings": "Clippings",
            "templates": "Templates",
        },
        "profile": {"interest_profile": "interest-profile.md"},
        "processing": {
            "article_timeout": 300,
            "youtube_timeout": 300,
            "podcast_timeout": 600,
            "evaluate_batch_size": 6,
            "evaluate_timeout": 600,
        },
        "retry": {"max_attempts": 4, "backoff_hours": [1, 4, 12, 24]},
        "feeds": {"request_timeout": 30, "user_agent": "AI-Research-Assistant/1.0"},
        "schedule": {"hour": 6, "minute": 0},
    }


def test_skill_runner_selects_correct_skill():
    """SkillRunner should select skill based on category."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())

    assert runner._skill_config["articles"]["skill"] == "article"
    assert runner._skill_config["youtube"]["skill"] == "youtube"
    assert runner._skill_config["podcasts"]["skill"] == "podcast"


def test_skill_runner_runs_command():
    """SkillRunner should invoke claude CLI with correct arguments."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())

    entry = Entry(
        guid="test-123",
        title="Test Article",
        url="https://example.com/article",
        content="",
        author=None,
        published_at=datetime.now(),
        feed_id=1,
        feed_title="Test Feed",
        category="articles",
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Done. I've saved the article analysis to **Clippings/Test Article.md**.",
            stderr="",
        )

        # Mock path.exists() to return True
        with patch.object(Path, "exists", return_value=True):
            runner.run_skill(entry)

        # Verify command was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "claude" in call_args
        assert "--dangerously-skip-permissions" in call_args
        assert "/article https://example.com/article" in " ".join(call_args)


def test_extract_note_path_bold_markdown():
    """Should extract path from **Folder/File.md** format."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    stdout = "Done. I've saved the article analysis to **Clippings/Test Article.md**."

    path = runner._extract_note_path(stdout, "Clippings")

    assert path is not None
    assert path.name == "Test Article.md"
    assert "Clippings" in str(path)


def test_extract_note_path_nested_folder():
    """Should extract path from nested folder format."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    stdout = "Note saved to **Clippings/Youtube extractions/Video Title.md**"

    path = runner._extract_note_path(stdout, "Clippings/Youtube extractions")

    assert path is not None
    assert path.name == "Video Title.md"
    assert "Youtube extractions" in str(path)


def test_extract_note_path_backtick_format():
    """Should extract path from `Folder/File.md` backtick format."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    stdout = "Done. I've created the note at `Clippings/Netflix Article.md`."

    path = runner._extract_note_path(stdout, "Clippings")

    assert path is not None
    assert path.name == "Netflix Article.md"
    assert "Clippings" in str(path)


def test_validate_skills_returns_missing():
    """Should return list of missing skills."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    # Point to a non-existent path to simulate missing skills
    runner._skills_path = Path("/nonexistent/path")

    missing = runner.validate_skills()

    assert "article" in missing
    assert "youtube" in missing
    assert "podcast" in missing


def _make_entry(category="articles"):
    """Create a test entry for a given category."""
    return Entry(
        guid="test-123",
        title="Test Article",
        url="https://example.com/article",
        content="",
        author=None,
        published_at=datetime.now(),
        feed_id=1,
        feed_title="Test Feed",
        category=category,
    )


def test_run_skill_returns_failure_on_timeout():
    """run_skill should return SkillResult with error on timeout."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    entry = _make_entry()

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 300)):
        result = runner.run_skill(entry)

    assert result.success is False
    assert "timed out" in result.error


def test_run_skill_returns_failure_on_nonzero_exit():
    """run_skill should return SkillResult with error on non-zero exit code."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    entry = _make_entry()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Something went wrong",
        )
        result = runner.run_skill(entry)

    assert result.success is False
    assert "exited with code 1" in result.error


def test_run_skill_returns_failure_when_claude_not_found():
    """run_skill should return SkillResult with error when claude CLI is missing."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    entry = _make_entry()

    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = runner.run_skill(entry)

    assert result.success is False
    assert "not found" in result.error


def test_run_skill_returns_failure_when_no_note_path_found():
    """run_skill should fail when skill output doesn't contain a note path."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    entry = _make_entry()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="I did some work but forgot to mention where I saved it.",
            stderr="",
        )
        result = runner.run_skill(entry)

    assert result.success is False
    assert "no note path found" in result.error


def test_run_skill_returns_failure_when_note_file_missing():
    """run_skill should fail when skill reports a path but file doesn't exist."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    entry = _make_entry()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Saved to **Clippings/Article extractions/Test.md**.",
            stderr="",
        )
        # Path.exists returns False (file not created)
        result = runner.run_skill(entry)

    assert result.success is False
    assert "file not found" in result.error


def test_run_skill_reads_timeout_from_config():
    """run_skill should use the timeout from config for the given category."""
    from src.skill_runner import SkillRunner

    config = _test_config()
    config["processing"]["youtube_timeout"] = 999
    runner = SkillRunner(config=config)
    entry = _make_entry(category="youtube")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Saved to **Clippings/Youtube extractions/Video.md**.",
            stderr="",
        )
        with patch.object(Path, "exists", return_value=True):
            runner.run_skill(entry)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["timeout"] == 999


def test_extract_note_path_returns_none_for_no_match():
    """_extract_note_path should return None when no pattern matches."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    result = runner._extract_note_path("No file info here.", "Clippings")

    assert result is None


def test_vault_path_property():
    """SkillRunner.vault_path should return the configured vault path."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner(config=_test_config())
    assert runner.vault_path == Path("/tmp/test-vault")
