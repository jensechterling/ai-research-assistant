# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated RSS pipeline that fetches articles, YouTube videos, and podcasts, then invokes Claude Code skills (`/article`, `/youtube`, `/podcast`) to create Obsidian notes.

## Commands

```bash
# Run tests
uv run pytest tests/ -v

# Run single test
uv run pytest tests/test_database.py::test_database_creates_tables -v

# Run pipeline
uv run ai-research-assistant run
uv run ai-research-assistant run --limit 5    # test with fewer items
uv run ai-research-assistant run --dry-run    # preview only

# Feed management
uv run ai-research-assistant feeds add URL -c articles
uv run ai-research-assistant feeds list
uv run ai-research-assistant status

# Lint
uv run ruff check src/ tests/
```

## Architecture

```
User subscribes to feeds → FeedManager fetches RSS → Pipeline processes entries → SkillRunner invokes Claude skills → Notes in Obsidian
```

**Core flow (`src/pipeline.py`):**
1. `FeedManager.fetch_new_entries()` - gets unprocessed RSS entries
2. `Database.get_retry_candidates()` - gets failed items due for retry
3. For each entry: `SkillRunner.run_skill()` invokes `/article`, `/youtube`, or `/podcast`
4. Success → `mark_processed()`, Failure → `add_to_retry_queue()` with exponential backoff (1h, 4h, 12h, 24h)
5. Post-process with `/evaluate-knowledge` skill

**Key design decisions:**
- Skills live in separate repo (`obsidian-workflow-skills`) - this repo is purely automation
- `SkillRunner.validate_skills()` checks `~/.claude/skills/` before running to fail fast
- Note path extracted from skill stdout (patterns: `**path.md**` or `` `path.md` ``)
- SQLite database in `data/pipeline.db` tracks processed entries, retry queue, run history

**Category → Skill mapping** (`src/skill_runner.py`):
- `articles` → `/article` (120s timeout) → `Clippings/`
- `youtube` → `/youtube` (300s timeout) → `Clippings/Youtube extractions/`
- `podcasts` → `/podcast` (600s timeout) → `Clippings/`

## Dependencies

Skills must be installed from [obsidian-workflow-skills](https://github.com/jensechterling/obsidian-workflow-skills) to `~/.claude/skills/`.

Vault path hardcoded: `~/Obsidian/Professional vault/`
