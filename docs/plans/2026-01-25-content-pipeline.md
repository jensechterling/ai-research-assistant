# Content Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated daily pipeline that fetches RSS content, delegates to Claude Code skills for summarization, and writes structured notes to Obsidian.

**Architecture:** Python CLI using SQLite for state management + feedparser for RSS. Invokes Claude Code CLI (`/article`, `/youtube`, `/podcast` skills) for all content processing. launchd schedules daily runs with pmset wake.

**Tech Stack:** Python 3.11+, SQLite, feedparser, click, uv (package manager)

**Spec Reference:** `/Users/jens.echterling/GitHub/Development/AI research assistant/docs/Content Pipeline - Build Specification.md`

**Skills Reference:** `/Users/jens.echterling/GitHub/Productivity/Skills/obsidian-workflow-skills/skills/`

---

## Phase 1: Project Setup + Database

### Task 1.1: Create Repository Structure

**Files:**
- Create: `/Users/jens.echterling/GitHub/Development/AI research assistant/`
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p /Users/jens.echterling/GitHub/Development/AI research assistant/{src,skills/article,config,templates,scripts,exports,data,logs}
touch /Users/jens.echterling/GitHub/Development/AI research assistant/logs/.gitkeep
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "content-pipeline"
version = "0.1.0"
description = "Automated content aggregation pipeline for Obsidian"
requires-python = ">=3.11"

dependencies = [
    "feedparser>=6.0",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "click>=8.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
]

[project.scripts]
content-pipeline = "src.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 3: Create .gitignore**

```
# Environment
.env
.venv/

# Runtime data
data/

# Logs
logs/*.log

# Python
__pycache__/
*.pyc
.pytest_cache/

# macOS
.DS_Store

# IDE
.idea/
.vscode/
```

**Step 4: Create .env.example**

```bash
# No secrets required for basic operation
# Claude Code CLI handles its own authentication

# Optional: Override database location
# PIPELINE_DB_PATH=/custom/path/pipeline.db
```

**Step 5: Create src/__init__.py**

```python
"""Content Pipeline - Automated content aggregation for Obsidian."""
```

**Step 6: Initialize git and uv**

Run:
```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git init
uv sync
```

**Step 7: Commit**

```bash
git add -A
git commit -m "chore: initialize project structure with pyproject.toml"
```

---

### Task 1.2: Implement Database Schema

**Files:**
- Create: `src/database.py`
- Create: `tests/__init__.py`
- Create: `tests/test_database.py`

**Step 1: Create tests/__init__.py**

```python
"""Content Pipeline tests."""
```

**Step 2: Write failing test for database initialization**

Create `tests/test_database.py`:

```python
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
```

**Step 3: Run test to verify it fails**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.database'"

**Step 4: Write minimal database implementation**

Create `src/database.py`:

```python
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
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py -v`

Expected: PASS

**Step 6: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/database.py tests/
git commit -m "feat: add SQLite database with schema for feeds, entries, retry queue"
```

---

### Task 1.3: Add Database CRUD Operations

**Files:**
- Modify: `src/database.py`
- Modify: `tests/test_database.py`

**Step 1: Write failing test for is_processed**

Add to `tests/test_database.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py::test_is_processed_returns_false_for_new_entry -v`

Expected: FAIL with "AttributeError: 'Database' object has no attribute 'is_processed'"

**Step 3: Add is_processed and mark_processed methods**

Add to `src/database.py` (inside Database class):

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/database.py tests/test_database.py
git commit -m "feat: add is_processed and mark_processed methods"
```

---

### Task 1.4: Add Pipeline Run Tracking

**Files:**
- Modify: `src/database.py`
- Modify: `tests/test_database.py`

**Step 1: Write failing test for pipeline run tracking**

Add to `tests/test_database.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py::test_record_run_start_and_complete -v`

Expected: FAIL with "AttributeError"

**Step 3: Add pipeline run methods**

