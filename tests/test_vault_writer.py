"""Tests for writing notes, Daily Dose entries and evaluation-log rows."""
from datetime import date

import pytest
import yaml

from src.analysis import Analysis
from src.extraction import ExtractedArticle
from src.vault_writer import (
    append_daily_dose,
    render_note,
    source_slug,
    upsert_evaluation_log,
    write_note,
)

TODAY = date(2026, 10, 29)  # a Thursday
CONFIG = {
    "folders": {
        "knowledge_base": "2 Know-how",
        "daily_notes": "1 Daily notes",
        "templates": "Templates",
        "kb_fallback": "Misc",
    }
}
URL = "https://www.lennysnewsletter.com/p/agent-evals?utm=1"


def _article(**overrides) -> ExtractedArticle:
    data = dict(
        title="Agent Evals: A Guide",
        author="Jane Doe",
        published="2026-10-01",
        site="Lenny's Newsletter",
        url=URL,
        text="First paragraph.\n\nSecond paragraph.",
        word_count=4,
        from_feed=False,
        truncated=False,
    )
    data.update(overrides)
    return ExtractedArticle(**data)


def _analysis(**overrides) -> Analysis:
    data = dict(
        summary="Summary para one.\n\nSummary para two.",
        key_findings=["Finding one", "Finding two"],
        suggestions_work=["Work idea"],
        suggestions_personal=["Personal idea"],
        tags=["ai-agents", "evals"],
        kb_folder="AI & ML",
        takeaway="Evals first.",
        action="Write 20 eval tasks.",
    )
    data.update(overrides)
    return Analysis(**data)


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n")[1])


@pytest.fixture
def vault(tmp_path):
    kb = tmp_path / "2 Know-how"
    (kb / "AI & ML").mkdir(parents=True)
    (kb / "Leadership").mkdir()
    return tmp_path


# --- 5.1 note rendering ---------------------------------------------------


def test_note_frontmatter_fields():
    fm = _frontmatter(render_note(_article(), _analysis(), TODAY))

    assert fm["created"] == "2026-10-29"
    assert fm["evaluated"] == "2026-10-29"
    assert fm["source"] == URL
    assert fm["author"] == "[[Jane Doe]]"
    assert fm["tags"] == ["ai-agents", "evals", "source/lennysnewsletter"]


def test_note_sections_in_order():
    text = render_note(_article(), _analysis(), TODAY)
    headings = [line for line in text.splitlines() if line.startswith("#")]

    assert headings == [
        "# Agent Evals: A Guide",
        "## Metadata",
        "## Management Summary",
        "## Key Findings",
        "## Suggestions",
        "### For Work",
        "### For Personal Life",
        "## Original Content",
    ]


def test_note_contains_exact_url_and_collapsed_original_text():
    text = render_note(_article(), _analysis(), TODAY)

    assert f"- **URL:** {URL}" in text
    assert "> [!info]- Full Article Text\n> First paragraph.\n>\n> Second paragraph." in text


def test_truncated_note_says_so():
    text = render_note(_article(truncated=True, word_count=30000), _analysis(), TODAY)

    assert "truncated at 30000 words" in text


def test_note_without_author_omits_author_link():
    fm = _frontmatter(render_note(_article(author=None), _analysis(), TODAY))

    assert "author" not in fm


@pytest.mark.parametrize(
    "url,slug",
    [
        ("https://www.lennysnewsletter.com/p/x", "lennysnewsletter"),
        ("https://stratechery.com/2026/x", "stratechery"),
        ("https://review.firstround.com/x", "review-firstround"),
        ("https://oneusefulthing.substack.com/p/x", "oneusefulthing-substack"),
    ],
)
def test_source_slug(url, slug):
    assert source_slug(url) == slug


# --- 5.2 filing and naming ------------------------------------------------


def test_note_written_to_existing_folder_with_sanitised_name(vault):
    path = write_note(vault, CONFIG, _article(), _analysis(), TODAY)

    assert path == vault / "2 Know-how" / "AI & ML" / "Agent-Evals-A-Guide.md"
    assert path.read_text().startswith("---\n")


