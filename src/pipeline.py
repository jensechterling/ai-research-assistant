"""Main pipeline orchestration."""
import fcntl
import logging
import os
import subprocess
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from src.analysis import load_context
from src.config import get_project_dir, get_vault_path, load_config
from src.database import Database
from src.feed_manager import FeedManager
from src.llm import FatalRunError, MeliousClient, resolve_api_key
from src.models import Entry
from src.processor import EntryProcessor

logger = logging.getLogger(__name__)

SUPPORTED_CATEGORY = "articles"
ANALYSIS_FAILURES_TO_STOP = 3  # analysis failures in a row, before any analysis worked, that stop a run
NOTIFICATION_TITLE = "Content Pipeline"

LOCK_PATH = Path(__file__).parent.parent / "data" / "pipeline.lock"


class PipelineLockError(Exception):
    """Raised when the pipeline lock cannot be acquired."""

    def __init__(self, pid: int | None = None):
        self.pid = pid
        msg = "Pipeline is already running"
        if pid:
            msg += f" (PID {pid})"
        super().__init__(msg)


class PipelineLock:
    """File-based lock using fcntl.flock() to prevent concurrent pipeline runs."""

    def __init__(self, lock_path: Path = LOCK_PATH):
        self.lock_path = lock_path
        self._fd: int | None = None

    def acquire(self) -> None:
        """Acquire the pipeline lock. Raises PipelineLockError if already held."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Lock is held — read PID for diagnostics
            pid = None
            try:
                content = os.pread(self._fd, 32, 0).decode().strip()
                if content:
                    pid = int(content)
            except (ValueError, OSError):
                pass
            os.close(self._fd)
            self._fd = None
            raise PipelineLockError(pid)
        # Write our PID
        os.ftruncate(self._fd, 0)
        os.pwrite(self._fd, str(os.getpid()).encode(), 0)

    def release(self) -> None:
        """Release the pipeline lock."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


@dataclass
class PipelineResult:
    """Result from running the pipeline."""

    processed: int = 0
    failed: int = 0
    retried: int = 0
    skipped: int = 0  # entries listed by a dry run
    permanent_failures: int = 0
    stale: int = 0
    unsupported: int = 0
    cost_eur: float = 0.0
    stopped_reason: str | None = None  # set when a fatal error stopped the run
    limit_reason: str | None = None  # set when the time or cost limit was reached
    dry_run: bool = False
    created_notes: list[Path] = field(default_factory=list)
    failures: list[tuple[Entry, str]] = field(default_factory=list)


def build_processor(config: dict, today: date) -> EntryProcessor:
    """Check the vault, profile and API key, then build the per-entry processor."""
    try:
        vault = get_vault_path(config)
    except ValueError as e:
        raise FatalRunError(str(e)) from None
    if not vault.is_dir():
        raise FatalRunError(f"Vault folder not found: {vault}")
    context = load_context(config, vault, today)
    key = resolve_api_key(config["llm"]["keychain_service"], get_project_dir() / ".env")
    http_client = httpx.Client(
        timeout=config["feeds"]["request_timeout"],
        headers={"User-Agent": config["feeds"]["user_agent"]},
        follow_redirects=True,
    )
    return EntryProcessor(config, vault, context, MeliousClient(config["llm"], key), http_client, today)


def run_pipeline(
    db: Database,
    dry_run: bool = False,
    limit: int | None = None,
    verbose: bool = False,
    force: bool = False,
    *,
    config: dict | None = None,
    feed_manager=None,
    processor_factory: Callable[[dict, date], EntryProcessor] = build_processor,
    now: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
    notify: Callable[[PipelineResult], None] | None = None,
) -> PipelineResult:
    """Execute the content pipeline."""
    # Acquire lock (skip for dry-run)
    lock = None
    if not dry_run:
        lock = PipelineLock(LOCK_PATH)
        if force:
            try:
                lock.acquire()
            except PipelineLockError as e:
                logger.warning(f"Force override: {e}")
                lock = None
        else:
            lock.acquire()

    try:
        return _run_pipeline_inner(
            db, dry_run, limit, verbose,
            config=config if config is not None else load_config(),
            feed_manager=feed_manager if feed_manager is not None else FeedManager(db),
            processor_factory=processor_factory,
            now=now or datetime.now(),
            clock=clock,
            notify=notify or send_notification,
        )
    finally:
        if lock is not None:
            lock.release()