Add to `src/database.py` (inside Database class):

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/database.py tests/test_database.py
git commit -m "feat: add pipeline run tracking methods"
```

---

### Task 1.5: Add Retry Queue Methods

**Files:**
- Modify: `src/database.py`
- Modify: `tests/test_database.py`

**Step 1: Write failing test for retry queue**

Add to `tests/test_database.py`:

```python
from datetime import timedelta


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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py::test_add_to_retry_queue_and_get_candidates -v`

Expected: FAIL with "AttributeError"

**Step 3: Add retry queue methods**

Add to `src/database.py` (inside Database class):

```python
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
        from datetime import timedelta

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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_database.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/database.py tests/test_database.py
git commit -m "feat: add retry queue with exponential backoff"
```

---

## Phase 2: Feed Manager + CLI

### Task 2.1: Create Entry Dataclass

**Files:**
- Create: `src/models.py`

**Step 1: Create models module**

Create `src/models.py`:

```python
"""Data models for content pipeline."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Entry:
    """RSS feed entry."""

    guid: str
    title: str
    url: str
    content: str
    author: str | None
    published_at: datetime | None
    feed_id: int
    feed_title: str
    category: str  # articles, youtube, podcasts


@dataclass
class Feed:
    """Feed subscription."""

    id: int
    url: str
    title: str | None
    category: str
    is_active: bool = True
```

**Step 2: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/models.py
git commit -m "feat: add Entry and Feed dataclasses"
```

---

### Task 2.2: Implement Feed Manager

**Files:**
- Create: `src/feed_manager.py`
- Create: `tests/test_feed_manager.py`

**Step 1: Write failing test for add_feed**

Create `tests/test_feed_manager.py`:

```python
"""Tests for feed manager module."""
import tempfile
from pathlib import Path

import pytest


def test_add_feed_stores_in_database():
    """add_feed should store feed in database with auto-detected title."""
    from src.database import Database
    from src.feed_manager import FeedManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        fm = FeedManager(db)

        # Add a real feed (will fetch title)
        feed = fm.add_feed("https://stratechery.com/feed/", category="articles")

        assert feed.url == "https://stratechery.com/feed/"
        assert feed.category == "articles"
        assert feed.title is not None  # Should have fetched title


def test_add_feed_auto_detects_youtube_category():
    """add_feed should auto-detect youtube category from URL."""
    from src.database import Database
    from src.feed_manager import FeedManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        fm = FeedManager(db)

        feed = fm.add_feed(
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC123",
            category=None,  # Let it auto-detect
        )

        assert feed.category == "youtube"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_feed_manager.py::test_add_feed_auto_detects_youtube_category -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement FeedManager**

Create `src/feed_manager.py`:

```python
"""Feed subscription management."""
from pathlib import Path
from datetime import datetime
import hashlib
import xml.etree.ElementTree as ET

import feedparser
import httpx

from src.database import Database
from src.models import Entry, Feed


class FeedManager:
    """Manages feed subscriptions and fetches new entries."""

    def __init__(self, db: Database):
        """Initialize with database connection."""
        self.db = db

    def add_feed(self, url: str, category: str | None = None) -> Feed:
        """Add a new feed subscription."""
        # Auto-detect category if not provided
        if category is None:
            category = self._detect_category(url)

        # Fetch feed to get title
        title = self._fetch_feed_title(url)

        # Insert into database
        cursor = self.db.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            (url, title, category),
        )
        self.db.commit()

        return Feed(
            id=cursor.lastrowid,
            url=url,
            title=title,
            category=category,
            is_active=True,
        )

    def remove_feed(self, url: str) -> None:
        """Remove a feed subscription."""
        self.db.execute("DELETE FROM feeds WHERE url = ?", (url,))
        self.db.commit()

    def list_feeds(self, category: str | None = None) -> list[Feed]:
        """List all feeds, optionally filtered by category."""
        if category:
            cursor = self.db.execute(
                "SELECT * FROM feeds WHERE category = ? AND is_active = 1",
                (category,),
            )
        else:
            cursor = self.db.execute("SELECT * FROM feeds WHERE is_active = 1")

        return [
            Feed(
                id=row["id"],
                url=row["url"],
                title=row["title"],
                category=row["category"],
                is_active=bool(row["is_active"]),
            )
            for row in cursor.fetchall()
        ]

    def fetch_new_entries(self) -> list[Entry]:
        """Fetch all new (unprocessed) entries from all active feeds."""
        entries = []
        feeds = self.list_feeds()

        for feed in feeds:
            try:
                feed_entries = self._fetch_feed_entries(feed)
                # Filter out already processed
                for entry in feed_entries:
                    if not self.db.is_processed(entry.guid):
                        entries.append(entry)
            except Exception as e:
                # Log error but continue with other feeds
                print(f"Error fetching {feed.url}: {e}")

        return entries

    def _detect_category(self, url: str) -> str:
        """Detect feed category from URL pattern."""
        if "youtube.com/feeds" in url:
            return "youtube"
        # Could add podcast detection based on feed content
        return "articles"

    def _fetch_feed_title(self, url: str) -> str | None:
        """Fetch feed and extract title."""
        try:
            parsed = feedparser.parse(url)
            return parsed.feed.get("title")
        except Exception:
            return None

    def _fetch_feed_entries(self, feed: Feed) -> list[Entry]:
        """Fetch entries from a single feed."""
        parsed = feedparser.parse(feed.url)
        entries = []

        for item in parsed.entries:
            # Generate GUID from id or link
            guid = item.get("id") or item.get("link") or ""
            if not guid:
                # Hash the title + link as fallback
                guid = hashlib.sha256(
                    f"{item.get('title', '')}{item.get('link', '')}".encode()
                ).hexdigest()[:16]

            # Parse published date
            published = None
            if hasattr(item, "published_parsed") and item.published_parsed:
                published = datetime(*item.published_parsed[:6])

            entries.append(
                Entry(
                    guid=guid,
                    title=item.get("title", "Untitled"),
                    url=item.get("link", ""),
                    content=item.get("summary", ""),
                    author=item.get("author"),
                    published_at=published,
                    feed_id=feed.id,
                    feed_title=feed.title or "",
                    category=feed.category,
                )
            )

        # Update last_fetched_at
        self.db.execute(
            "UPDATE feeds SET last_fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
            (feed.id,),
        )
        self.db.commit()

        return entries

    def export_opml(self, output_path: Path) -> None:
        """Export all feeds to OPML format."""
        feeds = self.list_feeds()

        root = ET.Element("opml", version="2.0")
        head = ET.SubElement(root, "head")
        ET.SubElement(head, "title").text = "Content Pipeline Feeds"
        body = ET.SubElement(root, "body")

        # Group by category
        categories = {}
        for feed in feeds:
            if feed.category not in categories:
                categories[feed.category] = []
            categories[feed.category].append(feed)

        for category, cat_feeds in categories.items():
            outline = ET.SubElement(body, "outline", text=category, title=category)
            for feed in cat_feeds:
                ET.SubElement(
                    outline,
                    "outline",
                    type="rss",
                    text=feed.title or feed.url,
                    title=feed.title or feed.url,
                    xmlUrl=feed.url,
                )

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(output_path, encoding="utf-8", xml_declaration=True)

    def import_opml(self, opml_path: Path) -> int:
        """Import feeds from OPML file, return count added."""
        tree = ET.parse(opml_path)
        root = tree.getroot()
        count = 0

        for outline in root.findall(".//outline[@xmlUrl]"):
            url = outline.get("xmlUrl")
            if url:
                try:
                    # Get category from parent outline
                    parent = outline.find("..")
                    category = parent.get("text", "articles") if parent is not None else "articles"
                    self.add_feed(url, category=category)
                    count += 1
                except Exception:
                    pass  # Skip duplicates or errors

        return count
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_feed_manager.py -v`

Expected: All PASS (or skip if network unavailable)

**Step 5: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/feed_manager.py tests/test_feed_manager.py
git commit -m "feat: add FeedManager with CRUD and OPML support"
```

---

### Task 2.3: Implement CLI

**Files:**
- Create: `src/main.py`
- Create: `config/settings.yaml`

**Step 1: Create settings.yaml**

Create `config/settings.yaml`:

```yaml
# Obsidian vault
obsidian:
  vault_path: "~/Obsidian/Professional vault"
  clippings_folder: "Clippings"
  youtube_folder: "Clippings/Youtube extractions"

# Processing settings
processing:
  article_timeout_seconds: 120
  youtube_timeout_seconds: 300
  podcast_timeout_seconds: 600

# Retry settings
retry:
  max_attempts: 4
  backoff_hours: [1, 4, 12, 24]

# Feed polling
feeds:
  request_timeout_seconds: 30
  user_agent: "ContentPipeline/1.0"
```

**Step 2: Create CLI entry point**

Create `src/main.py`:

```python
"""CLI entry point for content pipeline."""
from pathlib import Path

import click

from src.database import Database
from src.feed_manager import FeedManager


def get_db() -> Database:
    """Get database instance."""
    db_path = Path(__file__).parent.parent / "data" / "pipeline.db"
    return Database(db_path)


@click.group()
def cli():
    """Content Pipeline - Import articles, videos, and podcasts to Obsidian."""
    pass


# === Pipeline Commands ===


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be processed without doing it")
def run(dry_run: bool):
    """Run the content pipeline."""
    # Placeholder - will be implemented in Phase 4
    click.echo("Pipeline not yet implemented. Use --dry-run to preview.")
    if dry_run:
        db = get_db()
        fm = FeedManager(db)
        entries = fm.fetch_new_entries()
        for entry in entries:
            click.echo(f"[DRY RUN] Would process: {entry.title} ({entry.category})")
        click.echo(f"Total: {len(entries)} entries")


@cli.command()
def status():
    """Show pipeline status: pending items, retry queue, last run."""
    db = get_db()
    fm = FeedManager(db)

    # Last run info
    last_run = db.get_last_successful_run()
    if last_run:
        click.echo(f"Last successful run: {last_run.strftime('%Y-%m-%d %H:%M')}")
    else:
        click.echo("No previous runs")

    # Pending items
    entries = fm.fetch_new_entries()
    click.echo(f"Pending items: {len(entries)}")

    # Retry queue
    retry_entries = db.get_retry_candidates()
    click.echo(f"In retry queue: {len(retry_entries)}")

    # Feed counts
    feeds = fm.list_feeds()
    by_category = {}
    for f in feeds:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    click.echo(f"Feeds: {by_category}")


# === Feed Management Commands ===


@cli.group()
def feeds():
    """Manage feed subscriptions."""
    pass


@feeds.command("add")
@click.argument("url")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["articles", "youtube", "podcasts"]),
    help="Feed category (auto-detected if not specified)",
)
def feeds_add(url: str, category: str | None):
    """Add a new feed subscription."""
    db = get_db()
    fm = FeedManager(db)

    try:
        feed = fm.add_feed(url, category)
        click.echo(f"Added: {feed.title} ({feed.category})")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@feeds.command("remove")
@click.argument("url")
def feeds_remove(url: str):
    """Remove a feed subscription."""
    db = get_db()
    fm = FeedManager(db)

    fm.remove_feed(url)
    click.echo(f"Removed: {url}")


@feeds.command("list")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["articles", "youtube", "podcasts"]),
    help="Filter by category",
)
def feeds_list(category: str | None):
    """List all feed subscriptions."""
    db = get_db()
    fm = FeedManager(db)

    feed_list = fm.list_feeds(category)
    for feed in feed_list:
        click.echo(f"[{feed.category}] {feed.title}")
        click.echo(f"    {feed.url}")


@feeds.command("export")
@click.option(
    "--output",
    "-o",
    default="exports/feeds.opml",
    help="Output file path (default: exports/feeds.opml)",
)
def feeds_export(output: str):
    """Export feeds to OPML format."""
    db = get_db()
    fm = FeedManager(db)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fm.export_opml(output_path)
    click.echo(f"Exported to: {output_path}")


@feeds.command("import")
@click.argument("opml_file", type=click.Path(exists=True))
def feeds_import(opml_file: str):
    """Import feeds from OPML file."""
    db = get_db()
    fm = FeedManager(db)

    count = fm.import_opml(Path(opml_file))
    click.echo(f"Imported {count} feeds")


if __name__ == "__main__":
    cli()
```

**Step 3: Test CLI works**

Run:
```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
uv run content-pipeline --help
uv run content-pipeline feeds --help
```

Expected: Help text displayed

**Step 4: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/main.py config/
git commit -m "feat: add CLI with feed management commands"
```

---

## Phase 3: Article Skill

### Task 3.1: Create Article Skill Files

**Files:**
- Create: `skills/article/SKILL.md`
- Create: `skills/article/article-workflow.md`

**Step 1: Create SKILL.md**

Create `skills/article/SKILL.md` - copy content from the spec's "skills/article/SKILL.md" section.

**Step 2: Create article-workflow.md**

Create `skills/article/article-workflow.md` - copy content from the spec's "skills/article/article-workflow.md" section.

**Step 3: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add skills/
git commit -m "feat: add /article skill definition"
```

**Step 4: Install skill to Claude Code**

Determine where Claude Code loads skills from and symlink or copy:

```bash
# Location varies - check Claude Code documentation
# Example: ln -s /path/to/skills/article ~/.claude/skills/article
```

**Step 5: Test skill manually**

```bash
claude --print "/article https://stratechery.com/2024/the-ai-search-race/"
```

Verify note created in `~/Obsidian/Professional vault/Clippings/`

---

## Phase 4: Skill Runner + Pipeline

### Task 4.1: Implement Skill Runner

**Files:**
- Create: `src/skill_runner.py`
- Create: `tests/test_skill_runner.py`

**Step 1: Write failing test**

Create `tests/test_skill_runner.py`:

```python
"""Tests for skill runner module."""
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models import Entry
from datetime import datetime


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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_skill_runner.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement SkillRunner**

Create `src/skill_runner.py`:

```python
"""Claude Code skill invocation."""
import subprocess
import time
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
            "timeout": 120,
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
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill exited with code {result.returncode}: {result.stderr}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Verify note was created
        note_path = self._find_created_note(entry.title, output_folder)

        if note_path is None:
            return SkillResult(
                success=False,
                note_path=None,
                error="Skill completed but no note found in expected location",
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

    def _find_created_note(self, title: str, folder: str) -> Path | None:
        """Find the note created by the skill."""
        output_dir = self.VAULT_PATH / folder
        safe_title = self._sanitize_filename(title)

        # Check for exact match
        expected_path = output_dir / f"{safe_title}.md"
        if expected_path.exists():
            return expected_path

        # Check for recently modified files (within last 60 seconds)
        now = time.time()
        for path in output_dir.glob("*.md"):
            if now - path.stat().st_mtime < 60:
                return path

        return None

    def _sanitize_filename(self, title: str) -> str:
        """Remove/replace characters invalid in filenames."""
        replacements = {
            "/": "-",
            "\\": "-",
            ":": " -",
            "*": "",
            "?": "",
            '"': "'",
            "<": "",
            ">": "",
            "|": "-",
        }
        result = title
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result.strip()[:100]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/jens.echterling/GitHub/Development/AI research assistant && uv run pytest tests/test_skill_runner.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/skill_runner.py tests/test_skill_runner.py
git commit -m "feat: add SkillRunner for Claude Code CLI invocation"
```

---

### Task 4.2: Implement Main Pipeline

**Files:**
- Create: `src/pipeline.py`
- Modify: `src/main.py`

**Step 1: Create pipeline.py**

Create `src/pipeline.py`:

```python
"""Main pipeline orchestration."""
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.database import Database
from src.feed_manager import FeedManager
from src.models import Entry
from src.skill_runner import SkillRunner, SkillResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result from running the pipeline."""

    processed: int = 0
    failed: int = 0
    retried: int = 0
    skipped: int = 0
    created_notes: list[Path] = field(default_factory=list)
    failures: list[tuple[Entry, str]] = field(default_factory=list)


