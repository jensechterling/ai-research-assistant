# Tasks

Every fix starts with a test that fails on the current code (test first), then the change that makes it pass.

## 1. Page download and extraction

- [ ] 1.1 In `src/http_fetch.py`, expose the header charset (or `None`) on `FetchResult`; in `src/extraction.py`, pass `content` bytes to trafilatura when it is `None`. Done when a test serving an ISO-8859-1 page with `<meta charset="iso-8859-1">` and no header charset gets `Grüße aus München` back, and fails on the old code.
- [ ] 1.2 Move 403 out of `PERMANENT_STATUSES`. Done when `tests/test_extraction.py` shows 403 with short feed text raises a transient `ExtractionError`, and 401, 402, 404, 410 and 451 stay permanent.
- [ ] 1.3 Choose the text with more words (page wins ties), keeping page metadata when the feed text wins. Done when tests cover the paywall-teaser scenario (250-word page, 3,000-word feed: feed text, page title and author, `from_feed=True`) and the readable-article scenario (page longer: page text).
## 2. Retry entries keep their feed text

- [ ] 2.1 Add nullable `entry_content` and `published_at` columns to `retry_queue` in the startup migration in `src/database.py`. Done when a test opens a database created with the old schema and finds both columns, with existing rows intact.
- [ ] 2.2 Store both in `add_to_retry_queue()`, never replacing stored content with an empty value on re-queue. Done when tests cover first queueing, re-queueing with content, and re-queueing with empty content (stored text kept).
- [ ] 2.3 Rebuild retry entries in `_select_entries()` from the stored columns. Done when a pipeline test queues an entry with 1,200 words of feed content, drops it from the feed, serves a 403 page, and gets a note; a second test with NULL content still uses the page only.

## 3. Vault index: same source and unique filenames

- [ ] 3.1 Add `VaultIndex` to `src/vault_writer.py`: one walk of the vault skipping hidden folders, a `source → path` map from frontmatter, lower-cased stems. Done when tests cover notes without frontmatter, a non-string `source`, a hidden folder that is skipped, and a case-only stem difference.
- [ ] 3.2 Check the index in `EntryProcessor.process()` before extraction; on a hit, return `ProcessingResult(success=True, existing=True, ...)` with the existing path, zero cost and no download, write or bookkeeping. Done when the clipped-note scenario test shows the note's bytes unchanged and no extract or analyze call.
- [ ] 3.3 Make `write_note()` pick the first stem free in the index and add the new stem and `source → path` pair to it; remove the overwrite-on-same-source branch. Done when the same-title-in-another-folder test writes `Weekly-Roundup-2.md` and its Daily Dose and log links use that stem.
- [ ] 3.4 Build the index once in `build_processor()` and pass it in; in `_process_entries()`, handle `existing` before the success branch (`mark_processed` with the existing path, remove from the retry queue, `[EXISTS]` log line, no change to `processed`, `retried`, `created_notes` or `analysis_worked`). Done when pipeline tests show: two entries for one URL make one model call and one note; the "Processed 3" scenario from the entry-processing spec; and an existing-note match followed by 3 analysis failures still stops the run.

## 4. Daily-note Templater dates

- [ ] 4.1 Replace the token chain in `_resolve_templater_dates()` with a one-pass tokenizer (`YYYY YY MMMM MMM MM M Do DD D dddd ddd`) and accept an optional integer day offset. Done when tests give `2026-11-01` and `2026-11-03` for offsets -1 and 1, `Monday, November 2nd 2026` for `dddd, MMMM Do YYYY`, `2.11.2026` for `D.M.YYYY`, and leave other `<% %>` commands untouched.

## 5. Cost accounting

- [ ] 5.1 Catch any `Exception` from the write step in `process()` and return a vault failure carrying the analysis cost. Done when a test whose writer raises `UnicodeDecodeError` gets a result with the analysis cost, and the run total includes it.
- [ ] 5.2 Add `cost_eur` to `FatalRunError`; set it in `analyze()` when a repair or truncation retry hits an account error after a paid request, and add it to the run total in the pipeline before re-raising. Done when a test with a paid first request and a 402 on the repair turn records the first request's cost on the failed run.

## 6. Scripts and launchd

- [ ] 6.1 In `scripts/run.sh`, capture the pipeline's exit status, run `backup_feeds.sh`, then exit with that status. Done when a test with a failing pipeline stub on a Monday shows the backup ran and the script exits non-zero.
- [ ] 6.2 Rewrite `scripts/backup_feeds.sh` to commit `exports/feeds.opml` onto `backup/feeds` with a temporary index, push only when the tree changed, and drop the master-only guard. Update `tests/test_backup_script.py` with a bare remote. Done when tests show: the first Monday creates `backup/feeds` with only that file and pushes it; an unchanged export makes no commit and no push; HEAD, the index and staged changes on the checked-out branch are untouched; other weekdays do nothing.
- [ ] 6.3 Change the PATH in `templates/com.claude.ai-research-assistant.plist.j2` to `/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin`. Done when the template-rendering test asserts the new order.

## 7. Documentation and integration

- [ ] 7.1 Update `CLAUDE.md` (core flow: same-source check before analysis, 403 transient), `README.md` (weekly backup goes to `backup/feeds`) and add a `CHANGELOG.md` entry. Done when each statement matches the code.
- [ ] 7.2 Run `uv run pytest tests/ -v`, `uv run ruff check src/ tests/` and `openspec validate pipeline-review-fixes --strict`. Done when all three pass.
- [ ] 7.3 Run `run --dry-run` from the worktree against a copy of the iMac database and vault, then `run --limit 3 --verbose` on the copy. Done when the log shows the same-source check and no warnings, and the copied database's `retry_queue` holds content for newly queued entries.

## Workflow follow-up

- PR #3 (archive of `api-pipeline`) merges first; rebase this branch onto master afterwards.
- Open a PR only with the user's consent; merge after review.
- After merge, follow design.md "Migration Plan" on the iMac, then archive with `/opsx:archive`.
