"""Tests for pipeline file lock."""
import fcntl
import os
from unittest.mock import MagicMock

from src.pipeline import PipelineLock, PipelineLockError


def test_lock_acquired_and_pid_written(tmp_path):
    """Lock file is created with current PID."""
    lock_path = tmp_path / "pipeline.lock"
    lock = PipelineLock(lock_path)
    lock.acquire()

    assert lock_path.exists()
    assert lock_path.read_text().strip() == str(os.getpid())

    lock.release()


def test_second_invocation_blocked(tmp_path):
    """Second lock attempt raises PipelineLockError with PID."""
    lock_path = tmp_path / "pipeline.lock"

    first = PipelineLock(lock_path)
    first.acquire()

    second = PipelineLock(lock_path)
    try:
        second.acquire()
        assert False, "Expected PipelineLockError"
    except PipelineLockError as e:
        assert e.pid == os.getpid()
        assert str(os.getpid()) in str(e)
    finally:
        first.release()


def test_lock_released_after_context_manager(tmp_path):
    """Lock is released when context manager exits."""
    lock_path = tmp_path / "pipeline.lock"

    with PipelineLock(lock_path):
        pass

    # Should be acquirable again
    second = PipelineLock(lock_path)
    second.acquire()
    second.release()


def test_dry_run_does_not_acquire_lock(tmp_path, monkeypatch):
    """Dry run should not create or acquire the lock file."""
    lock_path = tmp_path / "pipeline.lock"
    monkeypatch.setattr("src.pipeline.LOCK_PATH", lock_path)

    from src.pipeline import run_pipeline

    db = MagicMock()
    db.get_last_successful_run.return_value = None
    db.get_retry_candidates.return_value = []

    feed_manager_mock = MagicMock()
    feed_manager_mock.fetch_new_entries.return_value = []
    monkeypatch.setattr("src.pipeline.FeedManager", lambda _db: feed_manager_mock)
    monkeypatch.setattr("src.pipeline.SkillRunner", MagicMock)

    run_pipeline(db, dry_run=True)

    # Lock file should not have been opened with flock
    if lock_path.exists():
        # Verify it's not locked
        fd = os.open(str(lock_path), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def test_force_bypasses_lock_with_warning(tmp_path, monkeypatch, caplog):
    """--force should proceed even when lock is held."""
    import logging

    lock_path = tmp_path / "pipeline.lock"
    monkeypatch.setattr("src.pipeline.LOCK_PATH", lock_path)

    # Hold the lock externally
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.pwrite(fd, b"99999", 0)

    from src.pipeline import run_pipeline

    db = MagicMock()
    db.get_last_successful_run.return_value = None
    db.get_retry_candidates.return_value = []
    db.record_run_start.return_value = 1

    feed_manager_mock = MagicMock()
    feed_manager_mock.fetch_new_entries.return_value = []
    monkeypatch.setattr("src.pipeline.FeedManager", lambda _db: feed_manager_mock)

    skill_runner_mock = MagicMock()
    skill_runner_mock.validate_skills.return_value = []
    monkeypatch.setattr("src.pipeline.SkillRunner", lambda: skill_runner_mock)

    with caplog.at_level(logging.WARNING, logger="src.pipeline"):
        result = run_pipeline(db, dry_run=False, force=True)

    assert result.processed == 0
    assert "Force override" in caplog.text

    # Clean up external lock
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