def run_pipeline(db: Database, dry_run: bool = False) -> PipelineResult:
    """Execute the content pipeline."""
    feed_manager = FeedManager(db)
    skill_runner = SkillRunner()

    # Check for catch-up (missed runs)
    last_run = db.get_last_successful_run()
    if last_run:
        hours_since = (datetime.now() - last_run).total_seconds() / 3600
        if hours_since > 36:
            logger.warning(f"Catch-up mode: {hours_since:.1f} hours since last run")

    # Start pipeline run
    run_id = db.record_run_start()

    # Fetch new entries + retry candidates
    new_entries = feed_manager.fetch_new_entries()
    retry_rows = db.get_retry_candidates()

    # Convert retry rows to Entry objects
    retry_entries = []
    for row in retry_rows:
        retry_entries.append(
            Entry(
                guid=row["entry_guid"],
                title=row["entry_title"] or "Untitled",
                url=row["entry_url"],
                content="",
                author=None,
                published_at=None,
                feed_id=row["feed_id"],
                feed_title="",
                category=row["category"],
            )
        )

    all_entries = new_entries + retry_entries

    logger.info(f"Found {len(new_entries)} new entries, {len(retry_entries)} retries")

    if dry_run:
        for entry in all_entries:
            logger.info(f"[DRY RUN] Would process: {entry.title} ({entry.category})")
        return PipelineResult(skipped=len(all_entries))

    # Process entries sequentially
    result = PipelineResult()

    for entry in all_entries:
        is_retry = entry in retry_entries

        try:
            skill_result = skill_runner.run_skill(entry)

            if skill_result.success:
                # Mark as processed
                db.mark_processed(
                    entry_guid=entry.guid,
                    feed_id=entry.feed_id,
                    entry_url=entry.url,
                    entry_title=entry.title,
                    note_path=skill_result.note_path,
                )

                # Remove from retry queue if it was a retry
                if is_retry:
                    db.remove_from_retry_queue(entry.guid)
                    result.retried += 1

                result.created_notes.append(skill_result.note_path)
                result.processed += 1
                logger.info(f"✓ Processed: {entry.title}")
            else:
                # Add to retry queue
                db.add_to_retry_queue(
                    entry_guid=entry.guid,
                    feed_id=entry.feed_id,
                    entry_url=entry.url,
                    entry_title=entry.title,
                    category=entry.category,
                    error=skill_result.error or "Unknown error",
                )
                result.failed += 1
                result.failures.append((entry, skill_result.error or "Unknown error"))
                logger.error(f"✗ Failed: {entry.title} - {skill_result.error}")

        except Exception as e:
            db.add_to_retry_queue(
                entry_guid=entry.guid,
                feed_id=entry.feed_id,
                entry_url=entry.url,
                entry_title=entry.title,
                category=entry.category,
                error=str(e),
            )
            result.failed += 1
            result.failures.append((entry, str(e)))
            logger.error(f"✗ Exception processing {entry.title}: {e}")

    # Post-process with /evaluate-knowledge
    if result.created_notes:
        logger.info(f"Running /evaluate-knowledge on {len(result.created_notes)} new notes")
        file_list = " ".join(f'"{p}"' for p in result.created_notes)
        try:
            subprocess.run(
                [
                    "claude",
                    "--print",
                    "--dangerously-skip-permissions",
                    f"/evaluate-knowledge {file_list}",
                ],
                timeout=600,
                capture_output=True,
            )
        except Exception as e:
            logger.warning(f"evaluate-knowledge failed: {e}")

    # Record run completion
    db.record_run_complete(run_id, result.processed, result.failed)

    # Send notification
    send_notification(result)

    return result


