"""Write analyzed articles into the Obsidian vault: notes, Daily Dose, evaluation log."""
import os
import re
import stat
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml
from jinja2 import Environment, FileSystemLoader

from src.analysis import Analysis
from src.config import get_project_dir
from src.extraction import ExtractedArticle

_NOTES = Environment(
    loader=FileSystemLoader(str(get_project_dir() / "templates" / "notes")),
    keep_trailing_newline=True,
)
FILENAME_FORBIDDEN = re.compile(r'[/\\:*?"<>|#\[\]^]')
MAX_FILENAME_LENGTH = 80
DAILY_DOSE_HEADING = "Daily Dose of Know-How"
LOG_HEADER = "| Note | Evaluated | Category | Key Insight |"

# Moment.js tokens used by Templater, longest first so "YYYY" wins over "YY"
_MOMENT_TOKENS = [
    ("YYYY", "%Y"), ("YY", "%y"), ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"),
    ("dddd", "%A"), ("ddd", "%a"), ("DD", "%d"),
]
_TEMPLATER_DATE = re.compile(r'<%\s*tp\.date\.now\(\s*(?:"([^"]*)"|\'([^\']*)\')?\s*\)\s*%>')


# --- note -----------------------------------------------------------------


def source_slug(url: str) -> str:
    """Tag-friendly name of the URL's site, e.g. www.lennysnewsletter.com -> lennysnewsletter."""
    domain = urlparse(url).netloc.removeprefix("www.")
    name = domain.rsplit(".", 1)[0]
    return name.replace(".", "-").replace("_", "-").lower()


def render_note(article: ExtractedArticle, analysis: Analysis, today: date) -> str:
    """Render the full note: YAML frontmatter plus the Markdown body."""
    frontmatter = {
        "created": today.isoformat(),
        "tags": [*analysis.tags, f"source/{source_slug(article.url)}"],
        "source": article.url,
    }
    if article.author:
        frontmatter["author"] = f"[[{article.author}]]"
    frontmatter["evaluated"] = today.isoformat()

    callout = "\n".join(f"> {line}" if line.strip() else ">" for line in article.text.splitlines())
    body = _NOTES.get_template("article.md.j2").render(article=article, analysis=analysis, callout=callout)
    header = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True, width=10_000)
    return _defuse(f"---\n{header}---\n\n{body}")


def write_note(vault: Path, config: dict, article: ExtractedArticle, analysis: Analysis, today: date) -> Path:
    """File the note into the knowledge base and return its path."""
    folders = config["folders"]
    kb_path = vault / folders["knowledge_base"]
    folder = _resolve_folder(kb_path, folders["knowledge_base"], analysis.kb_folder, folders["kb_fallback"])
    folder.mkdir(parents=True, exist_ok=True)

    stem = sanitize_filename(article.title)
    path = folder / f"{stem}.md"
    suffix = 2
    while path.exists() and _note_source(path) != article.url:
        path = folder / f"{stem}-{suffix}.md"
        suffix += 1

    atomic_write(path, render_note(article, analysis, today))
    return path


def sanitize_filename(title: str) -> str:
    """Remove characters that break files or Obsidian links, hyphenate spaces, cap the length."""
    name = FILENAME_FORBIDDEN.sub("", title)
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"-{2,}", "-", name)
    name = name[:MAX_FILENAME_LENGTH].strip("-.")
    return name or "Untitled"


def _resolve_folder(kb_path: Path, kb_name: str, requested: str, fallback: str) -> Path:
    name = requested.strip().strip("/\\").strip()
    if name.lower().startswith(kb_name.lower() + "/"):
        name = name[len(kb_name) + 1:].strip("/\\").strip()
    if not name or name.lower() == kb_name.lower() or "/" in name or "\\" in name or ".." in name or name.startswith("."):
        name = fallback

    if kb_path.is_dir():
        for existing in kb_path.iterdir():
            if existing.is_dir() and existing.name.lower() == name.lower():
                return existing
    return kb_path / name


def _note_source(path: Path) -> str | None:
    text = path.read_text()
    if not text.startswith("---\n"):
        return None
    try:
        frontmatter = yaml.safe_load(text.split("---\n", 2)[1]) or {}
    except (yaml.YAMLError, IndexError):
        return None
    return frontmatter.get("source") if isinstance(frontmatter, dict) else None


# --- daily note -----------------------------------------------------------


