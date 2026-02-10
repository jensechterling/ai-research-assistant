# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated RSS pipeline that fetches articles, YouTube videos, and podcasts, then invokes Claude Code skills (`/article`, `/youtube`, `/podcast`) to create personalized Obsidian notes. Skills are bundled as Jinja2 templates and rendered during setup with user-specific configuration.

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

# Setup / upgrade
uv run ai-research-assistant setup

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

**Configuration (`src/config.py`):**
- `config/defaults.yaml` — version-controlled defaults
- `config/user.yaml` — gitignored user overrides (created by `setup`)
- `load_config()` deep-merges user over defaults
- All paths and folders come from config, never hardcoded

**Skills (`skills/`):**
- Templates live in `skills/_templates/` as Jinja2 `.md` files
- `setup` renders them into `skills/{name}/` using config values
- Generated skills are symlinked to `~/.claude/skills/`
- Template variables: `{{ folders.youtube }}`, `{{ profile.interest_profile }}`, etc.

**Category → Skill mapping** (`src/skill_runner.py`):
- `articles` → `/article` → configured article folder
- `youtube` → `/youtube` → configured youtube folder
- `podcasts` → `/podcast` → configured clippings folder

**Key design decisions:**
- Skills bundled in this repo as Jinja2 templates — no separate skills repo needed
- `SkillRunner` reads all paths from `src/config.py`, never hardcoded
- `setup` wizard handles first-time config AND upgrades (re-renders templates)
- SQLite database in `data/pipeline.db` tracks processed entries, retry queue, run history
