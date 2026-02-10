"""Main pipeline orchestration."""
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.database import Database
from src.feed_manager import FeedManager
from src.models import Entry
from src.skill_runner import SkillRunner

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result from running the pipeline."""

    processed: int = 0
    failed: int = 0
    retried: int = 0
    skipped: int = 0
    created_notes: list[Path] = field(default_factory=list)
    failures: list[tuple[Entry, str]] = field(default_factory=list)


def run_pipeline(db: Database, dry_run: bool = False, limit: int | None = None, verbose: bool = False) -> PipelineResult:
    """Execute the content pipeline."""
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
                # Add to retry queue
                db.add_to_retry_queue(
                    entry_guid=entry.guid,
                    feed_id=entry.feed_id,
                    entry_url=entry.url,
                    entry_title=entry.title,
                    category=entry.category,
                    error=skill_result.error or "Unknown error",
                )
                result.failed += 1
                result.failures.append((entry, skill_result.error or "Unknown error"))
                if verbose:
                    logger.error(f"    ✗ {skill_result.error}")

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
    elif result.processed == 0 and result.failed == 0:
        message = "No items to process"
    elif result.failed > 0:
        message = f"Processed {result.processed}, Failed {result.failed}"
        first_fail = result.failures[0]
        message += f"\nFirst failure: {first_fail[0].title[:30]}..."
    else:
        message = f"Processed {result.processed} items"
        if result.retried > 0:
            message += f" ({result.retried} retried)"

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
