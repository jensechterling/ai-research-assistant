---
created: 2026-02-14
tags: [type/design, status/approved]
---

# Enhanced Logging for RSS Feed Pipeline

> Comprehensive logging improvements for debugging, performance monitoring, and audit trails.

## Context

**Goal:** Add detailed logging with timing metrics to the RSS feed pipeline for debugging, performance analysis, and historical audit.

**Current state:**
- Logs only go to stdout/stderr (no files)
- No timestamps for per-entry processing
- No progress output from `/evaluate-knowledge` skill
- No historical audit trail

**Approach selected:** Daily rotating log files + enhanced console output with timing instrumentation.

## Design Decisions

### 1. Log File Structure

**Daily rotating log files:**
```
~/code/ai-research-assistant/logs/
├── 2026-02-14.log          # Today's log
├── 2026-02-13.log          # Yesterday
└── 2026-02-12.log          # etc.
```

**Log format (file):**
```
2026-02-14 15:42:13.234 [INFO] pipeline: Starting run (30 new entries, limit: 5)
2026-02-14 15:42:13.456 [DEBUG] skill_runner: Invoking /pkm:article for https://example.com/...
2026-02-14 15:42:25.789 [INFO] skill_runner: ✓ Created note (12.3s): Article Title.md
2026-02-14 15:42:38.012 [INFO] pipeline: Running /evaluate-knowledge on 5 notes (1 batch)
2026-02-14 15:42:38.123 [DEBUG] evaluate-knowledge: Processing note 1/5: Article Title.md
2026-02-14 15:42:52.456 [INFO] evaluate-knowledge: Batch 1/1 done (14.3s, 4 promoted, 1 discarded)
2026-02-14 15:42:52.789 [INFO] pipeline: Run complete (39.5s total, 5 processed, 0 failed)
```

**Console output (INFO level, same as now but with timestamps):**
```
[15:42:13] Found 30 new entries, 0 retries (limited to 5)
[15:42:13] [1/5] Processing: Article Title
[15:42:25]   ✓ Created: Article Title.md (12.3s)
[15:42:38] Running /evaluate-knowledge on 5 new notes (1 batch)
[15:42:52]   Batch 1/1 done (14.3s, 4 promoted, 1 discarded)
[15:42:52] Processed: 5, Failed: 0 (39.5s total)
```

**Rationale:**
- Daily files are easy to browse ("what ran on Tuesday?")
- Timestamps enable performance analysis
- Separate file/console levels avoid cluttering daily use
- Standard log format works with grep, tail, etc.

### 2. Timing Instrumentation

**What gets timed:**

| Component | Metric | Logged As |
|-----------|--------|-----------|
| **Per-entry processing** | Start → note created | `skill_runner: ✓ Created note (12.3s)` |
| **Per-article evaluation** | Evaluate start → complete | `[1/5] Evaluating: Article.md (3.2s)` |
| **/evaluate-knowledge batch** | Batch start → batch complete | `Batch 1/1 done (14.3s, avg 2.8s/note)` |
| **Full pipeline run** | Run start → run complete | `Run complete (39.5s total)` |
| **Individual skill steps** (DEBUG) | Fetch, analyze, write operations | `[DEBUG] WebFetch complete (3.2s)` |

**Implementation approach:**
- Use Python's `time.perf_counter()` for high-resolution timing
- Timing context manager: `with timer("operation"):` logs duration automatically
- Skill output parsing: Extract timing from skill stdout if skills report it

**Example timing decorator:**
```python
@timed_operation("article_processing")
def run_skill(self, entry: Entry) -> SkillResult:
    # ... existing code ...
    # Duration logged automatically: "article_processing complete (12.3s)"
```

### 3. /evaluate-knowledge Skill Output Enhancement

**Current behavior:**
- Runs silently, no progress output
- Pipeline only sees "batch complete" at the end

**New behavior:**
- Output progress with per-note timing:
  ```
  [1/5] Evaluating: Article Title.md (3.2s)
  [2/5] Evaluating: Another Article.md (2.8s)
  [3/5] Evaluating: Third Article.md (4.1s)
  [4/5] Evaluating: Fourth Article.md (2.9s)
  [5/5] Evaluating: Final Article.md (3.5s)
  ✓ Batch complete: 4 promoted to Knowledge/, 1 discarded (16.5s total, avg 3.3s/note)
  ```

