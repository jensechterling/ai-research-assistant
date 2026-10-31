"""Tests for the run loop: filters, dedupe, outcomes, limits and fatal handling."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.database import Database
from src.llm import FatalRunError
from src.models import Entry
from src.pipeline import run_pipeline
from src.processor import ProcessingResult

NOW = datetime(2026, 10, 30, 6, 0)
CONFIG = {
    "processing": {"max_entry_age_days": 14, "max_run_minutes": 60},
    "llm": {"max_cost_per_run_eur": 2.0},
}


def _entry(guid: str, days_old: int = 1, category: str = "articles", feed_title: str = "Blog") -> Entry:
    return Entry(
        guid=guid, title=f"Title {guid}", url=f"https://example.com/{guid}", content="feed text",
        author=None, published_at=NOW - timedelta(days=days_old), feed_id=1, feed_title=feed_title,
        category=category,
    )


class FakeFeeds:
    def __init__(self, entries=None, error=None):
        self.entries = entries or []
        self.error = error

    def fetch_new_entries(self):
        if self.error:
            raise self.error
        return list(self.entries)


class FakeProcessor:
    """Returns a scripted result per guid; default is success."""

    def __init__(self, outcomes=None, cost=0.01):
        self.outcomes = outcomes or {}
        self.cost = cost
        self.seen: list[Entry] = []

    def process(self, entry):
        self.seen.append(entry)
        outcome = self.outcomes.get(entry.guid)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is not None:
            return outcome
        return ProcessingResult(True, note_path=Path(f"/vault/{entry.guid}.md"), cost_eur=self.cost)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("src.pipeline.LOCK_PATH", tmp_path / "pipeline.lock")
    return Database(tmp_path / "test.db")


def _run(db, feeds, processor=None, *, factory=None, notes=None, clock=None, config=CONFIG, **kwargs):
    notes = notes if notes is not None else []
    factory = factory or (lambda config, today: processor)
    return run_pipeline(
        db, config=config, feed_manager=feeds, processor_factory=factory, now=NOW,
        clock=clock or (lambda: 0.0), notify=notes.append, **kwargs,
    )


def _queue(db, entry: Entry, due: bool = True):
    db.add_to_retry_queue(entry.guid, entry.feed_id, entry.url, entry.title, entry.category, "earlier error")
    if due:
        db.execute("UPDATE retry_queue SET next_retry_at = datetime('now', '-1 hour') WHERE entry_guid = ?",
                   (entry.guid,))
        db.commit()


def _last_run(db):
    return db.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 1").fetchone()


def test_successful_entries_are_marked_processed_and_run_completed(db):
    processor = FakeProcessor()
    notes = []

    result = _run(db, FakeFeeds([_entry("a"), _entry("b")]), processor, notes=notes)

    assert result.processed == 2
    assert result.cost_eur == pytest.approx(0.02)
    assert db.is_processed("a") and db.is_processed("b")
    assert _last_run(db)["status"] == "completed"
    assert notes == [result]


def test_preflight_failure_stops_before_any_entry(db):
    def factory(config, today):
        raise FatalRunError("Interest profile not found: /vault/interest-profile.md")

    result = _run(db, FakeFeeds([_entry("a")]), factory=factory)

    assert result.stopped_reason == "Interest profile not found: /vault/interest-profile.md"
    assert result.processed == 0
    assert not db.is_processed("a")
    run = _last_run(db)
    assert run["status"] == "failed"
    assert "Interest profile" in run["error"]


def test_non_article_categories_are_skipped_untouched(db):
    processor = FakeProcessor()
    feeds = FakeFeeds([_entry("v1", category="youtube", feed_title="Channel"), _entry("a")])

    result = _run(db, feeds, processor)

    assert [e.guid for e in processor.seen] == ["a"]
    assert result.unsupported == 1
    assert not db.is_processed("v1")
    assert db.get_queued_guids() == set()


def test_entry_both_new_and_due_retry_is_processed_once_as_retry(db):
    entry = _entry("a")
    _queue(db, entry, due=True)
    processor = FakeProcessor()

    result = _run(db, FakeFeeds([entry]), processor)

    assert [e.guid for e in processor.seen] == ["a"]
    assert processor.seen[0].content == "feed text"
    assert result.retried == 1
    assert db.get_queued_guids() == set()


def test_entry_waiting_for_retry_time_is_not_processed(db):
    entry = _entry("a")
    _queue(db, entry, due=False)
    processor = FakeProcessor()

    _run(db, FakeFeeds([entry]), processor)

    assert processor.seen == []


def test_stale_entries_skipped_before_limit(db):
    entries = [_entry(f"old{i}", days_old=30) for i in range(35)] + [_entry(f"new{i}") for i in range(5)]
    processor = FakeProcessor()

    result = _run(db, FakeFeeds(entries), processor, limit=3)

    assert [e.guid for e in processor.seen] == ["new0", "new1", "new2"]
    assert result.stale == 35


def test_retry_entries_are_not_age_filtered(db):
    old = _entry("old", days_old=30)
    _queue(db, old, due=True)
    processor = FakeProcessor()

    result = _run(db, FakeFeeds([]), processor)

    assert [e.guid for e in processor.seen] == ["old"]
    assert result.retried == 1


def test_permanent_failure_marked_processed_without_note(db):
    processor = FakeProcessor({"a": ProcessingResult(False, step="extraction",
                                                     error="extraction: not extractable", permanent=True)})

    result = _run(db, FakeFeeds([_entry("a")]), processor)

    assert result.permanent_failures == 1
    assert db.is_processed("a")
    row = db.execute("SELECT note_path FROM processed_entries WHERE entry_guid = 'a'").fetchone()
    assert row["note_path"] is None
    assert db.get_queued_guids() == set()


def test_permanent_failure_on_retry_entry_leaves_queue(db):
    entry = _entry("a")
    _queue(db, entry, due=True)
    processor = FakeProcessor({"a": ProcessingResult(False, step="extraction", error="x", permanent=True)})

    _run(db, FakeFeeds([entry]), processor)

    assert db.get_queued_guids() == set()
    assert db.is_processed("a")


def test_transient_failure_is_queued_with_step_prefix(db):
    processor = FakeProcessor({"a": ProcessingResult(False, step="analysis", error="analysis: timed out",
                                                     cost_eur=0.001)})

    result = _run(db, FakeFeeds([_entry("a")]), processor)

    assert result.failed == 1
    row = db.execute("SELECT last_error FROM retry_queue WHERE entry_guid = 'a'").fetchone()
    assert row["last_error"] == "analysis: timed out"
    assert not db.is_processed("a")


def test_entry_given_up_by_queue_is_marked_processed(db):
    entry = _entry("a")
    for _ in range(4):
        _queue(db, entry, due=True)
    processor = FakeProcessor({"a": ProcessingResult(False, step="analysis", error="analysis: timed out")})

    result = _run(db, FakeFeeds([entry]), processor)

    assert result.failed == 1
    assert db.get_queued_guids() == set()
    assert db.is_processed("a")


def test_unexpected_exception_in_processing_is_transient(db):
    processor = FakeProcessor({"a": ValueError("boom")})

    result = _run(db, FakeFeeds([_entry("a"), _entry("b")]), processor)

    assert result.failed == 1
    assert result.processed == 1
    assert "boom" in db.execute("SELECT last_error FROM retry_queue").fetchone()["last_error"]


def test_rejected_key_mid_run_stops_without_queueing(db):
    entries = [_entry(f"e{i}") for i in range(10)]
    processor = FakeProcessor({"e2": FatalRunError("Melious API rejected the request (HTTP 401): bad key")})
    notes = []

    result = _run(db, FakeFeeds(entries), processor, notes=notes)

    assert result.processed == 2
    assert [e.guid for e in processor.seen] == ["e0", "e1", "e2"]
    assert db.get_queued_guids() == set()
    assert not db.is_processed("e2")
    run = _last_run(db)
    assert run["status"] == "failed"
    assert "HTTP 401" in run["error"]
    assert notes[0].stopped_reason.startswith("Melious API rejected")


def test_unhandled_exception_records_failed_run_and_reraises(db):
    with pytest.raises(RuntimeError):
        _run(db, FakeFeeds(error=RuntimeError("disk full")), FakeProcessor())

    run = _last_run(db)
    assert run["status"] == "failed"
    assert "disk full" in run["error"]


def test_cost_ceiling_stops_new_entries(db):
    config = {**CONFIG, "llm": {"max_cost_per_run_eur": 1.0}}
    processor = FakeProcessor(cost=0.5)

    result = _run(db, FakeFeeds([_entry(f"e{i}") for i in range(5)]), processor, config=config)

    assert result.processed == 2
    assert result.limit_reason.startswith("cost")
    assert db.get_queued_guids() == set()
    assert not db.is_processed("e2")
    assert _last_run(db)["status"] == "completed"


def test_time_limit_stops_new_entries(db):
    ticks = iter([0.0, 0.0, 30 * 60.0, 61 * 60.0, 61 * 60.0])
    processor = FakeProcessor()

    result = _run(db, FakeFeeds([_entry(f"e{i}") for i in range(5)]), processor, clock=lambda: next(ticks))

    assert result.processed == 2
    assert result.limit_reason.startswith("time")


def test_dry_run_lists_without_processing_or_recording(db):
    def factory(config, today):
        raise AssertionError("processor built in dry run")

    entries = [_entry("old", days_old=30), _entry("a"), _entry("v", category="youtube")]
    notes = []

    result = _run(db, FakeFeeds(entries), factory=factory, notes=notes, dry_run=True)

    assert result.skipped == 1
    assert result.stale == 1
    assert result.unsupported == 1
    assert notes == []
    assert _last_run(db) is None


def test_claude_cli_is_never_started(db, monkeypatch):
    calls = []
    monkeypatch.setattr("src.pipeline.subprocess.run", lambda args, **kw: calls.append(args))

    run_pipeline(db, config=CONFIG, feed_manager=FakeFeeds([_entry("a")]),
                 processor_factory=lambda config, today: FakeProcessor(), now=NOW, clock=lambda: 0.0)

    assert calls, "notification should have used subprocess.run"
    assert all("claude" not in args for args in calls)


def _analysis_failure(cost=0.001):
    return ProcessingResult(False, step="analysis", error="analysis: HTTP 400: bad parameter", cost_eur=cost)


def test_three_analysis_failures_in_a_row_at_start_stop_the_run(db):
    entries = [_entry(f"e{i}") for i in range(6)]
    processor = FakeProcessor({e.guid: _analysis_failure() for e in entries})
    notes = []

    result = _run(db, FakeFeeds(entries), processor, notes=notes)

    assert [e.guid for e in processor.seen] == ["e0", "e1", "e2"]
    assert db.get_queued_guids() == {"e0", "e1", "e2"}
    assert "3 analyses failed in a row" in result.stopped_reason
    assert "bad parameter" in result.stopped_reason
    assert _last_run(db)["status"] == "failed"
    assert notes[0].stopped_reason == result.stopped_reason


def test_analysis_failures_after_a_success_do_not_stop_the_run(db):
    entries = [_entry(f"e{i}") for i in range(5)]
    processor = FakeProcessor({e.guid: _analysis_failure() for e in entries[1:]})

    result = _run(db, FakeFeeds(entries), processor)

    assert len(processor.seen) == 5
    assert result.stopped_reason is None
    assert result.failed == 4


def test_extraction_failures_do_not_count_toward_the_analysis_streak(db):
    entries = [_entry(f"e{i}") for i in range(5)]
    outcomes = {f"e{i}": ProcessingResult(False, step="extraction", error="extraction: transient: x")
                for i in range(3)}
    outcomes["e3"] = _analysis_failure()
    outcomes["e4"] = _analysis_failure()
    processor = FakeProcessor(outcomes)

    result = _run(db, FakeFeeds(entries), processor)

    assert len(processor.seen) == 5
    assert result.stopped_reason is None


def test_crash_sends_run_stopped_notification(db):
    notes = []

    with pytest.raises(RuntimeError):
        _run(db, FakeFeeds(error=RuntimeError("disk full")), FakeProcessor(), notes=notes)

    assert "disk full" in notes[0].stopped_reason
