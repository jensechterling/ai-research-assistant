## Context

The pipeline processes RSS entries by invoking Claude Code skills (`/article`, `/youtube`, `/podcast`). When a skill fails to create a note, the entry is added to a retry queue with exponential backoff (1h, 4h, 12h, 24h). Some failures are permanent — paywalled content, deleted resources — and retrying them wastes time and API calls.

Currently, a skill that encounters a paywall returns exit code 0 with output explaining the content is behind a paywall but no note path. The pipeline treats this identically to transient failures (network issues, timeouts).

## Goals / Non-Goals

**Goals:**
- Detect permanent failures from skill output using pattern matching
- Skip the retry queue for permanent failures to avoid wasted retries
- Provide clear logging and notification counts for permanent failures

**Non-Goals:**
- HTTP status code inspection (skills abstract away the HTTP layer)
- Feed-level blocking (e.g., auto-unsubscribe feeds with repeated permanent failures) — may be a future enhancement
- Configurable pattern lists (hardcoded patterns are sufficient for now)

## Decisions

### D1: Pattern matching on skill stdout
Detect permanent failures by matching known phrases in skill output (case-insensitive). This is pragmatic because:
- Skills return natural language output, not structured error codes
- Paywall/access patterns are consistent and recognizable
- False positives are low-risk (entry just won't be retried, user can manually re-run)

Alternative considered: structured error codes from skills. Rejected because skills are Claude Code skill files (markdown prompts), not code we control — they produce free-form text.

### D2: `permanent` flag on SkillResult
Add a boolean `permanent` field to `SkillResult` rather than a new class or enum. This keeps the change minimal — the pipeline checks `skill_result.permanent` and skips the retry queue.

Alternative considered: `FailureType` enum (transient/permanent). Overkill for a boolean distinction.

### D3: Pipeline logs permanent failures as warnings, not errors
Permanent failures are expected (paywalled content) rather than exceptional. Using `logger.warning` with a `[PERMANENT]` prefix makes them easy to filter without cluttering error logs.

### D4: Notification includes permanent count
The macOS notification already shows processed/failed counts. Add permanent failure count so the user knows at a glance without checking logs.

## Risks / Trade-offs

- **False positives**: A pattern like "paywall" could match in legitimate article content discussing paywalls → Low risk because matching only happens when no note path is found (skill already failed)
- **False negatives**: New paywall messages not covered by patterns → Entries retry normally, no worse than current behavior. Patterns can be expanded over time.
- **Hardcoded patterns**: Not user-configurable → Acceptable for now; patterns are in a module-level constant, easy to find and extend
