"""Tests for permanent failure handling in the pipeline."""
import logging
from datetime import datetime
from pathlib import Path

import pytest

from src.database import Database
from src.models import Entry
from src.pipeline import run_pipeline
from src.processor import ProcessingResult

NOW = datetime(2026, 10, 30, 6, 0)
CONFIG = {
    "processing": {"max_entry_age_days": 14, "max_run_minutes": 60},
    "llm": {"max_cost_per_run_eur": 2.0},
}
PAYWALL = ProcessingResult(False, step="extraction", error="extraction: not extractable (HTTP 403)", permanent=True)
TIMEOUT = ProcessingResult(False, step="analysis", error="analysis: request timed out after 180s")


def _entry(guid: str) -> Entry:
    return Entry(guid=guid, title=f"Article {guid}", url=f"https://example.com/{guid}", content="",
                 author=None, published_at=NOW, feed_id=1, feed_title="Feed", category="articles")


class Feeds:
    def __init__(self, entries):
        self.entries = entries

    def fetch_new_entries(self):
        # Like FeedManager: only entries not yet marked processed
        return [e for e in self.entries if not self.db.is_processed(e.guid)]


class Processor:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = 0

    def process(self, entry):
        self.calls += 1
        return self.outcomes[entry.guid]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("src.pipeline.LOCK_PATH", tmp_path / "pipeline.lock")
    return Database(tmp_path / "test.db")


def _run(db, entries, processor):
    feeds = Feeds(entries)
    feeds.db = db
    return run_pipeline(db, config=CONFIG, feed_manager=feeds, processor_factory=lambda c, t: processor,
                        now=NOW, clock=lambda: 0.0, notify=lambda r: None)


def test_permanent_failure_skips_retry_queue_and_logs_warning(db, caplog):
    caplog.set_level(logging.WARNING)

    _run(db, [_entry("a")], Processor({"a": PAYWALL}))

    assert db.get_queued_guids() == set()
    assert "[PERMANENT] Article a: extraction: not extractable (HTTP 403)" in caplog.text


def test_transient_failure_still_retries(db):
    _run(db, [_entry("a")], Processor({"a": TIMEOUT}))

    assert db.get_queued_guids() == {"a"}


def test_permanent_failures_counted_separately(db):
    outcomes = {"a": PAYWALL, "b": PAYWALL, "c": TIMEOUT,
                "d": ProcessingResult(True, note_path=Path("/v/d.md"))}

    result = _run(db, [_entry(g) for g in "abcd"], Processor(outcomes))

    assert result.permanent_failures == 2
    assert result.failed == 1
    assert result.processed == 1


def test_permanent_failure_not_attempted_again_next_day(db):
    processor = Processor({"a": PAYWALL})

    _run(db, [_entry("a")], processor)
    result = _run(db, [_entry("a")], processor)

    assert processor.calls == 1
    assert result.permanent_failures == 0
