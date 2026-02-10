"""Tests for database module."""
import tempfile
from pathlib import Path


def test_database_creates_tables():
    """Database should create all required tables on init."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Check tables exist
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row[0] for row in tables}

        assert "feeds" in table_names
        assert "processed_entries" in table_names
        assert "retry_queue" in table_names
        assert "pipeline_runs" in table_names


def test_is_processed_returns_false_for_new_entry():
    """is_processed should return False for entries not in database."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        assert db.is_processed("some-guid-123") is False


def test_mark_processed_and_is_processed():
    """mark_processed should make is_processed return True."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # First add a feed
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Mark entry as processed
        db.mark_processed(
            entry_guid="guid-123",
            feed_id=1,
            entry_url="https://example.com/article",
            entry_title="Test Article",
            note_path=Path("/vault/Clippings/test.md"),
        )

        assert db.is_processed("guid-123") is True


def test_record_run_start_and_complete():
    """Pipeline run should be trackable from start to completion."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Start a run
        run_id = db.record_run_start()
        assert run_id == 1

        # Complete the run
        db.record_run_complete(run_id, processed=5, failed=1)

        # Verify
        row = db.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        assert row["status"] == "completed"
        assert row["items_processed"] == 5
        assert row["items_failed"] == 1


def test_get_last_successful_run():
    """get_last_successful_run should return timestamp of last completed run."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # No runs yet
        assert db.get_last_successful_run() is None

        # Add a completed run
        run_id = db.record_run_start()
        db.record_run_complete(run_id, processed=3, failed=0)

        # Should now have a timestamp
        last_run = db.get_last_successful_run()
        assert last_run is not None


def test_add_to_retry_queue_and_get_candidates():
    """Failed entries should be added to retry queue with backoff."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        # Add a feed first
        db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            ("https://example.com/feed", "Test Feed", "articles"),
        )
        db.commit()

        # Add to retry queue
        db.add_to_retry_queue(
            entry_guid="guid-456",
            feed_id=1,
            entry_url="https://example.com/article",
            entry_title="Failed Article",
            category="articles",
            error="Connection timeout",
        )

        # Should not be immediately available (1 hour backoff)
        candidates = db.get_retry_candidates()
        assert len(candidates) == 0

        # Manually set next_retry to now for testing
        db.execute(
            "UPDATE retry_queue SET next_retry_at = CURRENT_TIMESTAMP WHERE entry_guid = ?",
            ("guid-456",),
        )
        db.commit()

        # Now should be available
        candidates = db.get_retry_candidates()
        assert len(candidates) == 1
        assert candidates[0]["entry_guid"] == "guid-456"
