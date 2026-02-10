"""Tests for feed manager module."""
import tempfile
from pathlib import Path


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
