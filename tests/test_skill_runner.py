"""Tests for skill runner module."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models import Entry


def test_skill_runner_selects_correct_skill():
    """SkillRunner should select skill based on category."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()

    assert runner.SKILL_CONFIG["articles"]["skill"] == "article"
    assert runner.SKILL_CONFIG["youtube"]["skill"] == "youtube"
    assert runner.SKILL_CONFIG["podcasts"]["skill"] == "podcast"


def test_skill_runner_runs_command():
    """SkillRunner should invoke claude CLI with correct arguments."""
    from src.skill_runner import SkillRunner

    runner = SkillRunner()

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
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Mock _find_created_note to return a path
        with patch.object(runner, "_find_created_note", return_value=Path("/vault/test.md")):
            result = runner.run_skill(entry)

        # Verify command was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "claude" in call_args
        assert "--dangerously-skip-permissions" in call_args
        assert "/article https://example.com/article" in " ".join(call_args)
