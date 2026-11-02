# Tasks

## 1. Probes (before writing pipeline code)

- [x] 1.1 Write `scripts/probe_melious.py`, which sends one short article and a fake profile to `deepseek-v4.1-flash` and records the API's actual behaviour. Done when design.md D3 and the reasoning Open Question are updated from the findings and the `llm` defaults adjusted. The probe records:
  - whether `response_format` `json_object` is honoured
  - whether `json_schema` strict mode is honoured
  - the `usage` fields, including reasoning and cached tokens
  - the provider-ID field, if any
  - whether a "no reasoning" parameter is accepted
  - `finish_reason` when `max_tokens` is set low
  - the HTTP status and body for an invalid key and for an unknown model
- [x] 1.2 Check the current `openai` Python SDK retry and exception behaviour through Context7: `max_retries`, the retried status codes, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, how a 402 surfaces, and `APITimeoutError`. Done when design.md D2 is confirmed or corrected.
- [x] 1.3 Fetch three feeds from `exports/feeds.opml`, including `simonwillison.net/atom/everything/`, with feedparser. Find whether the full text is under `content[0].value` and how many words a typical summary has. Done when D7 states the exact access path.

## 2. Dependencies and configuration

- [x] 2.1 Add `openai`, `trafilatura` and `pydantic` to `pyproject.toml`. Done when `uv sync` succeeds and `uv run python -c "import openai, trafilatura, pydantic"` exits 0.
- [x] 2.2 Add the keys from design.md D11 to `config/defaults.yaml`, and add `MELIOUS_API_KEY=` to `.env.example`, replacing its comment about Claude Code auth. Done when a test in `tests/test_config.py` checks that the defaults load and that a `user.yaml` overriding `llm.model` merges correctly.

## 3. Feeds and extraction

- [x] 3.1 Change `FeedManager` to download feeds with `httpx` and `feeds.request_timeout` before parsing, and to store `content[0].value` (falling back to `summary`) as entry content. Done when tests with fixture feeds cover both content keys, a timed-out feed being skipped while the others are read, and the existing feed tests still pass.
- [x] 3.2 Implement `extract_article()` in `src/extraction.py`. Done when tests with mocked HTTP cover every content-extraction scenario:
  - readable page
  - metadata missing
  - 403 rescued by feed text
  - retry entry with no content
  - truncation at `max_words`
  - 403 without feed text (permanent)
  - short post (permanent)
  - 429/5xx/timeout (transient)

## 4. Melious client and analysis

- [x] 4.1 Implement `src/llm.py`: key resolution from the environment, `.env` and the Keychain (10 s timeout), the client, JSON completion, usage and EUR cost summed across attempts, the provider ID, and `FatalRunError` on 401/402/403/404. Done when tests cover:
  - each key source and the missing-key error text
  - a hanging Keychain lookup
  - 503 then success, and persistent timeout
  - each fatal status
  - the cost arithmetic (10k input and 2k output tokens give EUR 0.0040)
  - the key never appearing in a raised error, log record or notification text
- [x] 4.2 Write `templates/prompts/analysis-system.md.j2` and `analysis-user.md.j2` with the rules carried over from `skills/_templates/article/article-workflow.md` and the filing rules from `evaluate-knowledge/SKILL.md`. Done when a test renders it and checks that the profile, folder list and language instruction are in the system message and the entry text is in the user message.
- [x] 4.3 Implement `src/analysis.py`: the pydantic `Analysis` model, message building, one repair turn, and the truncation retry with the token limit doubled. Done when tests with a fake client cover:
  - a valid reply
  - an invalid reply that is then repaired
  - invalid twice (transient)
  - truncated then complete
  - truncated twice (transient, "output truncated")
  - more than five tags rejected
  - a missing interest profile raising `FatalRunError`

## 5. Vault output

- [x] 5.1 Write `templates/notes/article.md.j2` with the layout in design.md D5. Done when a test renders it from fixture data and checks the frontmatter fields, the section order, the exact source URL, the `source/<slug>` tag, the truncation note and the collapsed callout.
- [x] 5.2 Implement `write_note()`: folder normalisation and creation, the unsafe-name fallback, filename sanitising, same-source replacement, the numbered suffix, and temp-file-and-rename writes. Done when tests in a temporary vault cover every filing and naming scenario in the vault-output spec, and `../../Private` writes nothing outside the knowledge base.
- [x] 5.3 Implement `append_daily_dose()`: create from the template with `tp.date.now` formats resolved, case- and level-insensitive heading match, append the heading when missing, aliased link, no duplicate link. Done when tests use the real template text, with its `# Daily dose of know-how` H1, and an existing daily note with an `##` heading.
- [x] 5.4 Implement `upsert_evaluation_log()`: append or replace the row, escape `|`, set "Last updated", recount "Total evaluated" from the table, create the log when missing, and leave "Aggregated Patterns" byte-identical. Done when tests run against a fixture log with patterns and table sections.

