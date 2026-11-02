"""Write analyzed articles into the Obsidian vault: notes, Daily Dose, evaluation log."""
import os
import re
import stat
import tempfile
from datetime import date, timedelta
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

# Moment.js tokens used by Templater, longest first so "YYYY" wins over "YY". One regex pass
# means a short token like "D" never matches inside text another token produced.
# Text in [brackets] is literal, as in Moment.
_MOMENT_TOKEN = re.compile(r"\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|Do|DD|D|dddd|ddd")
_MOMENT_FORMATS = {
    "YYYY": lambda d: f"{d.year:04d}",
    "YY": lambda d: f"{d.year % 100:02d}",
    "MMMM": lambda d: d.strftime("%B"),
    "MMM": lambda d: d.strftime("%b"),
    "MM": lambda d: f"{d.month:02d}",
    "M": lambda d: str(d.month),
    "Do": lambda d: _ordinal(d.day),
    "DD": lambda d: f"{d.day:02d}",
    "D": lambda d: str(d.day),
    "dddd": lambda d: d.strftime("%A"),
    "ddd": lambda d: d.strftime("%a"),
}
# tp.date.now(), tp.date.now("FORMAT") or tp.date.now("FORMAT", N) with N an integer day offset
_TEMPLATER_DATE = re.compile(
    r'<%\s*tp\.date\.now\(\s*(?:(?:"([^"]*)"|\'([^\']*)\')\s*(?:,\s*(-?\d+)\s*)?)?\)\s*%>'
)


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


def write_note(vault: Path, config: dict, article: ExtractedArticle, analysis: Analysis, today: date,
               index: "VaultIndex | None" = None) -> Path:
    """File the note into the knowledge base under a filename unused anywhere in the vault.

    An existing note is never overwritten. The new note is added to the index, so a later
    entry in the same run sees its name and source.
    """
    if index is None:
        index = VaultIndex.build(vault)
    folders = config["folders"]
    kb_path = vault / folders["knowledge_base"]
    folder = _resolve_folder(kb_path, folders["knowledge_base"], analysis.kb_folder, folders["kb_fallback"])
    folder.mkdir(parents=True, exist_ok=True)

    base = sanitize_filename(article.title)
    stem, suffix = base, 2
    while index.has_stem(stem) or (folder / f"{stem}.md").exists():
        stem = f"{base}-{suffix}"
        suffix += 1
    path = folder / f"{stem}.md"

    atomic_write(path, render_note(article, analysis, today))
    index.add(path, article.url)
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


# --- vault index ----------------------------------------------------------

FRONTMATTER_READ_LIMIT = 65_536  # frontmatter sits at the top; no need to read whole notes


class VaultIndex:
    """Source URLs and filename stems of every note in the vault, built once per run.

    Links to notes use the bare filename and Obsidian resolves them vault-wide and
    case-insensitively, so stems are compared lower-cased across the whole vault.
    Hidden folders (.obsidian, .trash) are skipped.
    """

    def __init__(self) -> None:
        self._sources: dict[str, Path] = {}
        self._stems: set[str] = set()

    @classmethod
    def build(cls, vault: Path) -> "VaultIndex":
        index = cls()
        for root, dirs, files in os.walk(vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if name.endswith(".md") and not name.startswith("."):
                    path = Path(root) / name
                    index.add(path, _note_source(path))
        return index

    def add(self, path: Path, source: str | None) -> None:
        self._stems.add(path.stem.lower())
        if source and source not in self._sources:
            self._sources[source] = path

    def find_source(self, url: str) -> Path | None:
        return self._sources.get(url)

    def has_stem(self, stem: str) -> bool:
        return stem.lower() in self._stems


def _note_source(path: Path) -> str | None:
    """The note's frontmatter `source` when it is a string, else None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(FRONTMATTER_READ_LIMIT)
    except OSError:
        return None
    if not head.startswith("---\n"):
        return None
    parts = head.split("\n---", 1)
    if len(parts) < 2:
        return None
    try:
        frontmatter = yaml.safe_load(parts[0][4:])
    except Exception:  # YAMLError, ValueError for dates like 2024-02-30, RecursionError: one odd note must not stop a run
        return None
    source = frontmatter.get("source") if isinstance(frontmatter, dict) else None
    return source if isinstance(source, str) else None


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
        day = today + timedelta(days=int(match.group(3) or 0))
        return _MOMENT_TOKEN.sub(
            lambda token: token.group(1) if token.group(1) is not None else _MOMENT_FORMATS[token.group(0)](day), fmt
        )

    return _TEMPLATER_DATE.sub(replace, text)


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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
