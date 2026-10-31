"""Feed subscription management."""
from pathlib import Path
from datetime import datetime
import hashlib
import logging
import xml.etree.ElementTree as ET

import feedparser
import httpx

from src.config import load_config
from src.database import Database
from src.http_fetch import FetchError, fetch
from src.models import Entry, Feed

logger = logging.getLogger(__name__)
MAX_FEED_BYTES = 20_000_000
FEED_DEADLINE_SECONDS = 60


class FeedManager:
    """Manages feed subscriptions and fetches new entries."""

    def __init__(self, db: Database, http_client: httpx.Client | None = None):
        """Initialize with database connection and an optional HTTP client."""
        self.db = db
        if http_client is None:
            feeds_config = load_config()["feeds"]
            http_client = httpx.Client(
                timeout=feeds_config["request_timeout"],
                headers={"User-Agent": feeds_config["user_agent"]},
                follow_redirects=True,
            )
        self.http_client = http_client

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
                logger.warning(f"Error fetching {feed.url}: {e}")

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
            parsed = self._parse(url)
            return parsed.feed.get("title")
        except Exception:
            return None

    def _parse(self, url: str) -> feedparser.FeedParserDict:
        """Download a feed with the client's timeout and parse it."""
        response = fetch(self.http_client, url, max_bytes=MAX_FEED_BYTES, deadline_seconds=FEED_DEADLINE_SECONDS)
        if response.status != 200:
            raise FetchError(f"HTTP {response.status}", permanent=False)
        return feedparser.parse(response.content)

    @staticmethod
    def _item_content(item) -> str:
        """Return the item's full content when present, else its summary."""
        content = item.get("content")
        if content and content[0].get("value"):
            return content[0]["value"]
        return item.get("summary", "")

    def _fetch_feed_entries(self, feed: Feed) -> list[Entry]:
        """Fetch entries from a single feed."""
        parsed = self._parse(feed.url)
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
                    content=self._item_content(item),
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
