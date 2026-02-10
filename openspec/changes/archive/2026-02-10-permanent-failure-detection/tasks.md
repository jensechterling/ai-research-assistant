## 1. Permanent failure detection in SkillRunner

- [x] 1.1 Add `PERMANENT_FAILURE_PATTERNS` list and `permanent` field to `SkillResult` in `src/skill_runner.py`
- [x] 1.2 Add pattern matching in `run_skill()` when no note path is found — set `permanent=True` and use descriptive error message

## 2. Pipeline retry queue bypass

- [x] 2.1 Add `permanent_failures` counter to `PipelineResult` in `src/pipeline.py`
- [x] 2.2 In `_run_pipeline_inner()`, check `skill_result.permanent` — skip `add_to_retry_queue()` and log with `[PERMANENT]` prefix
- [x] 2.3 Update `send_notification()` to include permanent failure count in message

## 3. Tests

- [x] 3.1 Test that paywall pattern in stdout sets `SkillResult.permanent = True`
- [x] 3.2 Test that non-matching output sets `SkillResult.permanent = False`
- [x] 3.3 Test that permanent failures are not added to retry queue
- [x] 3.4 Test that transient failures are still added to retry queue
- [x] 3.5 Test that `PipelineResult.permanent_failures` counts correctly
- [x] 3.6 Test notification message includes permanent failure count