def test_prefixed_and_differently_cased_folder_matches_existing(vault):
    path = write_note(vault, CONFIG, _article(), _analysis(kb_folder="2 Know-how/ai & ml/"), TODAY)

    assert path.parent == vault / "2 Know-how" / "AI & ML"


def test_new_folder_is_created(vault):
    path = write_note(vault, CONFIG, _article(), _analysis(kb_folder="Health Tech"), TODAY)

    assert path.parent == vault / "2 Know-how" / "Health Tech"


@pytest.mark.parametrize("name", ["../../Private", "AI & ML/Nested", "   ", "..", ".hidden"])
def test_unsafe_folder_goes_to_fallback(vault, name):
    path = write_note(vault, CONFIG, _article(), _analysis(kb_folder=name), TODAY)

    assert path.parent == vault / "2 Know-how" / "Misc"
    assert not (vault.parent / "Private").exists()


def test_filename_strips_link_breaking_characters_and_is_capped(vault):
    title = 'A [big] title: "what?" #1 ^ ' + "x" * 100
    path = write_note(vault, CONFIG, _article(title=title), _analysis(), TODAY)

    assert all(c not in path.stem for c in '[]:"?#^')
    assert len(path.stem) <= 80


def test_same_title_different_source_gets_numbered_suffix(vault):
    first = write_note(vault, CONFIG, _article(), _analysis(), TODAY)
    second = write_note(vault, CONFIG, _article(url="https://other.example/x"), _analysis(), TODAY)
    third = write_note(vault, CONFIG, _article(url="https://third.example/x"), _analysis(), TODAY)

    assert second.name == "Agent-Evals-A-Guide-2.md"
    assert third.name == "Agent-Evals-A-Guide-3.md"
    assert first.exists()


def test_same_source_replaces_existing_note(vault):
    first = write_note(vault, CONFIG, _article(), _analysis(summary="old"), TODAY)
    second = write_note(vault, CONFIG, _article(), _analysis(summary="new"), TODAY)

    assert second == first
    assert "new" in first.read_text()
    assert len(list(first.parent.glob("*.md"))) == 1


def test_no_temporary_files_left_behind(vault):
    path = write_note(vault, CONFIG, _article(), _analysis(), TODAY)

    assert [p.name for p in path.parent.iterdir()] == [path.name]


# --- 5.3 daily note -------------------------------------------------------

TEMPLATE = """---
tags:
  - daily-note
created: <% tp.date.now("YYYY-MM-DD") %>
day: <% tp.date.now("dddd") %>
---
# Daily Notes

-

# Daily dose of know-how

- """

ENTRY = dict(link_stem="Agent-Evals-A-Guide", title="Agent Evals: A Guide", folder="2 Know-how/AI & ML",
             takeaway="Evals first.", action="Write 20 eval tasks.")
EXPECTED_ENTRY = (
    "- [[Agent-Evals-A-Guide|Agent Evals: A Guide]] → *2 Know-how/AI & ML/*\n"
    "  - **Takeaway:** Evals first.\n"
    "  - **Action:** Write 20 eval tasks."
)


def _daily(vault):
    return vault / "1 Daily notes" / "2026-10-29.md"


def test_daily_note_created_from_templater_template(vault):
    (vault / "Templates").mkdir()
    (vault / "Templates" / "Daily Note.md").write_text(TEMPLATE)

    append_daily_dose(vault, CONFIG, today=TODAY, **ENTRY)

    text = _daily(vault).read_text()
    assert "created: 2026-10-29" in text
    assert "day: Thursday" in text
    assert "<%" not in text
    section = text.split("# Daily dose of know-how\n")[1]
    assert section.strip() == EXPECTED_ENTRY


def test_entry_appended_under_existing_h2_heading(vault):
    _daily(vault).parent.mkdir()
    _daily(vault).write_text(
        "# Daily Notes\n\n- met Anna\n\n## Daily Dose of Know-How\n\n- [[Old]] → *x/*\n"
        "  - **Takeaway:** t\n  - **Action:** a\n\n## Later section\n\ntext\n"
    )

    append_daily_dose(vault, CONFIG, today=TODAY, **ENTRY)

    text = _daily(vault).read_text()
    dose, later = text.split("## Daily Dose of Know-How\n")[1].split("## Later section")
    assert dose.index("[[Old]]") < dose.index("[[Agent-Evals-A-Guide|")
    assert EXPECTED_ENTRY in dose
    assert later == "\n\ntext\n"