def send_notification(result: PipelineResult) -> None:
    """Send macOS notification with pipeline results."""
    if result.failed == 0:
        title = "Content Pipeline ✓"
        message = f"Processed {result.processed} items"
    else:
        title = "Content Pipeline ⚠️"
        message = f"Processed {result.processed}, Failed {result.failed}"

    if result.failures:
        first_fail = result.failures[0]
        message += f"\nFirst failure: {first_fail[0].title[:30]}..."

    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            capture_output=True,
        )
    except Exception:
        pass  # Ignore notification failures
```

**Step 2: Update CLI to use pipeline**

Modify `src/main.py` - replace the `run` command:

```python
@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be processed without doing it")
def run(dry_run: bool):
    """Run the content pipeline."""
    import logging

    from src.pipeline import run_pipeline

    logging.basicConfig(level=logging.INFO)

    db = get_db()
    result = run_pipeline(db, dry_run=dry_run)

    click.echo(f"Processed: {result.processed}, Failed: {result.failed}")
    if result.retried:
        click.echo(f"Retried: {result.retried}")
```

**Step 3: Test pipeline**

Run:
```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
uv run content-pipeline run --dry-run
```

**Step 4: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add src/pipeline.py src/main.py
git commit -m "feat: add main pipeline with skill invocation and notifications"
```

