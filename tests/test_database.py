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
