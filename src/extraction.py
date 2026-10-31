"""Article text extraction without an LLM."""
import json
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura

from src.http_fetch import FetchError, fetch
from src.models import Entry

# HTTP statuses that mean the page itself will not become readable on retry
PERMANENT_STATUSES = {401, 402, 403, 404, 410, 451}
MAX_PAGE_BYTES = 10_000_000
PAGE_DEADLINE_SECONDS = 90
PAGE_TYPES = ("text/", "application/xhtml+xml")


@dataclass
class ExtractedArticle:
    """Main text and metadata of an article."""

    title: str
    author: str | None
    published: str | None  # ISO date (YYYY-MM-DD) when known
    site: str
    url: str
    text: str
    word_count: int
    from_feed: bool
    truncated: bool


class ExtractionError(Exception):
    """Extraction failed; permanent failures are not worth retrying."""

    def __init__(self, reason: str, permanent: bool):
        super().__init__(reason)
        self.reason = reason
        self.permanent = permanent


def extract_article(entry: Entry, client: httpx.Client, min_words: int, max_words: int) -> ExtractedArticle:
    """Extract the article for an entry from its page, falling back to the feed text."""
    page, page_problem, page_permanent = _fetch_page(entry, client)
    if page is not None and _word_count(page["text"]) >= min_words:
        return _build(entry, page, from_feed=False, max_words=max_words)

    feed_text = _html_to_text(entry.content)
    if _word_count(feed_text) >= min_words:
        return _build(entry, {"text": feed_text}, from_feed=True, max_words=max_words)

    if page_problem and not page_permanent:
        raise ExtractionError(f"transient: {page_problem}", permanent=False)
    detail = page_problem or "too little text"
    raise ExtractionError(f"not extractable ({detail})", permanent=True)


def _fetch_page(entry: Entry, client: httpx.Client) -> tuple[dict | None, str | None, bool]:
    """Return (extracted page data, problem description, problem is permanent)."""
    try:
        response = fetch(client, entry.url, max_bytes=MAX_PAGE_BYTES, deadline_seconds=PAGE_DEADLINE_SECONDS,
                         allowed_types=PAGE_TYPES)
    except FetchError as e:
        return None, e.reason, e.permanent

    if response.status != 200:
        permanent = response.status in PERMANENT_STATUSES
        return None, f"HTTP {response.status}", permanent

    extracted = trafilatura.extract(
        response.text, output_format="json", with_metadata=True, url=entry.url
    )
    if not extracted:
        return None, None, True
    return json.loads(extracted), None, True


def _build(entry: Entry, data: dict, from_feed: bool, max_words: int) -> ExtractedArticle:
    text, truncated = _truncate(data["text"], max_words)
    published = data.get("date") or (entry.published_at.date().isoformat() if entry.published_at else None)
    return ExtractedArticle(
        title=data.get("title") or entry.title,
        author=data.get("author") or entry.author,
        published=published,
        site=data.get("sitename") or entry.feed_title or _domain(entry.url),
        url=entry.url,
        text=text,
        word_count=_word_count(text),
        from_feed=from_feed,
        truncated=truncated,
    )


def _html_to_text(html: str) -> str:
    """Turn a feed's HTML fragment into plain text with paragraph breaks."""
    if not html or not html.strip():
        return ""
    text = trafilatura.extract(f"<html><body><article>{html}</article></body></html>")
    return text or ""


def _truncate(text: str, max_words: int) -> tuple[str, bool]:
    """Cut text to max_words words, keeping line breaks."""
    if _word_count(text) <= max_words:
        return text, False
    kept: list[str] = []
    remaining = max_words
    for line in text.splitlines():
        words = line.split()
        if len(words) >= remaining:
            kept.append(" ".join(words[:remaining]))
            break
        kept.append(line)
        remaining -= len(words)
    return "\n".join(kept), True


def _word_count(text: str) -> int:
    return len(text.split())


def _domain(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")
