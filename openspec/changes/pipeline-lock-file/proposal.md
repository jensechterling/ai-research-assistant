## Why

The pipeline has no protection against concurrent runs. When a scheduled launchd/cron job is still processing and a user manually triggers `ai-research-assistant run`, both instances write to the same SQLite database simultaneously. This causes duplicate processing, wasted Claude API calls, and potential database corruption.

## What Changes

- Add a file-based lock that prevents concurrent pipeline runs
- The pipeline acquires a lock at startup and releases it on exit (including crashes)
- If a lock is already held, the second instance exits immediately with a clear message
- A `--force` flag allows overriding a stale lock (e.g., after a crash that didn't clean up)

## Capabilities

### New Capabilities
- `pipeline-lock`: File-based mutual exclusion preventing concurrent pipeline runs

### Modified Capabilities

(none — this is a new internal capability, no existing spec-level behavior changes)

## Impact

- `src/pipeline.py` — acquire/release lock around the main processing loop
- `data/pipeline.lock` — new lock file location (alongside existing `pipeline.db`)
- CLI `run` command — new `--force` flag to override stale locks
