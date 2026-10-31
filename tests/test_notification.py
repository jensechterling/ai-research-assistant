"""Tests for the end-of-run macOS notification."""
from src.pipeline import PipelineResult, notification_text, send_notification


def test_normal_run_text():
    result = PipelineResult(processed=12, failed=1, permanent_failures=2, retried=3, cost_eur=0.09)

    assert notification_text(result) == (
        "Content Pipeline",
        "Processed 12, Failed 1, 2 skipped (not extractable), 3 retried, EUR 0.09",
    )


def test_quiet_run_text():
    assert notification_text(PipelineResult()) == ("Content Pipeline", "Processed 0, EUR 0.00")


def test_permanent_failures_mentioned():
    result = PipelineResult(processed=3, failed=1, permanent_failures=2, cost_eur=0.02)

    assert "2 skipped (not extractable)" in notification_text(result)[1]


def test_stopped_run_title_and_cut_cause():
    result = PipelineResult(stopped_reason="x" * 300)

    title, message = notification_text(result)

    assert title == "Run stopped"
    assert message == "x" * 150


def test_quotes_reach_osascript_as_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr("src.pipeline.subprocess.run", lambda args, **kw: calls.append(args))
    cause = 'Melious API rejected the request (HTTP 401): {"message": "Invalid API key format"}'

    send_notification(PipelineResult(stopped_reason=cause))

    args = calls[0]
    assert args[:7] == [
        "osascript",
        "-e", "on run argv",
        "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
        "-e", "end run",
    ]
    assert args[7] == cause
    assert args[8] == "Run stopped"
    assert all(cause not in a for a in args[:7])