---

## Phase 5: Automation Scripts

### Task 5.1: Create Shell Scripts

**Files:**
- Create: `scripts/run.sh`
- Create: `scripts/install.sh`
- Create: `scripts/uninstall.sh`
- Create: `templates/com.claude.content-pipeline.plist`

**Step 1: Create run.sh**

Create `scripts/run.sh`:

```bash
#!/bin/bash
set -e

# Navigate to project directory
cd /Users/jens.echterling/GitHub/Development/AI research assistant

# Load environment variables (if any)
if [ -f .env ]; then
    source .env
fi

# Run pipeline
uv run content-pipeline run

# Export OPML and commit to GitHub (weekly backup - Mondays)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq 1 ]; then
    uv run content-pipeline feeds export
    git add exports/feeds.opml
    git diff --cached --quiet || git commit -m "Weekly OPML backup $(date +%Y-%m-%d)"
    git push
fi
```

**Step 2: Create install.sh**

Create `scripts/install.sh`:

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing content-pipeline..."

# Create directories
mkdir -p ~/.claude/logs
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/exports"

# Make scripts executable
chmod +x "$PROJECT_DIR/scripts/run.sh"
chmod +x "$PROJECT_DIR/scripts/uninstall.sh"

# Copy launchd plist
cp "$PROJECT_DIR/templates/com.claude.content-pipeline.plist" ~/Library/LaunchAgents/