**Implementation:**
- Add progress counter to skill's evaluation loop
- Time each note individually with `perf_counter()`
- Print to stdout after each note completes (captured by pipeline)
- Pipeline logs this output at INFO level
- Final summary includes total time + average per note

**Skill changes needed:**
- Modify `SKILL.md` workflow to add timing wrapper per note
- Count notes upfront, output `[N/Total]` prefix per note
- Track individual timings, compute average
- Final summary line with total, average, and result counts

### 4. Log File Management

**Rotation strategy:**
- **Daily files:** One log file per day (YYYY-MM-DD.log)
- **Automatic rotation:** Python logging `TimedRotatingFileHandler` creates new file at midnight
- **Retention:** Keep last 30 days of logs (configurable)
- **Cleanup:** Old logs auto-deleted on startup if > 30 days

**Log levels by destination:**

**File (logs/YYYY-MM-DD.log):**
- DEBUG: All operations, skill internals, timing details
- INFO: Pipeline progress, results
- WARNING: Retries, timeouts
- ERROR: Failures

**Console (stdout):**
- INFO: Pipeline progress, results (like current output)
- WARNING: Retries, timeouts
- ERROR: Failures
- (No DEBUG to console - keeps it clean)

**Configuration:**
- Log retention days: `config/user.yaml` → `logging.retention_days: 30`
- Log level: `--verbose` flag sets console to DEBUG (shows everything)
- Log directory: `~/code/ai-research-assistant/logs/` (created if missing)

### 5. Implementation Components

**Files to modify:**

1. **`src/logging_config.py`** (new file)
   - Configure dual handlers (file + console)
   - TimedRotatingFileHandler for daily rotation
   - Custom formatter with timestamps
   - Cleanup old logs function

2. **`src/skill_runner.py`**
   - Add timing decorator for `run_skill()`
   - Log per-entry start/complete with duration
   - Add DEBUG logging for skill subprocess details

3. **`src/pipeline.py`**
   - Add timing for full pipeline run
   - Capture and log `/evaluate-knowledge` stdout
   - Log batch timing summaries

4. **`Claude/skills-pkm/skills/evaluate-knowledge/SKILL.md`**
   - Add progress output: `[N/Total] Evaluating: note.md`
   - Add per-note timing after completion
   - Add batch summary with total/avg timing

5. **`config/defaults.yaml`**
   - Add `logging.retention_days: 30`
   - Add `logging.level: INFO` (can override with `--verbose`)

**Testing verification:**
- Run `uv run ai-research-assistant run -n 5 --verbose`
- Check `logs/YYYY-MM-DD.log` exists with DEBUG entries
- Verify console shows timestamps and durations
- Confirm `/evaluate-knowledge` shows per-article progress

## Benefits

**Debugging:**
- Full DEBUG logs in files for troubleshooting
- Stack traces and error context preserved
- Can review past failures from log files

**Performance monitoring:**
- Identify slow articles/feeds
- Track evaluation time per note
- Spot performance regressions over time

**Audit trail:**
- Daily logs show what was processed when
- Can review "what ran last Tuesday at 4am?"
- Historical record for compliance/review

**Launchd-friendly:**
- When 4am automation is added, all output captured in daily logs
- No need to tail console, just check log files

## Future Enhancements

- Log rotation compression (gzip old logs)
- Summary stats command: `ai-research-assistant stats --last-week`
- Performance alerting (warn if avg time > threshold)
- Export to structured format (JSON lines for log aggregation)

## Related

- Implementation plan: `docs/plans/2026-02-14-logging-improvements-plan.md` (to be created)
- Skill to update: `Claude/skills-pkm/skills/evaluate-knowledge/SKILL.md`
- Python logging docs: https://docs.python.org/3/library/logging.html

---

**Status:** Approved 2026-02-14
**Next:** Create implementation plan via `/writing-plans`
