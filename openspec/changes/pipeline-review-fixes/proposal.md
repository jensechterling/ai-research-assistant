# Proposal

## Why

A code review of the Melious API pipeline (PR #2) found ten defects. Four lose articles or overwrite notes the user wrote by hand. On 2 November 2026 the new pipeline processed its first entries on the iMac, so these rules now decide what reaches the vault every morning.

PR #2's own review accepted three of the ten as rare or harmless (`openspec/changes/archive/2026-10-31-api-pipeline/design.md`, "Not changed"): same-title notes in different folders, cost lost when writing raises a non-`OSError`, and `run.sh` skipping the Monday backup after a stopped run. They are fixed here because each fix is small and the user asked for all ten.

## What Changes

- An HTTP 403 page response becomes a transient failure: it is retried, not marked "not extractable" at once. Cloudflare, Medium and Substack often answer 403 to an unknown client, and that block is often temporary. 401, 402, 404, 410 and 451 stay permanent.
- Extraction uses whichever of page text and feed text has more words, instead of the page whenever it reaches `extraction.min_words`. A 250-word paywall teaser no longer beats a 3,000-word `content:encoded`.
- Retry-queue rows store the entry's feed text and publication date, so a retry keeps its feed-text fallback after the item has left the feed.
- When a knowledge-base note with the same `source` URL already exists, the entry is recorded as processed with that note. It is not analyzed again and the note is not overwritten. **BREAKING** for the old "same source already written: that note is replaced" behavior.
- Note filenames are unique across the whole vault, not only the target folder, so Daily Dose and evaluation-log links (which use the bare filename) point to one note.
- Daily-note creation resolves `tp.date.now("FORMAT", offset)` and the Moment tokens `Do`, `D` and `M`.
- Bug fixes with no spec change:
  - pages are decoded using the charset in the HTML when the HTTP header gives none
  - analysis cost already spent is counted when a later step raises
  - `run.sh` still runs the Monday OPML backup after a stopped run
  - `backup_feeds.sh` commits only `exports/feeds.opml` and pushes only when it made a commit
  - the launchd PATH no longer finds an Intel-only `/usr/local/bin/git` before the Homebrew one

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `content-extraction`: page vs feed text choice by length; 403 transient; retry entries keep stored feed text.
- `vault-output`: existing note for the same source is reused, not replaced; filenames unique vault-wide; evaluation-log row no longer replaced by a rewrite; Templater date expressions with an offset and more Moment tokens.
- `entry-processing`: the existing-note check runs first in the per-entry order; a matched entry is stored as processed but not counted in the run totals, and does not count as an analysis that worked.

## Impact

- Code: `src/extraction.py`, `src/http_fetch.py`, `src/pipeline.py`, `src/processor.py`, `src/database.py`, `src/vault_writer.py`, `src/llm.py`, `src/analysis.py`, `scripts/run.sh`, `scripts/backup_feeds.sh`, `templates/com.claude.ai-research-assistant.plist.j2`, `templates/notes/article.md.j2`, `templates/prompts/analysis-user.md.j2`.
- Database: two nullable columns on `retry_queue` (`entry_content`, `published_at`), added by the existing startup migration. The old code ignores them.
- launchd: the plist changes, so the iMac needs `setup --install-schedule` once after merge.
- Cost: 403 retries add up to four page downloads per blocked entry and no model calls. Skipping analysis for already-filed URLs saves the model call.
- Depends on PR #3 (archive of `api-pipeline`), which creates the `content-extraction` and `vault-output` main specs this change modifies.
