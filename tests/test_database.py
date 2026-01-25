"""Tests for database module."""
import tempfile
from pathlib import Path

import pytest


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