# Load the job
launchctl load ~/Library/LaunchAgents/com.claude.content-pipeline.plist

# Set wake schedule (requires sudo)
echo "Setting wake schedule..."
sudo pmset repeat wake MTWRFSU 05:55:00

echo ""
echo "✓ Installed successfully!"
echo ""
echo "  Pipeline will run daily at 6:00 AM"
echo "  Machine will wake at 5:55 AM"
echo ""
echo "  Manual run:   cd $PROJECT_DIR && uv run content-pipeline run"
echo "  Check status: cd $PROJECT_DIR && uv run content-pipeline status"
echo "  View logs:    tail -f ~/.claude/logs/content-pipeline.log"
```

**Step 3: Create uninstall.sh**

Create `scripts/uninstall.sh`:

```bash
#!/bin/bash
set -e

echo "Uninstalling content-pipeline..."

# Unload launchd job
launchctl unload ~/Library/LaunchAgents/com.claude.content-pipeline.plist 2>/dev/null || true

# Remove plist
rm -f ~/Library/LaunchAgents/com.claude.content-pipeline.plist

# Optionally remove wake schedule
read -p "Remove wake schedule? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo pmset repeat cancel
    echo "Wake schedule removed"
fi

echo "✓ Uninstalled"
```

**Step 4: Create launchd plist**

Create `templates/com.claude.content-pipeline.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.content-pipeline</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/jens.echterling/GitHub/Development/AI research assistant/scripts/run.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/jens.echterling/.claude/logs/content-pipeline.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/jens.echterling/.claude/logs/content-pipeline.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>/Users/jens.echterling</string>
    </dict>
