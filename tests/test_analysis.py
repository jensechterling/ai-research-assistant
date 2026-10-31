"""Tests for the analysis step: prompt building, validation, repair and truncation."""
import json
from datetime import date

import pytest

from src.analysis import (
    Analysis,
    AnalysisContext,
    AnalysisError,
    analyze,
    build_messages,
    load_context,
)
from src.extraction import ExtractedArticle
from src.llm import Completion, FatalRunError, LLMError, Usage

ARTICLE = ExtractedArticle(
    title="Small teams ship faster",
    author="Jane Doe",
    published="2026-10-01",
    site="Example Blog",
    url="https://example.com/small-teams",
    text="ARTICLE BODY TEXT about small teams.",
    word_count=6,
    from_feed=False,
    truncated=False,
)
CONTEXT = AnalysisContext(
    profile="PROFILE TEXT: founder of a health app",
    folders=["AI & ML", "Leadership"],
    language="English",
    today=date(2026, 10, 30),
)
VALID = {
    "summary": "Para one.\n\nPara two.",
    "key_findings": ["a", "b", "c"],
    "suggestions_work": ["w1"],
    "suggestions_personal": ["p1"],
    "tags": ["team-size", "productivity"],
    "kb_folder": "Leadership",
    "takeaway": "Small teams ship faster.",
    "action": "Split the app team by product area.",
}


class FakeClient:
    """Returns queued completions and records each request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, max_tokens):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _reply(content, finish="stop", cost=0.001):
    if not isinstance(content, str):
        content = json.dumps(content)
    return Completion(content=content, finish_reason=finish, usage=Usage(cost_eur=cost))


# --- prompt ---------------------------------------------------------------


def test_system_message_holds_profile_folders_language_and_schema():
    system, user = build_messages(ARTICLE, CONTEXT)

    assert system["role"] == "system"
    assert "PROFILE TEXT" in system["content"]
    assert "AI & ML" in system["content"] and "Leadership" in system["content"]
    assert "English" in system["content"]
    assert '"kb_folder"' in system["content"]
    assert "ARTICLE BODY TEXT" not in system["content"]


def test_user_message_holds_article_metadata_and_text():
    _, user = build_messages(ARTICLE, CONTEXT)

    assert user["role"] == "user"
    assert "ARTICLE BODY TEXT" in user["content"]
    assert "Small teams ship faster" in user["content"]
    assert "PROFILE TEXT" not in user["content"]


def test_system_message_is_identical_for_different_articles():
    other = ExtractedArticle(**{**ARTICLE.__dict__, "title": "Other", "text": "OTHER TEXT"})

    assert build_messages(ARTICLE, CONTEXT)[0] == build_messages(other, CONTEXT)[0]


# --- analyze --------------------------------------------------------------


def test_valid_reply_is_returned_with_cost():
    client = FakeClient([_reply(VALID)])

    result = analyze(ARTICLE, CONTEXT, client, max_tokens=8000)

    assert result.analysis.kb_folder == "Leadership"
    assert result.cost_eur == pytest.approx(0.001)
    assert len(client.calls) == 1


def test_invalid_reply_is_repaired_once():
    client = FakeClient([_reply("not json"), _reply(VALID)])

    result = analyze(ARTICLE, CONTEXT, client, max_tokens=8000)

    assert result.analysis.takeaway == "Small teams ship faster."
    assert result.cost_eur == pytest.approx(0.002)
    repair_messages = client.calls[1]["messages"]
    assert repair_messages[-2] == {"role": "assistant", "content": "not json"}
    assert "valid" in repair_messages[-1]["content"].lower()


def test_invalid_twice_is_transient_error_carrying_cost():
    client = FakeClient([_reply("not json"), _reply({"summary": "only"})])

    with pytest.raises(AnalysisError) as exc:
        analyze(ARTICLE, CONTEXT, client, max_tokens=8000)

    assert "invalid" in str(exc.value)
    assert exc.value.cost_eur == pytest.approx(0.002)


def test_truncated_reply_is_retried_with_double_budget_not_repaired():
    client = FakeClient([_reply("", finish="length"), _reply(VALID)])

    result = analyze(ARTICLE, CONTEXT, client, max_tokens=8000)

    assert result.analysis.kb_folder == "Leadership"
    assert client.calls[1]["max_tokens"] == 16000
    assert client.calls[1]["messages"] == client.calls[0]["messages"]


def test_truncation_budget_is_capped_at_model_maximum():
    client = FakeClient([_reply("", finish="length"), _reply(VALID)])

    analyze(ARTICLE, CONTEXT, client, max_tokens=20000)

    assert client.calls[1]["max_tokens"] == 32000


def test_truncated_twice_fails_as_output_truncated():
    client = FakeClient([_reply("", finish="length"), _reply("", finish="length")])

    with pytest.raises(AnalysisError) as exc:
        analyze(ARTICLE, CONTEXT, client, max_tokens=8000)

    assert "output truncated" in str(exc.value)


def test_more_than_five_tags_is_rejected():
    with pytest.raises(ValueError):
        Analysis(**{**VALID, "tags": ["a", "b", "c", "d", "e", "f"]})


def test_tags_are_normalised_to_lower_case_hyphenated():
    analysis = Analysis(**{**VALID, "tags": ["#Team Size", "AI_Agents"]})

    assert analysis.tags == ["team-size", "ai-agents"]


def test_transient_client_error_keeps_cost_of_earlier_attempts():
    client = FakeClient([_reply("not json"), LLMError("HTTP 503: busy")])

    with pytest.raises(AnalysisError) as exc:
        analyze(ARTICLE, CONTEXT, client, max_tokens=8000)

    assert "503" in str(exc.value)
    assert exc.value.cost_eur == pytest.approx(0.001)


def test_fatal_client_error_propagates():
    client = FakeClient([FatalRunError("HTTP 401")])

    with pytest.raises(FatalRunError):
        analyze(ARTICLE, CONTEXT, client, max_tokens=8000)


# --- context --------------------------------------------------------------


def _config(profile="interest-profile.md"):
    return {
        "profile": {"interest_profile": profile},
        "folders": {"knowledge_base": "2 Know-how"},
        "llm": {"output_language": "English"},
    }


def test_load_context_reads_profile_and_top_level_folders(tmp_path):
    (tmp_path / "interest-profile.md").write_text("my profile")
    kb = tmp_path / "2 Know-how"
    (kb / "Leadership" / "Nested").mkdir(parents=True)
    (kb / "AI & ML").mkdir()
    (kb / ".hidden").mkdir()
    (kb / "evaluation-log.md").write_text("log")

    context = load_context(_config(), tmp_path, today=date(2026, 10, 30))

    assert context.profile == "my profile"
    assert context.folders == ["AI & ML", "Leadership"]


def test_missing_profile_is_fatal_and_names_path(tmp_path):
    (tmp_path / "2 Know-how").mkdir()

    with pytest.raises(FatalRunError) as exc:
        load_context(_config(), tmp_path, today=date(2026, 10, 30))

    assert "interest-profile.md" in str(exc.value)


def test_missing_knowledge_base_is_fatal(tmp_path):
    (tmp_path / "interest-profile.md").write_text("my profile")

    with pytest.raises(FatalRunError) as exc:
        load_context(_config(), tmp_path, today=date(2026, 10, 30))

    assert "2 Know-how" in str(exc.value)