def _run_pipeline_inner(db: Database, dry_run: bool, limit: int | None, verbose: bool, *, config: dict,
                        feed_manager, processor_factory, now: datetime, clock, notify) -> PipelineResult:
    """Inner pipeline logic (called with lock held)."""
    result = PipelineResult(dry_run=dry_run)

    if dry_run:
        entries, retry_guids = _select_entries(db, feed_manager, config, now, limit, result)
        for entry in entries:
            marker = " [retry]" if entry.guid in retry_guids else ""
            logger.info(f"[DRY RUN] Would process: {entry.title}{marker}")
        result.skipped = len(entries)
        return result

    # Check for catch-up (missed runs)
    last_run = db.get_last_successful_run()
    if last_run:
        hours_since = (datetime.now() - last_run).total_seconds() / 3600
        if hours_since > 36:
            logger.warning(f"Catch-up mode: {hours_since:.1f} hours since last run")

    run_id = db.record_run_start()
    try:
        processor = processor_factory(config, now.date())
        entries, retry_guids = _select_entries(db, feed_manager, config, now, limit, result)
        _process_entries(db, processor, entries, retry_guids, config, clock, verbose, result)
    except FatalRunError as e:
        result.stopped_reason = str(e)
        logger.error(f"Run stopped: {e}")
        db.record_run_failed(run_id, result.processed, result.failed, str(e))
        notify(result)
        return result
    except BaseException as e:
        result.stopped_reason = f"{type(e).__name__}: {e}"
        db.record_run_failed(run_id, result.processed, result.failed, result.stopped_reason)
        if isinstance(e, Exception):
            notify(result)
        raise

    db.record_run_complete(run_id, result.processed, result.failed)
    logger.info(
        f"Done: {result.processed} processed, {result.failed} failed, "
        f"{result.permanent_failures} skipped (not extractable), {result.retried} retried, "
        f"EUR {result.cost_eur:.4f}"
    )
    notify(result)
    return result


def _select_entries(db: Database, feed_manager, config: dict, now: datetime, limit: int | None,
                    result: PipelineResult) -> tuple[list[Entry], set[str]]:
    """Merge new and due retry entries, drop unsupported, waiting and stale ones, apply the limit."""
    new_entries = feed_manager.fetch_new_entries()
    retry_rows = db.get_retry_candidates()
    queued = db.get_queued_guids()
    due_guids = {row["entry_guid"] for row in retry_rows}

    unsupported = Counter()
    entries: list[Entry] = []
    seen: set[str] = set()
    for entry in new_entries:
        if entry.category != SUPPORTED_CATEGORY:
            unsupported[(entry.feed_title or str(entry.feed_id), entry.category)] += 1
            continue
        if entry.guid in queued and entry.guid not in due_guids:
            continue  # waiting for its retry time
        entries.append(entry)
        seen.add(entry.guid)

    for row in retry_rows:
        if row["entry_guid"] in seen:
            continue  # the feed copy is used: it has content and a date
        if row["category"] != SUPPORTED_CATEGORY:
            unsupported[(f"feed {row['feed_id']}", row["category"])] += 1
            continue
        entries.append(Entry(
            guid=row["entry_guid"], title=row["entry_title"] or "Untitled", url=row["entry_url"], content="",
            author=None, published_at=None, feed_id=row["feed_id"], feed_title="", category=row["category"],
        ))

    for (feed, category), count in unsupported.items():
        logger.info(f"Skipped {count} {category} entries from {feed}: use the manual /{category.rstrip('s')} skill")
    result.unsupported = sum(unsupported.values())

    cutoff = now - timedelta(days=config["processing"]["max_entry_age_days"])
    fresh = [
        e for e in entries
        if e.guid in due_guids or e.published_at is None or e.published_at >= cutoff
    ]
    result.stale = len(entries) - len(fresh)
    if result.stale:
        logger.info(f"Skipped {result.stale} stale entries (older than {config['processing']['max_entry_age_days']} days)")

    retries = sum(1 for e in fresh if e.guid in due_guids)
    logger.info(f"Found {len(fresh) - retries} new entries, {retries} retries")
    if limit is not None and limit < len(fresh):
        fresh = fresh[:limit]
        logger.info(f"Limited to {limit}")
    return fresh, due_guids


