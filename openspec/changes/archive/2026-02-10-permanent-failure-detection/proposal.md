## Why

Some content sources are permanently inaccessible — paywalled articles, deleted videos, geo-restricted podcasts. The pipeline currently retries these entries 4 times over 24 hours, wasting skill invocations on content that will never succeed. After all retries are exhausted, the entry sits silently in the retry queue with max attempts. There's no distinction between transient failures (network timeout, rate limit) and permanent ones (paywall, content removed).

## What Changes

- Detect permanent failure patterns in skill output (paywall indicators, content-not-found signals)
- Add a `permanent` flag to `SkillResult` to distinguish permanent from transient failures
- Skip the retry queue for permanently failed entries — log them and move on
- Improve notification messages to include permanent failure counts
- Log permanent failures distinctly so the user can review and optionally unsubscribe problematic feeds

## Capabilities

### New Capabilities
- `permanent-failure-detection`: Pattern-based detection of permanently unextractable content, with retry queue bypass and distinct logging

### Modified Capabilities

## Impact

- `src/skill_runner.py` — pattern matching on skill stdout, new `permanent` field on `SkillResult`
- `src/pipeline.py` — conditional retry queue bypass, updated notification message, distinct logging
- `tests/` — new tests for pattern detection and pipeline behavior with permanent failures