</dict>
</plist>
```

**Step 5: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
chmod +x scripts/*.sh
git add scripts/ templates/
git commit -m "feat: add automation scripts and launchd configuration"
```

---

## Phase 6: Final Setup

### Task 6.1: Create README

**Files:**
- Create: `README.md`

**Step 1: Create README.md**

```markdown
# Content Pipeline

Automated content aggregation pipeline that fetches articles, YouTube videos, and podcasts from RSS feeds and creates structured Obsidian notes using Claude Code skills.

## Features

- **Feed Management**: Subscribe to RSS feeds via CLI
- **Multi-Format Support**: Articles, YouTube, Podcasts
- **Personalized Summaries**: Uses your interest profile for relevant insights
- **Automatic Retry**: Failed items retry with exponential backoff
- **Daily Automation**: Runs automatically via launchd

## Quick Start

```bash
# Install dependencies
uv sync

# Add some feeds
uv run content-pipeline feeds add "https://stratechery.com/feed/" -c articles

# Run manually
uv run content-pipeline run

# Check status
uv run content-pipeline status
```

## Installation

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/content-pipeline.git
cd content-pipeline

# Install dependencies
uv sync

# Install automation (runs daily at 6 AM)
./scripts/install.sh
```

## Commands

| Command | Description |
|---------|-------------|
| `content-pipeline run` | Run the pipeline |
| `content-pipeline run --dry-run` | Preview without processing |
| `content-pipeline status` | Show pending items and stats |
| `content-pipeline feeds add URL` | Add a feed |
| `content-pipeline feeds list` | List all feeds |
| `content-pipeline feeds export` | Export to OPML |

## Dependencies

- Python 3.11+
- uv (package manager)
- Claude Code CLI

## License

MIT
```

**Step 2: Commit**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
git add README.md
git commit -m "docs: add README with setup instructions"
```

---

### Task 6.2: Push to GitHub

**Step 1: Create GitHub repo**

```bash
gh repo create content-pipeline --private --source=. --push
```

**Step 2: Add initial feeds**

```bash
cd /Users/jens.echterling/GitHub/Development/AI research assistant
uv run content-pipeline feeds add "https://stratechery.com/feed/" -c articles
uv run content-pipeline feeds add "https://www.lennysnewsletter.com/feed" -c articles
uv run content-pipeline feeds export
git add exports/feeds.opml
git commit -m "chore: add initial feed subscriptions"
git push
```

---

## Summary

**Total Tasks:** 14

**Phase 1:** Project setup, SQLite database with CRUD operations
**Phase 2:** Feed manager with feedparser, CLI commands
**Phase 3:** Article skill following existing patterns
**Phase 4:** Skill runner, main pipeline with retry logic
**Phase 5:** Automation scripts, launchd configuration
**Phase 6:** Documentation, GitHub setup

Each task follows TDD: write failing test → implement → verify → commit.