def _process_entries(db: Database, processor, entries: list[Entry], retry_guids: set[str], config: dict,
                     clock, verbose: bool, result: PipelineResult) -> None:
    max_seconds = config["processing"]["max_run_minutes"] * 60
    max_cost = config["llm"]["max_cost_per_run_eur"]
    start = clock()
    total = len(entries)
    analysis_worked = False
    analysis_failures = 0

    for idx, entry in enumerate(entries, 1):
        if clock() - start >= max_seconds:
            result.limit_reason = f"time limit of {config['processing']['max_run_minutes']} minutes reached"
        elif result.cost_eur >= max_cost:
            result.limit_reason = f"cost limit of EUR {max_cost:.2f} reached"
        if result.limit_reason:
            logger.warning(f"Stopping early: {result.limit_reason}; {total - idx + 1} entries left for the next run")
            return

        is_retry = entry.guid in retry_guids
        if verbose:
            logger.info(f"[{idx}/{total}] Processing: {entry.title}{' [retry]' if is_retry else ''}")

        # Skip if already processed (clears zombie retries)
        if db.is_processed(entry.guid):
            if is_retry:
                db.remove_from_retry_queue(entry.guid)
            continue

        try:
            outcome = processor.process(entry)
        except FatalRunError:
            raise
        except Exception as e:
            outcome = None
            error = f"unexpected: {type(e).__name__}: {e}"
        else:
            error = outcome.error or "Unknown error"
            result.cost_eur += outcome.cost_eur

        if outcome is not None and (outcome.success or outcome.step == "vault"):
            analysis_worked = True

        if outcome is not None and outcome.success:
            db.mark_processed(entry.guid, entry.feed_id, entry.url, entry.title, outcome.note_path)
            if is_retry:
                db.remove_from_retry_queue(entry.guid)
                result.retried += 1
            result.created_notes.append(outcome.note_path)
            result.processed += 1
            if verbose:
                logger.info(f"    ✓ Created: {outcome.note_path.name} (EUR {outcome.cost_eur:.4f})")
        elif outcome is not None and outcome.permanent:
            db.mark_processed(entry.guid, entry.feed_id, entry.url, entry.title, None)
            if is_retry:
                db.remove_from_retry_queue(entry.guid)
            result.permanent_failures += 1
            logger.warning(f"[PERMANENT] {entry.title}: {error}")
        else:
            still_queued = db.add_to_retry_queue(
                entry_guid=entry.guid, feed_id=entry.feed_id, entry_url=entry.url,
                entry_title=entry.title, category=entry.category, error=error,
            )
            if not still_queued:
                db.mark_processed(entry.guid, entry.feed_id, entry.url, entry.title, None)
                logger.warning(f"[GAVE UP] {entry.title}: no attempts left, last error: {error}")
            result.failed += 1
            result.failures.append((entry, error))
            if verbose:
                logger.error(f"    ✗ {error}")

            # Analysis failing for every entry points at the API or the config, not the articles:
            # stop instead of spending every entry's retry attempts on it.
            if outcome is not None and outcome.step == "analysis" and not analysis_worked:
                analysis_failures += 1
                if analysis_failures >= ANALYSIS_FAILURES_TO_STOP:
                    raise FatalRunError(
                        f"{analysis_failures} analyses failed in a row at the start of the run; last error: {error}"
                    )


def notification_text(result: PipelineResult) -> tuple[str, str]:
    """Return (title, message) for the end-of-run notification."""
    if result.stopped_reason:
        return "Run stopped", result.stopped_reason[:150]
    parts = [f"Processed {result.processed}"]
    if result.failed:
        parts.append(f"Failed {result.failed}")
    if result.permanent_failures:
        parts.append(f"{result.permanent_failures} skipped (not extractable)")
    if result.retried:
        parts.append(f"{result.retried} retried")
    parts.append(f"EUR {result.cost_eur:.2f}")
    return NOTIFICATION_TITLE, ", ".join(parts)


def send_notification(result: PipelineResult) -> None:
    """Show a macOS notification; text is passed as arguments so quotes cannot break it."""
    title, message = notification_text(result)
    try:
        subprocess.run(
            [
                "osascript",
                "-e", "on run argv",
                "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                "-e", "end run",
                message,
                title,
            ],
            capture_output=True,
        )
    except Exception:
        pass  # Ignore notification failures
