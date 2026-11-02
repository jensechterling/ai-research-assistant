# Design

## Context

See proposal.md for why. Facts that shape the approach:

- `extract_article()` returns page text as soon as it reaches `min_words` and only then looks at feed text. Feed-text extraction uses no page metadata.
- `_select_entries()` rebuilds a retry entry from its `retry_queue` row with `content=""` and `published_at=None`. A retry that is still in the feed uses the feed copy; only entries that left the feed (or whose feed failed to load) lose their text. The table has no column for either value.
- `fetch()` decodes the body with `response.encoding`, which httpx sets to UTF-8 when the header names no charset. `FetchResult.content` already holds the raw bytes. Checked on trafilatura 2.3.1: an ISO-8859-1 page passed as that decoded string loses its umlauts, and the same page passed as bytes keeps them.
- `write_note()` checks name collisions in the target folder only and overwrites a note whose `source` equals the entry URL. The Professional vault holds 1,168 notes; scanning them all for `source:` takes about 0.06 s, so a whole-vault check per run is cheap. Seven filenames are already duplicated across folders; this change does not rename them.
- `EntryProcessor.process()` catches only `OSError` from the write step. Any other exception reaches the pipeline's "unexpected" branch, which adds no cost.
- `run.sh` uses `set -e`, and a stopped run exits non-zero. On the iMac, `/usr/local/bin/git` is an Intel-only binary that fails with "Bad CPU type", and the launchd PATH lists `/usr/local/bin` first.
- The repository has no CI workflows, so pushes trigger nothing. The `backup/feeds` decision is about keeping master free of direct pushes, per the user's rules.

## Goals / Non-Goals

**Goals:**

- Fix all ten review findings, with one test per finding that fails on the old code.
- Keep the change backward compatible with the database and with notes already in the vault.

**Non-Goals:**

- URL normalisation (tracking parameters, trailing slashes) for the same-source check: exact match only.
- Renaming the seven existing duplicate filenames.
- The five low-severity review items (tag-limit order, prompt rebuilt per article, duplicate config load in `FeedManager`, YouTube and podcast rows left in `retry_queue`, local vs UTC time in the catch-up check).
- Dead feeds (First Round 404, NFX 404, Reforge 500) and `pipeline_runs.items_fetched` always being 0, both seen during the 2 November iMac run.

## Decisions

### 1. Only 403 becomes transient

401 and 402 are explicit demands for a login or payment and stay that way on retry. 403 is what Cloudflare and similar services return to clients they don't trust, and that block is often lifted. The retry queue's existing four attempts (1 h, 4 h, 12 h, 24 h) bound the extra cost to four page downloads per blocked entry, and no model calls.

Alternative: make 401, 402 and 403 transient, as the review suggested. Rejected: it adds retries that almost never succeed.

### 2. User-Agent unchanged

`feeds.user_agent` stays `AI-Research-Assistant/1.0`. PR #2's probe found every live feed's article page returns HTTP 200 with it, and neither integration run had an extraction failure, so a browser-style string would fix no observed problem. Revisit if 403s show up in the run log.

### 3. Longer text wins; page metadata is kept

`extract_article()` parses both sources and picks the one with more words, provided it reaches `min_words`. When the page was read but the feed text wins, the page's title, author, date and site name are merged with the feed text. Ties go to the page. The note and the prompt no longer say the page "could not be read" when the feed text is used; they say the page had less text or could not be read.

Alternative: prefer the feed only when it is some multiple of the page length. Rejected: the threshold would be arbitrary, and the longer text is the better input in the cases seen.

### 4. Retry rows carry feed content and publication date

`retry_queue` gains `entry_content TEXT` and `published_at TIMESTAMP`, added by the same startup migration that added `pipeline_runs.error`. `add_to_retry_queue()` stores both. Re-queuing never replaces stored content with an empty value, so a later attempt from outside the feed does not erase it. `_select_entries()` rebuilds retry entries from these columns. The 64 rows already queued on the iMac have NULLs and keep today's page-only behavior.

### 5. One vault index per run

A `VaultIndex` is built once per run: it walks the vault (skipping hidden folders), reads the frontmatter of notes that start with `---`, and keeps a `source → path` map and a set of lower-cased filename stems. Comparison is case-insensitive because macOS file names and Obsidian links are. The processor checks the index first, before extraction, so a match costs neither a download nor a model call. On a hit it returns `ProcessingResult(success=True, existing=True, note_path=<existing>, cost_eur=0)`, with no write and no bookkeeping. `_process_entries()` handles `existing` before its success branch: it calls `mark_processed()` with that path and removes the entry from the retry queue, but does not touch `processed`, `retried`, `created_notes` or `analysis_worked`, and logs `[EXISTS] <title> → <path>`. `write_note()` picks the first stem not in the index, then adds both the new stem and the new `source → path` pair, so a second entry for the same URL in the same run is matched. A frontmatter `source` that is not a string is ignored.

