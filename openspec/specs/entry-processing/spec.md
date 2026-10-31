# entry-processing Specification

## Purpose
Defines how a scheduled run picks entries, processes each one (extract, analyze, write), records outcomes and reports the result, without depending on the Claude Code CLI.

## Requirements

### Requirement: No Claude Code CLI in the run path
The `run` command SHALL NOT start the `claude` executable or depend on Claude Code skills being installed.

#### Scenario: Claude CLI absent
- **WHEN** `claude` is not on PATH and `~/.claude/skills/` is empty
- **THEN** `ai-research-assistant run` processes entries normally

### Requirement: Articles only
The run SHALL process entries from `articles` feeds only. Entries from feeds in any other category SHALL be skipped without being processed, queued or marked processed. The run log SHALL say once per feed how many entries were skipped and that the manual skill handles them.

#### Scenario: YouTube feed present
- **WHEN** a `youtube` feed has 3 new entries
- **THEN** none is processed, the retry queue is unchanged, and the log names the feed and the 3 skipped entries

### Requirement: Feed download timeout
Each feed SHALL be downloaded with a timeout of `feeds.request_timeout` seconds. A feed that fails or times out SHALL be logged and skipped for this run, and the other feeds processed.

#### Scenario: One feed hangs
- **WHEN** one of 14 feeds does not respond
- **THEN** that feed is skipped after the timeout and entries from the other 13 are processed

#### Scenario: Feed trickles or is huge
- **WHEN** a feed download takes longer than 60 seconds in total or exceeds 20 MB
- **THEN** that feed is skipped for this run and the other feeds are processed

### Requirement: One attempt per entry per run
An entry that appears both as a new feed entry and in the retry queue SHALL be processed once in that run. The feed copy is used because it carries content and a publication date, and the entry counts as a retry.

#### Scenario: Failed entry still in its feed
- **WHEN** an entry failed yesterday, is due for retry, and is still listed in its feed
- **THEN** it is processed once, and its retry attempt count goes up by at most one

#### Scenario: Entry waiting for its retry time
- **WHEN** an entry is in the retry queue with a retry time later than now, and is still listed in its feed
- **THEN** it is not processed in this run

### Requirement: Stale entries skipped
New entries published more than `processing.max_entry_age_days` days before the run (default 14) SHALL be skipped without being processed, queued or counted as failures. Entries with no publication date SHALL be processed. Retry-queue entries SHALL NOT be filtered by age. The stale filter SHALL run before `--limit` is applied and SHALL also apply in `--dry-run`.

#### Scenario: First run after a long outage
- **WHEN** feeds list 40 unprocessed entries, 35 of them published more than 14 days ago
- **THEN** only the 5 recent entries are processed, and the log states that 35 were skipped as stale

#### Scenario: Limit applies after the filter
- **WHEN** the same feeds are run with `--limit 3`
- **THEN** 3 of the 5 recent entries are processed

### Requirement: Per-entry processing order
For each entry the system SHALL run extraction, then analysis, then vault output, and SHALL stop at the first step that fails.

#### Scenario: Extraction fails
- **WHEN** extraction fails for an entry
- **THEN** no API request is made for that entry

### Requirement: Success definition
An entry SHALL count as processed only when its note file exists at the path the vault writer returned. Its guid and note path SHALL then be stored as processed, and it SHALL be removed from the retry queue if it was there.

#### Scenario: Successful retry
- **WHEN** an entry from the retry queue produces a note
- **THEN** it is marked processed, removed from the retry queue, and counted as retried

### Requirement: Transient failures retry
A transient failure from any step SHALL add the entry to the retry queue with the step name and error message, using the existing backoff schedule.

#### Scenario: Analysis timeout
- **WHEN** analysis fails with a timeout
- **THEN** the retry queue entry's error starts with `analysis:` and the backoff schedule applies

#### Scenario: Retries used up
- **WHEN** an entry fails transiently on its last allowed attempt and the retry queue drops it
- **THEN** it is recorded as processed with no note path, so later runs do not start it again, and the log says the entry was given up

### Requirement: Fatal errors stop the run
A problem that would fail every entry SHALL stop the run at once. Examples are a missing key, an account-level API error, a missing interest profile, or a missing vault or knowledge-base folder. The current and remaining entries SHALL NOT be added to the retry queue, and the run SHALL be recorded with status `failed`.

#### Scenario: Rejected key mid-run
- **WHEN** the API rejects the key while processing the third of ten entries
- **THEN** two entries are processed, eight are left untouched for the next run, and the run is recorded as `failed` with the cause

#### Scenario: Unexpected exception outside entry processing
- **WHEN** an unhandled exception escapes the run loop
- **THEN** the run is recorded as `failed` before the process exits

#### Scenario: Unexpected exception notifies
- **WHEN** an unhandled exception escapes the run loop
- **THEN** a "Run stopped" notification with the exception is shown before the process exits

### Requirement: Repeated analysis failures stop the run
When the first 3 entries of a run that reach analysis all fail at analysis, before any analysis has worked in that run, the system SHALL queue those 3 for retry as usual and then stop the run as a fatal error naming the last error. Failures at extraction SHALL NOT count.

#### Scenario: Config error rejected for every request
- **WHEN** Melious answers HTTP 400 for every analysis request and 20 entries are pending
- **THEN** 3 entries are queued for retry, 17 are left untouched, the run is recorded as `failed`, and the notification names the error

#### Scenario: Failures after a success
- **WHEN** the first analysis of the run succeeds and later ones fail
- **THEN** the run continues and the failed entries are queued as transient failures

### Requirement: Run time and cost limits
The system SHALL stop starting new entries once the run has lasted `processing.max_run_minutes` minutes (default 60), or once its summed analysis cost has reached `llm.max_cost_per_run_eur` (default 2.00). Entries not started SHALL be left for the next run, not queued as failures.

#### Scenario: Cost ceiling reached
- **WHEN** the ceiling is EUR 1.00 and the run's cost reaches EUR 1.01 after entry 40 of 60
- **THEN** entries 41 to 60 are not started and the log states which limit was reached

### Requirement: Run notification
At the end of a run the system SHALL show a macOS notification. A completed run gives the processed count, then the failed, skipped (not extractable) and retried counts where non-zero, then the run's cost in EUR. A stopped run is titled "Run stopped" and gives the cause, cut to 150 characters. The text SHALL reach the notification unchanged whatever characters it contains.

#### Scenario: Normal run
- **WHEN** a run processes 12 entries, with 1 transient failure, 2 permanent failures and 3 retries, at a cost of EUR 0.09
- **THEN** the notification reads `Processed 12, Failed 1, 2 skipped (not extractable), 3 retried, EUR 0.09`

#### Scenario: Quiet run
- **WHEN** a run finds nothing to process
- **THEN** the notification reads `Processed 0, EUR 0.00`

#### Scenario: Stopped run with quotes in the cause
- **WHEN** the run stops on an API error whose message contains `"` characters
- **THEN** the notification shows the cause with the quotes intact

### Requirement: Existing run controls unchanged
`--limit`, `--verbose`, `--force`, the pipeline lock and skipping already-processed entries SHALL behave as before. `--dry-run` SHALL list the entries that would be processed after the category and stale filters, and SHALL NOT download pages, call the API or write to the vault.

#### Scenario: Dry run
- **WHEN** `ai-research-assistant run --dry-run` is invoked
- **THEN** the would-be entries are listed with counts of stale and unsupported-category skips, and no page download, API request or vault write happens