def append_daily_dose(vault: Path, config: dict, *, link_stem: str, title: str, folder: str,
                      takeaway: str, action: str, today: date) -> None:
    """Add a Daily Dose entry for a note to today's daily note."""
    folders = config["folders"]
    path = vault / folders["daily_notes"] / f"{today.isoformat()}.md"
    if path.exists():
        text = path.read_text()
    else:
        template = vault / folders["templates"] / "Daily Note.md"
        text = _resolve_templater_dates(template.read_text(), today) if template.exists() else ""

    entry = _defuse(
        f"- [[{link_stem}|{_link_title(title)}]] → *{folder}/*\n"
        f"  - **Takeaway:** {_one_line(takeaway)}\n"
        f"  - **Action:** {_one_line(action)}"
    )
    heading = re.search(rf"^(#{{1,6}})[ \t]+{re.escape(DAILY_DOSE_HEADING)}[ \t]*$", text,
                        re.IGNORECASE | re.MULTILINE)
    if heading is None:
        text = text.rstrip("\n")
        text = (text + "\n\n" if text else "") + f"## {DAILY_DOSE_HEADING}\n\n{entry}\n"
    else:
        start = heading.end()
        next_heading = re.compile(r"^#{1,6}[ \t]", re.MULTILINE).search(text, start)
        end = next_heading.start() if next_heading else len(text)
        section = text[start:end]
        if f"[[{link_stem}|" in section or f"[[{link_stem}]]" in section:
            return
        kept = "\n".join(line for line in section.splitlines() if line.strip() != "-").strip("\n")
        new_section = "\n\n" + (kept + "\n\n" if kept else "") + entry + "\n"
        rest = text[end:]
        text = text[:start] + new_section + ("\n" + rest if rest else "")

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, text)


def _resolve_templater_dates(text: str, today: date) -> str:
    def replace(match: re.Match) -> str:
        fmt = match.group(1) or match.group(2) or "YYYY-MM-DD"
        for token, directive in _MOMENT_TOKENS:
            fmt = fmt.replace(token, directive)
        return today.strftime(fmt)

    return _TEMPLATER_DATE.sub(replace, text)


# --- evaluation log -------------------------------------------------------


def upsert_evaluation_log(vault: Path, config: dict, *, link_stem: str, title: str, folder: str,
                          takeaway: str, today: date) -> None:
    """Add or replace the note's row in the evaluation log and refresh the header counts."""
    path = vault / config["folders"]["knowledge_base"] / "evaluation-log.md"
    row = _defuse(f"| [[{link_stem}\\|{_link_title(title)}]] | {today.isoformat()} | {folder} | {_cell(takeaway)} |")
    row_prefixes = (f"| [[{link_stem}\\|", f"| [[{link_stem}]]")

    if path.exists():
        lines = path.read_text().splitlines()
    else:
        lines = [
            "# Knowledge Evaluation Log", "", "Last updated: ", "Total evaluated: 0 notes", "",
            "## Aggregated Patterns", "", "## All Evaluations", "",
            LOG_HEADER, "|------|-----------|----------|-------------|",
        ]

    header_index = next((i for i, line in enumerate(lines) if line.strip() == LOG_HEADER), None)
    if header_index is None:
        lines += ["", "## All Evaluations", "", LOG_HEADER, "|------|-----------|----------|-------------|"]
        header_index = len(lines) - 2

    # Rows can be separated by blank lines (older runs appended after gaps), so every
    # "| [[" line after the header counts as a row.
    rows = [i for i in range(header_index + 2, len(lines)) if lines[i].startswith("| [[")]
    existing = next((i for i in rows if lines[i].startswith(row_prefixes)), None)
    if existing is not None:
        lines[existing] = row
        total = len(rows)
    else:
        lines.insert(rows[-1] + 1 if rows else header_index + 2, row)
        total = len(rows) + 1

    for i, line in enumerate(lines):
        if line.startswith("Last updated:"):
            lines[i] = f"Last updated: {today.isoformat()}"
        elif line.startswith("Total evaluated:"):
            lines[i] = f"Total evaluated: {total} notes"

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, "\n".join(lines) + "\n")


def _link_title(title: str) -> str:
    """Display text for a wikilink: no brackets or pipes, which would end the link or a table cell."""
    return _one_line(title.replace("[", "").replace("]", "").replace("|", "-"))


def _defuse(text: str) -> str:
    """Stop Templater from running commands found in article or model text ("<%" -> "<\\%")."""
    return text.replace("<%", "<\\%")


def _cell(text: str) -> str:
    return _one_line(text).replace("|", "\\|")


def _one_line(text: str) -> str:
    return " ".join(text.split())


# --- file writing ---------------------------------------------------------


def atomic_write(path: Path, content: str) -> None:
    """Write via a temporary file in the same folder, then rename into place."""
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
