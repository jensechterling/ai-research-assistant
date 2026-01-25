"""Feed subscription management."""
from pathlib import Path
from datetime import datetime
import hashlib
import xml.etree.ElementTree as ET

import feedparser

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