def test_heading_appended_when_missing(vault):
    _daily(vault).parent.mkdir()
    _daily(vault).write_text("# Daily Notes\n\n- met Anna\n")

    append_daily_dose(vault, CONFIG, today=TODAY, **ENTRY)

    assert _daily(vault).read_text() == (
        "# Daily Notes\n\n- met Anna\n\n## Daily Dose of Know-How\n\n" + EXPECTED_ENTRY + "\n"
    )


def test_same_note_not_added_twice(vault):
    _daily(vault).parent.mkdir()
    _daily(vault).write_text("# Daily Notes\n")

    append_daily_dose(vault, CONFIG, today=TODAY, **ENTRY)
    append_daily_dose(vault, CONFIG, today=TODAY, **ENTRY)

    assert _daily(vault).read_text().count("[[Agent-Evals-A-Guide|") == 1


# --- 5.4 evaluation log ---------------------------------------------------

LOG = """# Knowledge Evaluation Log

Last updated: 2026-04-03
Total evaluated: 592 notes

## Aggregated Patterns

### Leadership (1 note)
- [[Leadership/Old Note]] - insight | with pipe

## All Evaluations

| Note | Evaluated | Category | Key Insight |
|------|-----------|----------|-------------|
| [[Leadership/Old Note]] | 2026-04-03 | Leadership | Old insight |
"""


def _log(vault):
    return vault / "2 Know-how" / "evaluation-log.md"


def _upsert(vault, takeaway="Evals first."):
    upsert_evaluation_log(vault, CONFIG, link_stem="Agent-Evals-A-Guide", title="Agent Evals: A Guide",
                          folder="AI & ML", takeaway=takeaway, today=TODAY)


def test_row_appended_and_header_counts_updated(vault):
    _log(vault).write_text(LOG)

    _upsert(vault)

    text = _log(vault).read_text()
    assert text.splitlines()[-1] == "| [[Agent-Evals-A-Guide\\|Agent Evals: A Guide]] | 2026-10-29 | AI & ML | Evals first. |"
    assert "Last updated: 2026-10-29" in text
    assert "Total evaluated: 2 notes" in text


def test_aggregated_patterns_left_byte_identical(vault):
    _log(vault).write_text(LOG)

    _upsert(vault)

    def patterns(t):
        return t.split("## Aggregated Patterns")[1].split("## All Evaluations")[0]

    assert patterns(_log(vault).read_text()) == patterns(LOG)


def test_pipe_in_takeaway_is_escaped(vault):
    _log(vault).write_text(LOG)

    _upsert(vault, takeaway="A | B")

    assert "| A \\| B |" in _log(vault).read_text()


def test_existing_row_for_same_note_is_replaced(vault):
    _log(vault).write_text(LOG)

    _upsert(vault, takeaway="first")
    _upsert(vault, takeaway="second")

    text = _log(vault).read_text()
    assert "first" not in text
    assert text.count("[[Agent-Evals-A-Guide\\|") == 1
    assert "Total evaluated: 2 notes" in text


def test_log_created_when_missing(vault):
    _upsert(vault)

    text = _log(vault).read_text()
    assert text.startswith("# Knowledge Evaluation Log\n")
    assert "| Note | Evaluated | Category | Key Insight |" in text
    assert "Total evaluated: 1 notes" in text
    assert "[[Agent-Evals-A-Guide\\|Agent Evals: A Guide]]" in text


SPLIT_LOG = LOG + """
| [[Leadership/Second Block]] | 2026-04-09 | Leadership | After a blank line |

- a stray bullet the old skill left here
"""


