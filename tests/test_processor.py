"""Tests for processing one entry: extract, analyze, write, bookkeeping."""
import logging
from datetime import date, datetime

import pytest

from src.analysis import Analysis, AnalysisError, AnalysisResult
from src.extraction import ExtractedArticle, ExtractionError
from src.llm import FatalRunError
from src.models import Entry
from src.processor import EntryProcessor

TODAY = date(2026, 10, 30)
ENTRY = Entry(
    guid="g1", title="Title", url="https://example.com/a", content="", author=None,
    published_at=datetime(2026, 10, 29), feed_id=1, feed_title="Blog", category="articles",
)
ARTICLE = ExtractedArticle(
    title="Title", author=None, published=None, site="Blog", url=ENTRY.url,
    text="text", word_count=1, from_feed=False, truncated=False,
)
ANALYSIS = Analysis(
    summary="s", key_findings=["f"], suggestions_work=["w"], suggestions_personal=["p"],
    tags=[], kb_folder="AI & ML", takeaway="t", action="a",
)
CONFIG = {
    "folders": {"knowledge_base": "2 Know-how"},
    "extraction": {"min_words": 150, "max_words": 30000},
    "llm": {"max_output_tokens": 8000},
}


class Recorder:
    """Fake steps that record calls and can be told to fail."""

    def __init__(self, vault, extract_error=None, analysis_error=None, write_error=None,
                 write_creates_file=True, daily_error=None, log_error=None):
        self.vault = vault
        self.extract_error = extract_error
        self.analysis_error = analysis_error
        self.write_error = write_error
        self.write_creates_file = write_creates_file
        self.daily_error = daily_error
        self.log_error = log_error
        self.calls = []

    def extract(self, entry, client, min_words, max_words):
        self.calls.append("extract")
        if self.extract_error:
            raise self.extract_error
        return ARTICLE

    def analyze(self, article, context, client, max_tokens):
        self.calls.append("analyze")
        if self.analysis_error:
            raise self.analysis_error
        return AnalysisResult(ANALYSIS, cost_eur=0.003)

    def write(self, vault, config, article, analysis, today):
        self.calls.append("write")
        if self.write_error:
            raise self.write_error
        path = vault / "2 Know-how" / "AI & ML" / "Title.md"
        if self.write_creates_file:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("note")
        return path

    def daily(self, vault, config, **kwargs):
        self.calls.append(("daily", kwargs))
        if self.daily_error:
            raise self.daily_error

    def log(self, vault, config, **kwargs):
        self.calls.append(("log", kwargs))
        if self.log_error:
            raise self.log_error


def _processor(steps: Recorder) -> EntryProcessor:
    return EntryProcessor(
        config=CONFIG, vault_path=steps.vault, context=object(), llm_client=object(),
        http_client=object(), today=TODAY,
        extract=steps.extract, analyze=steps.analyze, write=steps.write,
        daily_dose=steps.daily, evaluation_log=steps.log,
    )


def test_success_writes_note_and_bookkeeping(tmp_path):
    steps = Recorder(tmp_path)

    result = _processor(steps).process(ENTRY)

    assert result.success is True
    assert result.note_path == tmp_path / "2 Know-how" / "AI & ML" / "Title.md"
    assert result.cost_eur == pytest.approx(0.003)
    daily = next(c for c in steps.calls if isinstance(c, tuple) and c[0] == "daily")[1]
    assert daily == {"link_stem": "Title", "title": "Title", "folder": "2 Know-how/AI & ML",
                     "takeaway": "t", "action": "a", "today": TODAY}
    log = next(c for c in steps.calls if isinstance(c, tuple) and c[0] == "log")[1]
    assert log["folder"] == "AI & ML"


def test_permanent_extraction_failure_skips_analysis(tmp_path):
    steps = Recorder(tmp_path, extract_error=ExtractionError("not extractable (HTTP 403)", permanent=True))

    result = _processor(steps).process(ENTRY)

    assert result.success is False
    assert result.permanent is True
    assert result.step == "extraction"
    assert result.error == "extraction: not extractable (HTTP 403)"
    assert steps.calls == ["extract"]


def test_transient_extraction_failure_is_not_permanent(tmp_path):
    steps = Recorder(tmp_path, extract_error=ExtractionError("transient: HTTP 503", permanent=False))

    result = _processor(steps).process(ENTRY)

    assert result.permanent is False
    assert result.step == "extraction"


def test_analysis_failure_is_transient_with_prefix_and_cost(tmp_path):
    steps = Recorder(tmp_path, analysis_error=AnalysisError("request timed out after 180s", cost_eur=0.001))

    result = _processor(steps).process(ENTRY)

    assert result.success is False
    assert result.permanent is False
    assert result.step == "analysis"
    assert result.error == "analysis: request timed out after 180s"
    assert result.cost_eur == pytest.approx(0.001)
    assert "write" not in steps.calls


def test_fatal_analysis_error_propagates(tmp_path):
    steps = Recorder(tmp_path, analysis_error=FatalRunError("HTTP 401"))

    with pytest.raises(FatalRunError):
        _processor(steps).process(ENTRY)


def test_vault_write_failure_is_transient(tmp_path):
    steps = Recorder(tmp_path, write_error=PermissionError("read-only"))

    result = _processor(steps).process(ENTRY)

    assert result.success is False
    assert result.step == "vault"
    assert result.error.startswith("vault: ")
    assert result.cost_eur == pytest.approx(0.003)


def test_missing_note_file_after_write_is_failure(tmp_path):
    steps = Recorder(tmp_path, write_creates_file=False)

    result = _processor(steps).process(ENTRY)

    assert result.success is False
    assert result.step == "vault"


def test_bookkeeping_failure_still_counts_as_success(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    steps = Recorder(tmp_path, daily_error=PermissionError("locked"), log_error=OSError("disk"))

    result = _processor(steps).process(ENTRY)

    assert result.success is True
    assert "locked" in caplog.text
    assert "disk" in caplog.text
