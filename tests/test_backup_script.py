"""Tests for the weekly OPML backup guard in scripts/backup_feeds.sh."""
import shutil
import subprocess

from src.config import get_project_dir


def _repo(tmp_path, branch: str):
    (tmp_path / "scripts").mkdir()
    shutil.copy2(get_project_dir() / "scripts" / "backup_feeds.sh", tmp_path / "scripts")
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q", "-b", branch], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return git


def _commits(git) -> int:
    out = subprocess.run([*git, "rev-list", "--count", "HEAD"], capture_output=True, text=True, check=True)
    return int(out.stdout)


def _run(tmp_path, day: str) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "DAY_OF_WEEK": day, "UV": "false"}
    return subprocess.run(["bash", str(tmp_path / "scripts" / "backup_feeds.sh")],
                          capture_output=True, text=True, env=env)


def test_monday_on_feature_branch_skips_backup(tmp_path):
    git = _repo(tmp_path, "feat/api-pipeline")

    result = _run(tmp_path, "1")

    assert result.returncode == 0
    assert "Skipping weekly OPML backup" in result.stdout
    assert _commits(git) == 1


def test_other_weekday_does_nothing(tmp_path):
    git = _repo(tmp_path, "master")

    result = _run(tmp_path, "3")

    assert result.returncode == 0
    assert result.stdout == ""
    assert _commits(git) == 1


def test_monday_on_master_runs_export(tmp_path):
    _repo(tmp_path, "master")

    result = _run(tmp_path, "1")

    # UV=false makes the export step fail, which proves the backup path was entered
    assert result.returncode != 0
    assert "Skipping" not in result.stdout
