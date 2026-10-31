# Proposal

## Why

The scheduled pipeline has stopped producing notes. Notes in the synced vault fell from 38–51 a month (January–March 2026) to 16 in April and almost none since. The last "Daily Dose of Know-How" entry is from 9 April. Each entry is processed by a full headless Claude Code session (`claude --print --dangerously-skip-permissions /article URL`), followed by a second session for `/evaluate-knowledge`. So every unattended run depends on CLI auth, CLI auto-updates, the user's global hooks and plugins, MCP servers, and the model choosing the right tool sequence. Success is decided by regex-scraping the model's chat reply for a file path. The run loop also has its own bugs: a failed entry is attempted twice per run, and failed runs are recorded as completed.

Moving to a direct API call removes those dependencies. Python does the fetching, extraction, file writing and filing. The model gets one call per entry and returns structured JSON. The API is Melious (`https://api.melious.ai/v1`, OpenAI-compatible) with `deepseek-v4.1-flash`, a provider and model already in use elsewhere.

## What Changes

- **BREAKING** The `run` command no longer invokes the `claude` CLI. `SkillRunner` and the headless `/evaluate-knowledge` post-step are removed from the pipeline.
- **BREAKING** The scheduled pipeline processes `articles` feeds only. Entries from `youtube` and `podcasts` feeds are skipped with a warning; those categories stay available through the manual `/youtube` and `/podcast` skills. The user has no such subscriptions today.
- New article extraction in Python: the page is downloaded with a timeout and the main text extracted, with the feed's own full text as fallback.
- One LLM call per entry to Melious, returning JSON with the summary, findings, suggestions, tags, knowledge-base folder, takeaway and action. The JSON is validated against a schema, with one repair turn.
- A new vault writer renders a simplified note and writes it directly into the chosen knowledge-base subfolder. It appends the Daily Dose entry to today's daily note and adds a row to `evaluation-log.md`.
- Python, not the model, inserts the source URL, metadata and original text, so the model can't alter them.
- Failure classification becomes deterministic, based on HTTP status and extracted word count. Permanent failures are recorded so they are not attempted again.
- Run-loop fixes:
  - An entry that is both new and in the retry queue is processed once.
  - Failed and stopped runs are recorded as failed.
  - Account-level API errors stop the run.
  - Feed downloads and the whole run have time limits.
  - Each run has a cost ceiling.
- Each run logs token usage and EUR cost per entry and in total.
- New `llm` configuration section. The API key is read from the environment, the project's `.env` file, or the macOS Keychain item `melious-api-key`.
- The setup wizard checks for the Melious key and tests it. It no longer requires the `claude` CLI or `npx`, and no longer renders `config/mcp-minimal.json`.
- The Monday OPML backup in `scripts/run.sh` only commits and pushes when the checkout is on `master`.
- Unchanged: the four skill templates, their rendering and symlinks (kept for manual use), feed management, the database schema, retry backoff, the pipeline lock and scheduling.

## Capabilities

### New Capabilities
- `content-extraction`: Getting title, metadata and main text for an article entry without an LLM, and classifying extraction failures as permanent or transient.
- `note-analysis`: The single structured LLM call to Melious. Covers key resolution, prompt inputs, the response schema, validation and repair, timeouts, retries, fatal API errors, and usage and cost reporting.
- `vault-output`: Rendering and writing the note, filing it into the knowledge base, the Daily Dose entry, and the evaluation-log row.
- `entry-processing`: The per-run and per-entry flow. Covers which entries are processed, step order, the success definition, retry and fatal handling, time and cost limits, run recording and the run notification.

### Modified Capabilities
- `permanent-failure-detection`: Detection moves from matching phrases in skill stdout to classification by the extraction step, and permanent failures are now recorded so they are not attempted again.
- `setup-wizard`: Dependency checks change: a Melious key is required and tested, and the `claude` CLI is needed only for manual skills. `npx` is no longer checked, and `config/mcp-minimal.json` is no longer rendered.

## Impact

- **Code:**
  - `src/skill_runner.py` is removed.
  - `src/pipeline.py` is reworked.
  - New modules cover extraction, the LLM client, analysis, vault writing and per-entry processing.
  - `src/feed_manager.py` stores full feed text and fetches with a timeout.
  - `src/database.py` gains a failed-run status.
  - `src/setup.py` changes its dependency checks.
  - `scripts/run.sh` guards the OPML backup.
- **Dependencies:** adds `openai` (as the client for Melious's OpenAI-compatible API), `trafilatura` and `pydantic`. `httpx` and `python-dotenv` are already dependencies.
- **Config:** new `llm` and `extraction` sections plus new `processing` and `folders` keys in `config/defaults.yaml`. `.env.example` gains `MELIOUS_API_KEY`.
- **Vault:**
  - Notes go straight into knowledge-base subfolders instead of through `Clippings/`.
  - Note layout is simpler than the skills' layout (see design.md D5).
  - The "Aggregated Patterns" section of `evaluation-log.md` is no longer regenerated by the scheduled run.
- **Data leaving the machine:** article text and the interest profile go to Melious, which routes each call to one of its EU inference subprocessors. The caller can't pin which one.
- **Cost:** moves from the Claude subscription to Melious billing (EUR 0.20 per 1M input tokens, EUR 1.00 per 1M output tokens).
- **Tests:**
  - `tests/test_skill_runner.py` is removed.
  - `tests/test_permanent_failure.py` and the pipeline tests are rewritten.
  - New tests cover extraction, analysis and vault output, with HTTP and LLM calls mocked.
