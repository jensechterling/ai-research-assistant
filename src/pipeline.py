"""Main pipeline orchestration."""
import fcntl
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.database import Database
from src.feed_manager import FeedManager
from src.models import Entry
from src.skill_runner import SkillRunner

logger = logging.getLogger(__name__)

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
    skipped: int = 0
    permanent_failures: int = 0
    created_notes: list[Path] = field(default_factory=list)
    failures: list[tuple[Entry, str]] = field(default_factory=list)


def run_pipeline(db: Database, dry_run: bool = False, limit: int | None = None, verbose: bool = False, force: bool = False) -> PipelineResult:
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
        return _run_pipeline_inner(db, dry_run, limit, verbose)
    finally:
        if lock is not None:
            lock.release()


def _run_pipeline_inner(db: Database, dry_run: bool, limit: int | None, verbose: bool) -> PipelineResult:
    """Inner pipeline logic (called with lock held)."""
    feed_manager = FeedManager(db)
    skill_runner = SkillRunner()

    # Validate required skills are installed
    missing_skills = skill_runner.validate_skills()
    if missing_skills:
        logger.error(f"Missing required skills: {', '.join(missing_skills)}")
        logger.error("Run 'ai-research-assistant setup' to install skills")
        return PipelineResult()

    # Check for catch-up (missed runs)
    last_run = db.get_last_successful_run()
    if last_run:
        hours_since = (datetime.now() - last_run).total_seconds() / 3600
        if hours_since > 36:
            logger.warning(f"Catch-up mode: {hours_since:.1f} hours since last run")

    # Start pipeline run
    run_id = db.record_run_start()

    # Fetch new entries + retry candidates
    new_entries = feed_manager.fetch_new_entries()
    retry_rows = db.get_retry_candidates()

    # Convert retry rows to Entry objects
    retry_entries = []
    for row in retry_rows:
        retry_entries.append(
            Entry(
                guid=row["entry_guid"],
                title=row["entry_title"] or "Untitled",
                url=row["entry_url"],
                content="",
                author=None,
                published_at=None,
                feed_id=row["feed_id"],
                feed_title="",
                category=row["category"],
            )
        )

    all_entries = new_entries + retry_entries

    # Apply limit if specified
    if limit is not None and limit < len(all_entries):
        all_entries = all_entries[:limit]
        logger.info(f"Found {len(new_entries)} new entries, {len(retry_entries)} retries (limited to {limit})")
    else:
        logger.info(f"Found {len(new_entries)} new entries, {len(retry_entries)} retries")

    if dry_run:
        for entry in all_entries:
            logger.info(f"[DRY RUN] Would process: {entry.title} ({entry.category})")
        return PipelineResult(skipped=len(all_entries))

    # Process entries sequentially
    result = PipelineResult()
    total = len(all_entries)

    for idx, entry in enumerate(all_entries, 1):
        is_retry = entry in retry_entries

        if verbose:
            retry_marker = " [retry]" if is_retry else ""
            logger.info(f"[{idx}/{total}] Processing: {entry.title}{retry_marker}")

        try:
            # Skip if already processed (clears zombie retries)
            if db.is_processed(entry.guid):
                if is_retry:
                    db.remove_from_retry_queue(entry.guid)
                    if verbose:
                        logger.info("    Already processed, removed from retry queue")
                continue

            skill_result = skill_runner.run_skill(entry)

            if skill_result.success:
                # Mark as processed
                db.mark_processed(
                    entry_guid=entry.guid,
                    feed_id=entry.feed_id,
                    entry_url=entry.url,
                    entry_title=entry.title,
                    note_path=skill_result.note_path,
                )

                # Remove from retry queue if it was a retry
                if is_retry:
                    db.remove_from_retry_queue(entry.guid)
                    result.retried += 1

                result.created_notes.append(skill_result.note_path)
                result.processed += 1
                if verbose:
                    logger.info(f"    ✓ Created: {skill_result.note_path.name}")
            else:
                error_msg = skill_result.error or "Unknown error"
                if skill_result.permanent:
                    # Permanent failure — skip retry queue
                    result.permanent_failures += 1
                    logger.warning(f"[PERMANENT] {entry.title}: {error_msg}")
                else:
                    # Transient failure — add to retry queue
                    db.add_to_retry_queue(
                        entry_guid=entry.guid,
                        feed_id=entry.feed_id,
                        entry_url=entry.url,
                        entry_title=entry.title,
                        category=entry.category,
                        error=error_msg,
                    )
                    result.failed += 1
                    result.failures.append((entry, error_msg))
                    if verbose:
                        logger.error(f"    ✗ {error_msg}")

        except Exception as e:
            db.add_to_retry_queue(
                entry_guid=entry.guid,
                feed_id=entry.feed_id,
                entry_url=entry.url,
                entry_title=entry.title,
                category=entry.category,
                error=str(e),
            )
            result.failed += 1
            result.failures.append((entry, str(e)))
            if verbose:
                logger.error(f"    ✗ Exception: {e}")

    # Post-process with /evaluate-knowledge in batches
    if result.created_notes:
        vault_path = skill_runner.vault_path
        relative_paths = []
        for p in result.created_notes:
            try:
                rel = p.relative_to(vault_path)
                relative_paths.append(str(rel))
            except ValueError:
                relative_paths.append(str(p))

        batch_size = 6
        batches = [relative_paths[i : i + batch_size] for i in range(0, len(relative_paths), batch_size)]
        logger.info(
            f"Running /evaluate-knowledge on {len(relative_paths)} new notes "
            f"({len(batches)} batch{'es' if len(batches) != 1 else ''} of up to {batch_size})"
        )

        for batch_idx, batch in enumerate(batches, 1):
            file_list = " ".join(f'"{p}"' for p in batch)
            try:
                subprocess.run(
                    [
                        "claude",
                        "--print",
                        "--dangerously-skip-permissions",
                        f"/evaluate-knowledge {file_list}",
                    ],
                    timeout=600,
                    capture_output=True,
                )
                logger.info(f"    Batch {batch_idx}/{len(batches)} done ({len(batch)} notes)")
            except subprocess.TimeoutExpired:
                logger.warning(f"    Batch {batch_idx}/{len(batches)} timed out after 600s, continuing")
            except Exception as e:
                logger.warning(f"    Batch {batch_idx}/{len(batches)} failed: {e}, continuing")

    # Record run completion
    db.record_run_complete(run_id, result.processed, result.failed)

    # Send notification
    send_notification(result)

    return result


def send_notification(result: PipelineResult) -> None:
    """Send macOS notification with pipeline results."""
    title = "Content Pipeline"

    if result.skipped > 0:
        message = f"Dry run: {result.skipped} items previewed"
    elif result.processed == 0 and result.failed == 0 and result.permanent_failures == 0:
        message = "No items to process"
    elif result.failed > 0:
        message = f"Processed {result.processed}, Failed {result.failed}"
        if result.permanent_failures > 0:
            message += f", {result.permanent_failures} skipped (paywall)"
        first_fail = result.failures[0]
        message += f"\nFirst failure: {first_fail[0].title[:30]}..."
    else:
        message = f"Processed {result.processed} items"
        if result.retried > 0:
            message += f" ({result.retried} retried)"
        if result.permanent_failures > 0:
            message += f", {result.permanent_failures} skipped (paywall)"

    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            capture_output=True,
        )
    except Exception:
        pass  # Ignore notification failures