## 6. Processing and pipeline

- [x] 6.1 Implement `process_entry()` in `src/processor.py`, returning `ProcessingResult`, with the check that the note file exists. Done when tests with fake steps cover:
  - success
  - extraction permanent
  - extraction transient
  - analysis transient (`analysis:` prefix)
  - vault failure
  - a bookkeeping failure that still counts as success
- [x] 6.2 Add `Database.record_run_failed(run_id, processed, failed, error)` and a nullable `pipeline_runs.error` column, added to existing databases on startup. Done when tests check the stored status and error and the column migration.
- [x] 6.3 Rewrite the `src/pipeline.py` run loop as in design.md D9, and remove the `/evaluate-knowledge` subprocess. Done when tests cover:
  - preflight failures
  - the category skip
  - dedupe of an entry that is both new and a retry, and skipping one still waiting for its retry time
  - an entry given up by the retry queue marked processed with no note path
  - stale skip with `--limit` applied afterwards
  - a permanent failure marked processed with no note path, including one from the retry queue
  - a rejected key on entry 3 of 10 (2 processed, nothing queued, run `failed`)
  - an unhandled exception recorded as `failed`
  - the cost ceiling and the time limit
  - dry-run making no HTTP, API or vault calls
  - `subprocess.run` never called with `claude` (patched and asserted)
- [x] 6.4 Rewrite `send_notification()` to pass the text as an `osascript` argument, using the formats in the entry-processing spec. Done when tests assert the exact text for the normal, quiet, permanent-failure and stopped-with-quotes scenarios, and the argument list passed to `osascript`.
- [x] 6.5 Delete `src/skill_runner.py` and `tests/test_skill_runner.py`, and rewrite `tests/test_permanent_failure.py` against `ProcessingResult`. Done when `RTK_DISABLED=1 uv run pytest tests/ -q` and `uv run ruff check src/ tests/` both pass with exit code 0.

## 7. Setup wizard and run script

- [x] 7.1 Stop rendering `config/mcp-minimal.json`, and delete `templates/mcp-minimal.json.j2` and its `.gitignore` line. Done when the template-rendering test asserts the file is not created and the plist still is.
- [x] 7.2 Update `_check_dependencies()`: new wording for the `claude` and `yt-dlp` warnings, no `npx` check, a Melious key check, and a one-request key-and-model test that never prints the key. Done when `tests/test_setup.py` covers all five dependency-checking scenarios with the HTTP call mocked.
- [x] 7.3 Move the Monday OPML backup from `scripts/run.sh` into `scripts/backup_feeds.sh`, which commits and pushes only on `master`. Done when `bash -n` passes on both scripts and `tests/test_backup_script.py` shows a Monday on a feature branch prints the skip message and makes no commit.

## 8. Documentation

- [x] 8.1 Update `CLAUDE.md` and `README.md` (architecture, core flow, articles only, Melious key setup, cost, skills for manual use only) and add a `CHANGELOG.md` entry. Done when the README's setup steps, followed in a fresh clone, reach `run --dry-run` without a missing step.

## 9. Integration on real data

- [x] 9.1 On the MacBook, use a scratch vault copy and a scratch database with feeds imported from `exports/feeds.opml`, pointed to by a temporary `user.yaml`. Run `run --dry-run`, then `run --limit 6 --verbose`. Done when:
  - six entries end as notes or are classified with a stated reason
  - the daily note and log rows are correct
  - the cost is shown
  - the notes have been compared with three March notes from the same feeds, with the verdict recorded for the PR description
- [ ] 9.2 On the iMac, follow design.md "Migration Plan" steps 1 to 5. Done when five entries are processed into the real vault with no warnings in the log, and the next 06:00 run is confirmed complete in `~/.claude/logs/ai-research-assistant.log`.

## Workflow follow-up

- Open a PR from `feat/api-pipeline` after 9.1 passes. Merge only after 9.2 is confirmed on the iMac.
- After merge, archive with `/opsx:archive`. That updates the main specs for `permanent-failure-detection` and `setup-wizard` and creates the four new ones.
