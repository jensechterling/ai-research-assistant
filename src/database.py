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

    def is_processed(self, entry_guid: str) -> bool:
        """Check if entry has already been processed."""
        cursor = self.execute(
            "SELECT 1 FROM processed_entries WHERE entry_guid = ?",
            (entry_guid,),
        )
        return cursor.fetchone() is not None

    def mark_processed(
        self,
        entry_guid: str,
        feed_id: int,
        entry_url: str,
        entry_title: str | None,
        note_path: Path | None,
    ) -> None:
        """Mark entry as successfully processed."""
        self.execute(
            """INSERT INTO processed_entries
               (entry_guid, feed_id, entry_url, entry_title, note_path)
               VALUES (?, ?, ?, ?, ?)""",
            (entry_guid, feed_id, entry_url, entry_title, str(note_path) if note_path else None),
        )
        self.commit()

    def record_run_start(self) -> int:
        """Start a new pipeline run, return run_id."""
        cursor = self.execute(
            "INSERT INTO pipeline_runs (status) VALUES (?)",
            ("running",),
        )
        self.commit()
        return cursor.lastrowid

    def record_run_complete(self, run_id: int, processed: int, failed: int) -> None:
        """Mark pipeline run as complete with stats."""
        self.execute(
            """UPDATE pipeline_runs
               SET completed_at = CURRENT_TIMESTAMP,
                   items_processed = ?,
                   items_failed = ?,
                   status = ?
               WHERE id = ?""",
            (processed, failed, "completed", run_id),
        )
        self.commit()

    def get_last_successful_run(self) -> datetime | None:
        """Get timestamp of last completed pipeline run."""
        cursor = self.execute(
            """SELECT completed_at FROM pipeline_runs
               WHERE status = 'completed'
               ORDER BY completed_at DESC LIMIT 1"""
        )
        row = cursor.fetchone()
        if row and row["completed_at"]:
            return datetime.fromisoformat(row["completed_at"])
        return None

    # Backoff schedule: 1h, 4h, 12h, 24h
    BACKOFF_HOURS = [1, 4, 12, 24]

    def add_to_retry_queue(
        self,
        entry_guid: str,
        feed_id: int,
        entry_url: str,
        entry_title: str | None,
        category: str,
        error: str,
    ) -> None:
        """Add failed entry to retry queue with exponential backoff."""
        # Check if already in retry queue
        existing = self.execute(
            "SELECT retry_count FROM retry_queue WHERE entry_guid = ?",
            (entry_guid,),
        ).fetchone()

        if existing:
            retry_count = existing["retry_count"] + 1
            if retry_count >= len(self.BACKOFF_HOURS):
                # Give up - remove from queue
                self.execute("DELETE FROM retry_queue WHERE entry_guid = ?", (entry_guid,))
                self.commit()
                return
            backoff = self.BACKOFF_HOURS[retry_count]
            self.execute(
                """UPDATE retry_queue
                   SET retry_count = ?,
                       last_attempt_at = CURRENT_TIMESTAMP,
                       next_retry_at = datetime('now', '+' || ? || ' hours'),
                       last_error = ?
                   WHERE entry_guid = ?""",
                (retry_count, backoff, error, entry_guid),
            )
        else:
            backoff = self.BACKOFF_HOURS[0]
            self.execute(
                """INSERT INTO retry_queue
                   (entry_guid, feed_id, entry_url, entry_title, category,
                    last_attempt_at, next_retry_at, last_error)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP,
                           datetime('now', '+' || ? || ' hours'), ?)""",
                (entry_guid, feed_id, entry_url, entry_title, category, backoff, error),
            )
        self.commit()

    def get_retry_candidates(self) -> list[sqlite3.Row]:
        """Get entries due for retry (next_retry_at <= now)."""
        cursor = self.execute(
            """SELECT * FROM retry_queue
               WHERE next_retry_at <= CURRENT_TIMESTAMP
               ORDER BY next_retry_at"""
        )
        return cursor.fetchall()

    def remove_from_retry_queue(self, entry_guid: str) -> None:
        """Remove entry from retry queue (after successful processing)."""
        self.execute("DELETE FROM retry_queue WHERE entry_guid = ?", (entry_guid,))
        self.commit()