def test_rows_after_blank_lines_count_and_new_row_goes_after_the_last_row(vault):
    _log(vault).write_text(SPLIT_LOG)

    _upsert(vault)

    lines = _log(vault).read_text().splitlines()
    second = lines.index("| [[Leadership/Second Block]] | 2026-04-09 | Leadership | After a blank line |")
    assert lines[second + 1].startswith("| [[Agent-Evals-A-Guide\\|")
    assert "Total evaluated: 3 notes" in lines
    assert lines[-1] == "- a stray bullet the old skill left here"


def test_existing_row_found_after_blank_lines(vault):
    _log(vault).write_text(SPLIT_LOG.replace("[[Leadership/Second Block]]", "[[Agent-Evals-A-Guide\\|Agent Evals: A Guide]]"))

    _upsert(vault, takeaway="updated")

    text = _log(vault).read_text()
    assert text.count("[[Agent-Evals-A-Guide\\|") == 1
    assert "| updated |" in text
    assert "Total evaluated: 2 notes" in text


# --- review fixes ---------------------------------------------------------

def _cells(row: str) -> list[str]:
    return row.replace("\\|", "\x00").strip("|").split("|")


def test_pipe_and_brackets_in_title_keep_log_row_intact(vault):
    _log(vault).write_text(LOG)

    upsert_evaluation_log(vault, CONFIG, link_stem="A-B-x", title="A | B [[x]]\nmore",
                          folder="AI & ML", takeaway="t", today=TODAY)

    row = _log(vault).read_text().splitlines()[-1]
    assert len(_cells(row)) == 4
    assert row.startswith("| [[A-B-x\\|A - B x more]] |")


def test_pipe_and_brackets_in_title_keep_daily_link_intact(vault):
    _daily(vault).parent.mkdir()
    _daily(vault).write_text("# Daily Notes\n")

    append_daily_dose(vault, CONFIG, today=TODAY, **{**ENTRY, "title": "A | B [[x]]"})

    assert "- [[Agent-Evals-A-Guide|A - B x]] → *2 Know-how/AI & ML/*" in _daily(vault).read_text()


def test_templater_commands_are_neutralised_in_note(vault):
    article = _article(text="Try <%* app.vault.delete() %> now.")
    analysis = _analysis(summary="Uses <% tp.file.title %> here.", takeaway="<%* x %>")

    text = render_note(article, analysis, TODAY)

    assert "<%" not in text


def test_templater_commands_are_neutralised_in_daily_note_and_log(vault):
    _daily(vault).parent.mkdir()
    _daily(vault).write_text("# Daily Notes\n")
    _log(vault).write_text(LOG)
    entry = {**ENTRY, "takeaway": "<%* bad %>", "action": "<% bad %>", "title": "T <%"}

    append_daily_dose(vault, CONFIG, today=TODAY, **entry)
    upsert_evaluation_log(vault, CONFIG, link_stem="x", title="<% t %>", folder="AI & ML",
                          takeaway="<%* bad %>", today=TODAY)

    assert "<%" not in _daily(vault).read_text()
    assert "<%" not in _log(vault).read_text()


def test_entry_under_h1_heading_goes_before_next_heading_of_any_level(vault):
    _daily(vault).parent.mkdir()
    _daily(vault).write_text("# Daily dose of know-how\n\n-\n\n## Journal\n\n-\n")

    append_daily_dose(vault, CONFIG, today=TODAY, **ENTRY)

    text = _daily(vault).read_text()
    dose, journal = text.split("## Journal")
    assert EXPECTED_ENTRY in dose
    assert journal == "\n\n-\n"


def test_written_files_are_readable_by_others(vault):
    _log(vault).write_text(LOG)
    _log(vault).chmod(0o644)

    _upsert(vault)
    note = write_note(vault, CONFIG, _article(), _analysis(), TODAY)

    assert _log(vault).stat().st_mode & 0o777 == 0o644
    assert note.stat().st_mode & 0o777 == 0o644


def test_folder_equal_to_knowledge_base_name_goes_to_fallback(vault):
    path = write_note(vault, CONFIG, _article(), _analysis(kb_folder="2 Know-how"), TODAY)

    assert path.parent == vault / "2 Know-how" / "Misc"
