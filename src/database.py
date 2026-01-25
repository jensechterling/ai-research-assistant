"""SQLite database for pipeline state management."""
import sqlite3
from pathlib import Path
from datetime import datetime


class Database:
    """SQLite database wrapper for pipeline state."""

    SCHEMA = """
    -- Feed subscriptions
    CREATE TABLE IF NOT EXISTS feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE NOT NULL,
        title TEXT,
        category TEXT NOT NULL CHECK (category IN ('articles', 'youtube', 'podcasts')),
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_fetched_at TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
    );

    -- Processed entries (prevents reprocessing)
    CREATE TABLE IF NOT EXISTS processed_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_guid TEXT UNIQUE NOT NULL,
        feed_id INTEGER NOT NULL,
        entry_url TEXT NOT NULL,
        entry_title TEXT,
        published_at TIMESTAMP,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        note_path TEXT,
        FOREIGN KEY (feed_id) REFERENCES feeds(id)
    );

    -- Retry queue for failed items
    CREATE TABLE IF NOT EXISTS retry_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_guid TEXT UNIQUE NOT NULL,
        feed_id INTEGER NOT NULL,
        entry_url TEXT NOT NULL,
        entry_title TEXT,
        category TEXT NOT NULL,
        first_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_attempt_at TIMESTAMP,
        next_retry_at TIMESTAMP,
        retry_count INTEGER DEFAULT 0,
        last_error TEXT,
        FOREIGN KEY (feed_id) REFERENCES feeds(id)
    );

    -- Pipeline run history (for catch-up logic)
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        items_fetched INTEGER DEFAULT 0,
        items_processed INTEGER DEFAULT 0,
        items_failed INTEGER DEFAULT 0,
        status TEXT CHECK (status IN ('running', 'completed', 'failed'))
    );

    -- Indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_processed_guid ON processed_entries(entry_guid);
    CREATE INDEX IF NOT EXISTS idx_retry_next ON retry_queue(next_retry_at);
    CREATE INDEX IF NOT EXISTS idx_feeds_category ON feeds(category);
    """

    def __init__(self, db_path: Path):
        """Initialize database, creating tables if needed."""
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute SQL and return cursor."""
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        """Commit current transaction."""
        self.conn.commit()

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()
