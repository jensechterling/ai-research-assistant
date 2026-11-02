"""Process one feed entry: extract, analyze, write the note, then bookkeeping."""
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.analysis import AnalysisContext, AnalysisError, analyze
from src.extraction import ExtractionError, extract_article
from src.models import Entry
from src.vault_writer import VaultIndex, append_daily_dose, upsert_evaluation_log, write_note

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Outcome of processing one entry."""

    success: bool
    note_path: Path | None = None
    step: str | None = None  # "extraction", "analysis" or "vault" when failed
    error: str | None = None
    permanent: bool = False
    cost_eur: float = 0.0
    existing: bool = False  # a note with the entry's URL as source was already in the vault


class EntryProcessor:
    """Runs the per-entry steps; FatalRunError from any step propagates to the run loop."""

    def __init__(self, config: dict, vault_path: Path, context: AnalysisContext, llm_client, http_client,
                 today: date, extract=extract_article, analyze=analyze, write=write_note,
                 daily_dose=append_daily_dose, evaluation_log=upsert_evaluation_log,
                 index: VaultIndex | None = None):
        self._config = config
        self._vault = vault_path
        self._context = context
        self._llm = llm_client
        self._http = http_client
        self._today = today
        self._extract = extract
        self._analyze = analyze
        self._write = write
        self._daily_dose = daily_dose
        self._evaluation_log = evaluation_log
        self._index = index

    def process(self, entry: Entry) -> ProcessingResult:
        # A note for this URL already exists (clipped by hand, or filed from another feed):
        # reuse it, so nothing is downloaded, paid for or overwritten.
        existing = self._index.find_source(entry.url) if self._index is not None else None
        if existing is not None:
            return ProcessingResult(True, note_path=existing, existing=True)

        extraction = self._config["extraction"]
        try:
            article = self._extract(entry, self._http, extraction["min_words"], extraction["max_words"])
        except ExtractionError as e:
            return ProcessingResult(False, step="extraction", error=f"extraction: {e.reason}", permanent=e.permanent)

        try:
            result = self._analyze(article, self._context, self._llm, self._config["llm"]["max_output_tokens"])
        except AnalysisError as e:
            return ProcessingResult(False, step="analysis", error=f"analysis: {e}", cost_eur=e.cost_eur)
        cost = result.cost_eur

        try:
            path = self._write(self._vault, self._config, article, result.analysis, self._today, index=self._index)
        except OSError as e:
            return ProcessingResult(False, step="vault", error=f"vault: {e}", cost_eur=cost)
        if not path.is_file():
            return ProcessingResult(False, step="vault", error=f"vault: note not found after write: {path}",
                                    cost_eur=cost)

        self._bookkeeping(path, article.title, result.analysis)
        return ProcessingResult(True, note_path=path, cost_eur=cost)

    def _bookkeeping(self, path: Path, title: str, analysis) -> None:
        """Daily Dose entry and evaluation-log row; failures are warnings only."""
        folder = path.parent.relative_to(self._vault).as_posix()
        try:
            self._daily_dose(self._vault, self._config, link_stem=path.stem, title=title, folder=folder,
                             takeaway=analysis.takeaway, action=analysis.action, today=self._today)
        except Exception as e:
            logger.warning(f"    Daily note not updated for {path.name}: {e}")
        try:
            self._evaluation_log(self._vault, self._config, link_stem=path.stem, title=title,
                                 folder=path.parent.name, takeaway=analysis.takeaway, today=self._today)
        except Exception as e:
            logger.warning(f"    Evaluation log not updated for {path.name}: {e}")
