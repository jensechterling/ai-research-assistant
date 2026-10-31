# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated RSS pipeline that fetches article feeds, extracts each article in Python, analyzes it with one JSON-mode call to Melious (OpenAI-compatible API, `deepseek-v4.1-flash`), and writes a personalized note into the Obsidian knowledge base. The scheduled pipeline does not use the Claude Code CLI. The `/article`, `/youtube`, `/podcast` and `/evaluate-knowledge` skills stay in the repo as Jinja2 templates for manual use.

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
FeedManager fetches RSS → pipeline selects entries → EntryProcessor: extract → analyze (Melious) → write note → Daily Dose + evaluation log
```

**Core flow (`src/pipeline.py`):**
1. `build_processor()` preflight: vault, interest profile, knowledge-base folder, API key. Failure raises `FatalRunError` and stops the run.
2. `_select_entries()`: new entries plus due retries, merged by guid. Skips non-`articles` feeds, entries waiting for their retry time, and new entries older than `processing.max_entry_age_days`, then applies `--limit`.
3. `EntryProcessor.process()` (`src/processor.py`): `extract_article()` → `analyze()` → `write_note()` → `append_daily_dose()` + `upsert_evaluation_log()`.
4. Success → `mark_processed(note_path)`. Permanent extraction failure → `mark_processed(None)`. Transient failure → `add_to_retry_queue()` with backoff (1h, 4h, 12h, 24h); when the queue gives up, the entry is marked processed with no note.
5. `FatalRunError` (missing key, HTTP 401/402/403/404 from Melious, missing profile) stops the run without queueing; the run is recorded as `failed`.
6. Stops starting entries at `processing.max_run_minutes` or `llm.max_cost_per_run_eur`.

**Modules:**
- `src/extraction.py`: httpx download + trafilatura, feed-text fallback, permanent vs transient classification
- `src/llm.py`: key resolution (env, `.env`, Keychain), `MeliousClient.complete()`, usage and EUR cost (prefers Melious's reported `billing_cost`)
- `src/analysis.py`: prompt from `templates/prompts/`, pydantic `Analysis`, one repair turn, truncation retry with doubled token budget
- `src/vault_writer.py`: note from `templates/notes/article.md.j2`, folder resolution, temp-file-and-rename writes

**Configuration (`src/config.py`):**
- `config/defaults.yaml` — version-controlled defaults (`llm`, `extraction`, `processing`, `folders`, ...)
- `config/user.yaml` — gitignored user overrides (created by `setup`)
- `load_config()` deep-merges user over defaults
- All paths and folders come from config, never hardcoded

**Skills (`skills/`, manual use only):**
- Templates live in `skills/_templates/` as Jinja2 `.md` files
- `setup` renders them into `skills/{name}/` and symlinks them to `~/.claude/skills/`

**Key design decisions:**
- Python does fetching, extraction, filing and bookkeeping; the model only returns one validated JSON object per article
- Source URL, title and original text in a note come from extraction, never from the model
- Melious only; `scripts/probe_melious.py` checks API behaviour (JSON mode, usage fields, error codes)
- `openai` SDK 3.x uses `httpx2`, not `httpx`: test doubles for the SDK need `httpx2.MockTransport`
- SQLite database in `data/pipeline.db` tracks processed entries, retry queue, run history (with `error` for failed runs)
