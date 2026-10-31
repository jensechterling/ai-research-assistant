"""Tests for feed downloading and entry content in FeedManager."""
import httpx
import pytest

from src.database import Database
from src.feed_manager import FeedManager

RSS_WITH_CONTENT = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Full Text Feed</title>
<item>
  <title>Long post</title>
  <link>https://example.com/long</link>
  <guid>https://example.com/long</guid>
  <description>Short teaser text.</description>
  <content:encoded><![CDATA[<p>Full body of the long post with many words.</p>]]></content:encoded>
</item>
</channel></rss>"""

ATOM_SUMMARY_ONLY = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Summary Feed</title>
<entry>
  <title>Link post</title>
  <link href="https://example.org/link"/>
  <id>tag:example.org,2026:1</id>
  <updated>2026-10-29T10:00:00Z</updated>
  <summary type="html">&lt;p&gt;Only a summary body.&lt;/p&gt;</summary>
</entry>
</feed>"""


def _client(routes: dict[str, bytes | Exception]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        result = routes[str(request.url)]
        if isinstance(result, Exception):
            raise result
        return httpx.Response(200, content=result)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _add_feed(db: Database, url: str) -> None:
    db.execute("INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)", (url, "t", "articles"))
    db.commit()


def test_entry_content_prefers_full_content_over_summary(db):
    _add_feed(db, "https://example.com/feed")
    fm = FeedManager(db, http_client=_client({"https://example.com/feed": RSS_WITH_CONTENT}))

    entries = fm.fetch_new_entries()

    assert len(entries) == 1
    assert "Full body of the long post" in entries[0].content


def test_entry_content_falls_back_to_summary(db):
    _add_feed(db, "https://example.org/atom")
    fm = FeedManager(db, http_client=_client({"https://example.org/atom": ATOM_SUMMARY_ONLY}))

    entries = fm.fetch_new_entries()

    assert len(entries) == 1
    assert "Only a summary body" in entries[0].content


def test_timed_out_feed_is_skipped_and_others_are_read(db):
    _add_feed(db, "https://slow.example/feed")
    _add_feed(db, "https://example.com/feed")
    fm = FeedManager(db, http_client=_client({
        "https://slow.example/feed": httpx.ReadTimeout("timed out"),
        "https://example.com/feed": RSS_WITH_CONTENT,
    }))

    entries = fm.fetch_new_entries()

    assert [e.url for e in entries] == ["https://example.com/long"]


def test_default_client_uses_configured_timeout_and_user_agent(db):
    fm = FeedManager(db)

    assert fm.http_client.timeout.read == 30
    assert fm.http_client.headers["User-Agent"] == "AI-Research-Assistant/1.0"


def test_oversized_feed_is_skipped_with_warning(db, caplog, monkeypatch):
    monkeypatch.setattr("src.feed_manager.MAX_FEED_BYTES", 100)
    _add_feed(db, "https://example.com/feed")
    fm = FeedManager(db, http_client=_client({"https://example.com/feed": RSS_WITH_CONTENT}))

    entries = fm.fetch_new_entries()

    assert entries == []
    assert "larger than" in caplog.text
