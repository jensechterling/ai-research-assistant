"""Tests for article extraction."""
from datetime import datetime

import httpx
import pytest

from src.extraction import ExtractionError, extract_article
from src.models import Entry

URL = "https://www.example.com/post"


def _page(words: int, author: str | None = "Jane Doe", date: str | None = "2026-10-01") -> str:
    meta = ""
    if author:
        meta += f"<meta name='author' content='{author}'>"
    if date:
        meta += f"<meta property='article:published_time' content='{date}'>"
    paragraphs = []
    remaining = words
    while remaining > 0:
        n = min(40, remaining)
        paragraphs.append("<p>" + " ".join(f"w{remaining - i}" for i in range(n)) + "</p>")
        remaining -= n
    return (
        f"<html><head><title>Page Title</title>{meta}</head>"
        f"<body><article><h1>Page Title</h1>{''.join(paragraphs)}</article></body></html>"
    )


def _feed_html(words: int) -> str:
    return "<p>" + " ".join(f"f{i}" for i in range(words)) + "</p>"


def _entry(content: str = "", author: str | None = "Feed Author") -> Entry:
    return Entry(
        guid=URL,
        title="Entry Title",
        url=URL,
        content=content,
        author=author,
        published_at=datetime(2026, 10, 2, 8, 0),
        feed_id=1,
        feed_title="Example Blog",
        category="articles",
    )


def _client(status: int = 200, body: str = "", error: Exception | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if error is not None:
            raise error
        return httpx.Response(status, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _extract(entry: Entry, client: httpx.Client, max_words: int = 30000):
    return extract_article(entry, client, min_words=150, max_words=max_words)


def test_readable_page_uses_page_text_and_metadata():
    result = _extract(_entry(), _client(body=_page(400)))

    assert result.title == "Page Title"
    assert result.author == "Jane Doe"
    assert result.published == "2026-10-01"
    assert result.url == URL
    assert result.word_count >= 400
    assert result.from_feed is False
    assert result.truncated is False


def test_missing_page_metadata_falls_back_to_entry():
    result = _extract(_entry(), _client(body=_page(400, author=None, date=None)))

    assert result.author == "Feed Author"
    assert result.published == "2026-10-02"


def test_blocked_page_is_rescued_by_feed_text():
    result = _extract(_entry(content=_feed_html(1200)), _client(status=403, body="Forbidden"))

    assert result.from_feed is True
    assert result.word_count == 1200
    assert result.title == "Entry Title"
    assert result.site == "Example Blog"


def test_retry_entry_without_content_uses_page_only():
    result = _extract(_entry(content=""), _client(body=_page(300)))

    assert result.from_feed is False


def test_long_text_is_truncated_and_marked():
    result = _extract(_entry(), _client(body=_page(900)), max_words=500)

    assert result.word_count == 500
    assert len(result.text.split()) == 500
    assert result.truncated is True


@pytest.mark.parametrize("status", [401, 402, 403, 404, 410, 451])
def test_blocked_page_without_feed_text_is_permanent(status):
    with pytest.raises(ExtractionError) as exc:
        _extract(_entry(content=_feed_html(40)), _client(status=status, body="no"))

    assert exc.value.permanent is True
    assert "not extractable" in exc.value.reason


def test_short_post_is_permanent():
    with pytest.raises(ExtractionError) as exc:
        _extract(_entry(content=_feed_html(60)), _client(body=_page(60)))

    assert exc.value.permanent is True


@pytest.mark.parametrize("status", [429, 500, 503])
def test_server_error_without_feed_text_is_transient(status):
    with pytest.raises(ExtractionError) as exc:
        _extract(_entry(content=""), _client(status=status, body="busy"))

    assert exc.value.permanent is False
    assert str(status) in exc.value.reason


def test_network_timeout_without_feed_text_is_transient():
    with pytest.raises(ExtractionError) as exc:
        _extract(_entry(content=""), _client(error=httpx.ConnectTimeout("slow")))

    assert exc.value.permanent is False


def test_pdf_link_is_not_read_as_a_page_and_falls_back_to_feed_text():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7 " * 500)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = _extract(_entry(content=_feed_html(300)), client)

    assert result.from_feed is True


def test_pdf_link_without_feed_text_is_permanent():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ExtractionError) as exc:
        _extract(_entry(), client)

    assert exc.value.permanent
    assert "application/pdf" in exc.value.reason