Alternative: check only the target folder before writing, as today. Rejected: the target folder is known only after analysis, so the model call would already be paid for, and links resolve vault-wide.

### 6. Bytes to trafilatura when the header names no charset

`fetch()` exposes the charset from the header, or `None`. With a header charset, trafilatura gets the decoded string as today. Without one, it gets `FetchResult.content`, and its own detection reads `<meta charset>`.

### 7. Templater dates through a tokenizer

The single-pass `str.replace` chain becomes one regex over the Moment tokens (`YYYY`, `YY`, `MMMM`, `MMM`, `MM`, `M`, `Do`, `DD`, `D`, `dddd`, `ddd`), with each token formatted in Python. A single pass stops a short token like `D` from matching inside output already produced. The expression regex accepts an optional integer second argument, which shifts the date by that many days. Anything else inside `<% %>` is left as it is.

### 8. Cost survives later failures

`process()` catches any `Exception` from the write step, not just `OSError`, and returns a vault-step failure that carries the analysis cost. `FatalRunError` gains a `cost_eur` field. `FatalRunError` is not a subclass of `LLMError`, so it passes straight through the `request()` helper inside `analyze()`; that helper gets an `except FatalRunError` that sets `cost_eur` to the cost so far and re-raises. The pipeline adds it to the run total before re-raising.

### 9. `run.sh` keeps the pipeline's exit status but always runs the backup

The pipeline call becomes `$UV run ai-research-assistant run || status=$?`. The backup runs next, and the script exits with the pipeline's status, so launchd still sees a failed run. When the pipeline succeeded, a failed backup sets the exit status instead, so a broken backup is not silent.

### 10. Backup commits to `backup/feeds` without touching the checkout

`backup_feeds.sh` builds the commit with git plumbing and a temporary index file (`GIT_INDEX_FILE`). The tree holds only `exports/feeds.opml`. The parent is the local `backup/feeds` branch, or `origin/backup/feeds` after a fetch, or none on the first run. If the new tree equals the parent's tree, nothing is committed or pushed. Otherwise the script updates `refs/heads/backup/feeds` and runs `git push origin backup/feeds`. The working tree, the real index and the checked-out branch are never touched, so the master-only guard goes away.

Alternative: check out `backup/feeds` in a temporary worktree. Rejected: it is slower, and it leaves state behind if the script is killed.

### 11. launchd PATH order

The plist template's PATH becomes `/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin`. Homebrew's arm64 git wins, and `/usr/bin/git` is the fallback. The broken binary in `/usr/local/bin` stays on the user's machine; removing it is the user's call.

## Risks / Trade-offs

- [403 entries that never open stay in the queue for about 41 hours before being dropped] → That is the existing retry ceiling; the log shows each attempt.
- [Feed text will win for most entries: PR #2's probe found full text in 10 of 11 live feeds, so page and feed lengths are often close and the winner can flip on a few words] → Page metadata is kept either way; the text differs mainly in boilerplate. Check `from_feed` in the first week's notes.
- [The feed text can win while carrying newsletter footers or sponsor blocks] → Trafilatura already strips most of these from feed HTML; the note's collapsed original-text callout shows what was used.
- [Exact URL match misses the same article under a different URL] → Accepted for now (see Non-Goals); the cost is a duplicate note, as today.
- [Stored feed content enlarges `retry_queue`] → Rows are deleted on success or give-up; the queue is a few hundred rows at most.
- [The vault walk reads every note once per run] → 0.06 s at today's size; it grows linearly with the vault.

## Migration Plan

1. Merge PR #3 (archive of `api-pipeline`) first, then rebase this branch onto master.
2. After merge, on the iMac: `git pull && uv sync`, then `uv run ai-research-assistant setup --install-schedule`, which re-renders the plist with the new PATH and reloads launchd.
3. `uv run ai-research-assistant run --dry-run`, then check the next 06:00 run in `~/.claude/logs/ai-research-assistant.log`.
4. On the first Monday, confirm that `origin/backup/feeds` exists, that its tree holds only `exports/feeds.opml`, and that master is unchanged.

**Rollback:** revert the merge. The two new `retry_queue` columns are nullable and ignored by the old code. Notes written in the meantime are plain Markdown.
