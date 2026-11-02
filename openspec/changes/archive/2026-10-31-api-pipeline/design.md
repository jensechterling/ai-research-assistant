# Design

## Context

See proposal.md (Why) for the failure history. The facts below shape the approach.

- The pipeline runs on an iMac under launchd at 06:00 via `scripts/run.sh`. Its plist sets a minimal `PATH`. `run.sh` runs `source .env` without `export`, so variables in `.env` never reach the Python process. `python-dotenv` is a dependency but nothing calls it.
- Today `src/skill_runner.py` starts `claude --print --dangerously-skip-permissions` once per entry, and `src/pipeline.py` starts it again for `/evaluate-knowledge` in batches of six. Each headless session loads the user's global Claude Code hooks and plugins.
- Existing run-loop bugs:
  - `fetch_new_entries()` returns every unprocessed feed item, including items already in the retry queue, so the loop processes such an entry twice. `is_retry = entry in retry_entries` compares whole dataclasses, and the feed copy never matches the retry copy.
  - `record_run_complete()` always writes status `completed`.
  - `feedparser.parse(url)` has no timeout.
  - The notification text is interpolated into an AppleScript string, so a `"` in it breaks the notification.
- `FeedManager` stores only `item.summary` as entry content. Retry-queue rows store no content.
- The user's feeds are all article feeds. The last OPML backup (2 Feb 2026) lists 14, and the user confirmed there are no YouTube or podcast subscriptions.
- The live vault uses `2 Know-how` as the knowledge base (20 top-level subfolders) and `1 Daily notes` for daily notes. `Templates/Daily Note.md` uses Templater syntax (`<% tp.date.now("YYYY-MM-DD") %>`) and an H1 heading `# Daily dose of know-how`. Pipeline-written daily notes use `## Daily Dose of Know-How`. `evaluation-log.md` is 150 KB with 429 table rows.
- Melious (`https://api.melious.ai/v1`) is OpenAI-compatible. `deepseek-v4.1-flash` there has a 1M-token context, 32k output limit and reasoning enabled. It costs EUR 0.20 / 1.00 / 0.01 per 1M input / output / cache-read tokens. Melious routes each call to one of 12 EU subprocessors and can't be pinned to one.

## Goals / Non-Goals

**Goals:**
- A scheduled run whose only external dependencies are HTTPS to feeds and article sites, and HTTPS to Melious.
- Each failure says which step failed (extraction, analysis or vault) and whether it will be retried. Nothing can block a run indefinitely.
- New notes carry the same core content as the skills' notes (summary, findings, suggestions) and file into the same knowledge base, in a simpler layout.

**Non-Goals:**
- YouTube and podcast processing in the scheduled run. The manual skills stay.
- Matching the skills' note layout exactly (see D5).
- Regenerating the "Aggregated Patterns" section of the evaluation log.
- Providers other than Melious, and tool-calling or agent loops.
- Changing the manual skills, the retry backoff, or moving off the iMac. The only schema change is one nullable `pipeline_runs.error` column, added on startup when missing; older code ignores it.

## Decisions

### D1. Python does the steps; the model fills in one JSON object

```
feeds ─▶ filter (category, stale, dedupe) ─▶ per entry:
   extract (Python) ─▶ analyze (Melious, JSON) ─▶ write (Python) ─▶ mark processed
     │ permanent → mark processed, no note    │ transient → retry queue
     │ transient → retry queue                │ FATAL → stop run, record failed
```

The model never fetches, never writes files, and never decides where its output goes.

*Alternative:* run a coding-agent CLI headless with Melious. That keeps the tool-choice variability, the CLI-version drift and success-by-parsing. Rejected.

### D2. OpenAI Python SDK pointed at Melious

Use the `openai` package with `base_url=llm.base_url` and `max_retries=llm.max_retries`.

Confirmed against the current SDK README and `_exceptions.py` via Context7 (task 1.2, 2026-10-30):
- The SDK retries 2 times by default, with short exponential backoff.
- It retries connection errors, 408, 409, 429 and every status of 500 or above.
- `APITimeoutError` is a subclass of `APIConnectionError`, so timeouts are retried too.
- 401, 403 and 404 raise `AuthenticationError`, `PermissionDeniedError` and `NotFoundError`.
- 402 has no class of its own and raises the base `APIStatusError` with `status_code == 402`.
- The fatal check therefore tests `isinstance(e, APIStatusError) and e.status_code in {401, 402, 403, 404}`, not class names.
- Melious's extra response fields (`billing_cost`, `environment_impact`) are read from `completion.model_extra`.
- `reasoning_effort` is sent through `extra_body`, so the SDK's type hints for that parameter don't get in the way.

*Alternative:* raw `httpx` means more code to get the same retry behaviour. Rejected.

### D3. JSON output, validation, repair and truncation

Request `response_format={"type": "json_object"}` with the schema in the system prompt, and validate the reply with a pydantic model. `finish_reason == "length"` is checked first. A truncated reply is never sent to repair, because the repair would hit the same limit. It is retried once with the token limit doubled (max 32,000). A complete but invalid reply gets one repair turn.

**Probe results (task 1.1, 2026-10-30, `scripts/probe_melious.py`):**
- `json_object`, `json_schema` (strict) and no `response_format` all returned valid JSON on a small sample. `json_object` is kept: it is the more widely supported mode, so a Melious failover to another subprocessor is less likely to reject it with a 400. Pydantic remains the real check.
- Usage reports `prompt_tokens`, `completion_tokens` (reasoning included), `cached_tokens` and `reasoning_tokens`, flat and in the `*_details` objects.
- Each response carries `billing_cost.credits`. That figure equals our EUR formula exactly (244 in / 421 out → 0.0004698), so it is used as the entry cost when present, and the formula is the fallback.
- The serving provider is in `environment_impact.provider_id` (here `melious`, location `FI`).
- Reasoning can be turned off with `reasoning_effort: "none"` (or DeepSeek's `thinking: {type: disabled}`). `reasoning: {enabled: false}` is silently ignored. With reasoning on, output tokens were 2–3× higher and latency 2–3 s instead of 1 s on the sample.
- With `max_tokens: 60` the reply came back with `finish_reason: length` and empty content: the whole budget went to reasoning. That confirms the truncation rule.
- An unknown model gives 404 `model_not_found`, and an invalid key gives 401 `invalid_api_key`. Both are fatal under the spec.

### D4. One call replaces both the skill and `/evaluate-knowledge`

| Field | Was produced by | Used for |
|---|---|---|
| `summary`, `key_findings`, `suggestions_work`, `suggestions_personal` | `/article` | Note body |
| `tags` (≤5), `kb_folder` | `/evaluate-knowledge` inbox step | Frontmatter, filing |
| `takeaway`, `action` | `/evaluate-knowledge` Daily Dose | Daily note, evaluation log |

The prompt sends only top-level knowledge-base folder names. The skill could file into nested folders; this can't, and the simplification is deliberate.

### D5. Simplified note layout (user decision)

Frontmatter: `created`, `tags`, `source`, `author: "[[Name]]"`, `evaluated`. Body: Metadata, Management Summary, Key Findings, Suggestions (For Work / For Personal Life), and the extracted text in a collapsed `[!info]-` callout.

Dropped relative to the skills:
- the `type/reference`, `area/learning` and `status/inbox` tags
- the "Relevance to Your Questions" section (the scheduled run asks no questions)
- the skill's separate "Evaluation" section
- summary mode for long articles (the text is capped at `extraction.max_words` instead)

`evaluated: <today>` is set so a later manual `/evaluate-knowledge` should skip the note. It hasn't been verified that the skill's `evaluated >= modified` comparison treats a same-day date and file time as "already evaluated"; if not, the manual skill re-evaluates the note, which is harmless.

### D6. Filing and links

`kb_folder` is normalised: whitespace and trailing slashes trimmed, a leading `<knowledge_base>/` removed, then compared case-insensitively with existing top-level folders. No match creates a new folder. An empty name, or one still containing `/`, `\` or `..`, goes to `folders.kb_fallback` (default `Misc`). Links use `[[<filename stem>|<title>]]`, because filenames are hyphenated and the title isn't the filename. `|` is escaped inside the log table.

### D7. Article extraction

The page is fetched with `httpx` (timeout, user agent, redirects followed), then `trafilatura.extract(html, with_metadata=True, output_format="json")`. `FeedManager` stores `item.content[0].value` when present, else `summary`, so full-text feeds give a fallback. A retry entry that is still in its feed is replaced by the feed copy during dedupe (D9), so it carries content too. A retry entry that has left the feed relies on the page alone. Status codes 401, 402, 403, 404, 410 and 451 are permanent only when the feed text is also too short. 429, 5xx and network errors are transient on the same condition.

**Feed probe (task 1.3, 2026-10-30, the 14 feeds in `exports/feeds.opml`):**
- 3 feeds are dead: `review.firstround.com/feed.xml` (404), `www.nfx.com/feed.xml` (404) and `www.reforge.com/blog/rss.xml` (500). The iMac's list may differ.
- 10 of the 11 live feeds carry the full text in `entry.content[0].value`. Their `summary` is 12–61 words, below `min_words`, so today's summary-only storage leaves no usable fallback.
- `simonwillison.net/atom/everything/` has no `content`; feedparser puts the post body in `summary`.
- The latest article page of every live feed returned HTTP 200 to a plain `httpx` GET with the configured user agent.
- Substack paid posts (Lenny's Newsletter, The Pragmatic Engineer newsletter) carry only a 250–325-word preview in the feed, and the page shows the same preview. That passes `min_words`. See Risks.

### D8. Prompt layout for prefix caching

The system message holds the fixed instructions, the schema, the output language, the interest profile and the folder list. These are identical for every entry in a run. The user message holds the entry metadata and text. Melious bills cache reads at EUR 0.01 per 1M tokens, so the repeated profile is nearly free whenever the serving provider caches. The prompt templates are `templates/prompts/analysis-system.md.j2` and `analysis-user.md.j2`, and the JSON schema in the system prompt is generated from the pydantic `Analysis` model that validates the reply; the note template is `templates/notes/article.md.j2`.

### D9. Run loop

1. Preflight: vault folder, knowledge-base folder and interest profile exist, and the key resolves. Any failure is fatal before any entry is touched.
2. Fetch feeds through `httpx` with `feeds.request_timeout`, then parse the bytes with feedparser.
3. Drop non-`articles` categories (logged per feed).
4. Merge new and retry entries by guid: the feed copy wins, and the guid set marks retries.
5. Drop stale new entries (`processing.max_entry_age_days`).
6. Apply `--limit`. In dry-run, stop here and list the entries with skip counts.
7. Process entries until done, or until `processing.max_run_minutes` or `llm.max_cost_per_run_eur` is reached.
8. Record the run as `completed` or `failed` (new `Database.record_run_failed(run_id, error)`), then notify.

A `try/finally` around steps 2–7 makes sure the run is recorded as failed on any unhandled exception. The notification passes its text as an `osascript` argument (`on run argv`), not inside the script text.

### D10. Module layout

```
src/extraction.py   ExtractedArticle, ExtractionError(permanent), extract_article()
src/llm.py          resolve_api_key(), MeliousClient.complete() -> Completion(content, finish_reason, usage),
                    FatalRunError, LLMError (transient)
src/analysis.py     Analysis (pydantic), load_context(), build_messages(), analyze() -> AnalysisResult,
                    AnalysisError (transient, carries cost spent)
src/vault_writer.py write_note(), append_daily_dose(), upsert_evaluation_log()
src/processor.py    process_entry() -> ProcessingResult(success, note_path, step, error,
                                                        permanent, cost_eur)
src/pipeline.py     run loop (D9), notification
```

### D11. Configuration additions (`config/defaults.yaml`)

```yaml
llm:
  base_url: "https://api.melious.ai/v1"
  model: "deepseek-v4.1-flash"
  keychain_service: "melious-api-key"
  timeout_seconds: 180
  max_retries: 2
  max_output_tokens: 8000
  reasoning_effort: null              # null = model default (reasoning on); "none" turns it off
  output_language: "English"
  price_input_per_mtok: 0.20          # EUR
  price_cached_input_per_mtok: 0.01   # EUR
  price_output_per_mtok: 1.00         # EUR
  max_cost_per_run_eur: 2.00
extraction:
  min_words: 150
  max_words: 30000
processing:
  max_entry_age_days: 14
  max_run_minutes: 60
folders:
  kb_fallback: "Misc"
```

The keys `processing.youtube_timeout`, `podcast_timeout`, `article_timeout`, `evaluate_batch_size` and `evaluate_timeout` become unused. They stay one release so an old `user.yaml` still loads. Worst-case time for one entry with these values is about 18 minutes: 3 attempts × 180 s, doubled by a repair or truncation retry. The 60-minute run limit bounds the total.

### D12. Key resolution

Order: process environment, then `MELIOUS_API_KEY` in the project's `.env` (read with `dotenv_values`, so it works under launchd and in an interactive shell), then `security find-generic-password -s <service> -w` with a 10-second timeout. The `.env` route is the primary one on the iMac, because the Keychain can be locked or prompt for access when launchd fires. The key goes only to the SDK client. Error messages are cut to the HTTP status and the error body's `message` field.

### D13. OPML backup guard

The Monday backup moves from `run.sh` into `scripts/backup_feeds.sh`, which `run.sh` calls and which runs only when `git rev-parse --abbrev-ref HEAD` is `master`. Otherwise the iMac, while on `feat/api-pipeline`, would commit to the feature branch and push it. Pushing a backup straight to `master` is existing behaviour and out of scope here.

## Risks / Trade-offs

- [The flash-tier model writes weaker personalized suggestions than Claude did] → Task 9.1 compares new notes with March notes from the same feeds before switching over. `llm.model` is config.
- [Article sites block non-browser requests] → Full-text feeds fall back to their own text. Others become permanent "not extractable" and show in the run count. Measure the rate in 9.1.
- [A Substack paid-post preview (250–325 words) becomes a thin note about a teaser] → Not handled in this change. Task 9.1 checks how such notes read. If they aren't useful, a follow-up can raise `min_words` per feed or detect Substack's paywall marker. The skill had the same problem and wrote a note from the preview.
- [The 150-word minimum turns short link posts into permanent skips] → This is intended: link posts made thin notes. Lower `extraction.min_words` if wanted.
- [The interest profile, including personal context, goes to Melious on every call] → Accepted for this personal tool. README states it.
- [The cost ceiling undercounts] → A timed-out attempt reports no usage but may still be billed. The ceiling is a guard, not an exact figure.
- [Obsidian edits today's daily note between our read and our rename] → The window is milliseconds at 06:00. Accept it.
- [The Melious key used for testing belongs to another project's account] → See Open Questions.

## Integration Results (task 9.1, 2026-10-30)

These come from a fresh clone on the MacBook. The scratch vault held copies of the real interest profile, daily-note template and evaluation log, plus empty copies of the 18 knowledge-base folders. Feeds came from `exports/feeds.opml`.

- **Outcomes:** 11 articles from 7 feeds all became notes, with no failures and no permanent skips. The 13 feeds were narrowed by the stale filter to 60 candidates, with 150 skipped as stale.
- **Cost:** EUR 0.0018–0.0056 per article. With reasoning on, the mean was about EUR 0.0035; with reasoning off it was about EUR 0.0020 (two samples).
- **Filing:** notes landed in sensible existing folders: AI & ML, Strategy, Business models, Development, and Productivity setup (with AI).
- **Daily note:** created from the Templater template, with `created: 2026-10-30` and `day: Friday` filled in, and entries placed under its `# Daily dose of know-how` H1.
- **Evaluation log:** the first run exposed blank lines inside the real log's table. Rows were inserted after the first block and the total dropped to 325. That is fixed and covered by tests. The rerun took the total from 429 to 430, with the new row last.
- **Quality:** compared with the March Claude-written note from the same blog (`Python-Vulnerability-Lookup`), the new notes are at least as specific and personalised. Summaries are 3 paragraphs. They sometimes have 11 findings and 6 suggestions, above the 5–10 and 3–5 asked for but inside the schema limits.
  - Suggestions quote the interest profile verbatim, including an outdated job title. Updating the profile is the fix, not the code.
- **Reasoning off:** two samples read as well as reasoning-on notes at about 40% lower cost. The default stays on; the difference is about EUR 0.03 a month at this volume.
- **Teaser notes:** one gated Stratechery page (Sharp Tech) produced a thin note that says the page is gated. This is the teaser risk above; it applies to Stratechery as well as Substack.

## Code Review Changes (2026-10-31)

A review of the whole branch found no critical issues. These changes came out of it:

- **Bounded downloads (`src/http_fetch.py`).** httpx timeouts apply per network operation, so a server sending a byte every few seconds never trips them, and the run time limit is only checked between entries. Feeds and pages are now streamed against our own clock: pages 90 s and 10 MB, feeds 60 s and 20 MB. Pages must be `text/*` or `application/xhtml+xml`.
- **Stop rule for repeated analysis failures.** Only HTTP 401-404 were fatal, so a config error answered with HTTP 400, or a multi-day outage, used one retry attempt per entry per day until every entry was given up. Now 3 analysis failures in a row before any analysis works in that run are queued as usual, then the run stops as fatal. The 3 are queued rather than held back so the same entries cannot block every future run.
- **Link titles.** `[`, `]` and `|` are removed or replaced in link display text, so titles like "Post | Site" keep the evaluation-log table intact.
- **Templater.** `<%` in anything written to the vault becomes `<\%`. Whether "Trigger Templater on new file creation" is on in the vault was not checked; the change is safe either way.
- **Smaller fixes.** The Daily Dose section ends at the next heading of any level; written files keep their permissions (new ones 0644) and are fsynced; a folder named after the knowledge base goes to the fallback; a 404 always names the model; a crash shows a "Run stopped" notification.
- **Not changed:** same-title notes in different folders sharing a log row, analysis cost lost when writing raises a non-`OSError`, one guid in two feeds failing twice in a run, `run.sh` skipping the Monday backup after a stopped run, retries sorted after new entries. All rare or harmless.

## Migration Plan

1. On the iMac: `git fetch && git checkout feat/api-pipeline`, then `uv sync`.
2. Add `MELIOUS_API_KEY=...` to the project's gitignored `.env`.
3. `uv run ai-research-assistant setup`. Upgrade mode re-renders the plist and tests the key and model.
4. `uv run ai-research-assistant run --dry-run` to see the backlog after the stale filter.
5. `uv run ai-research-assistant run --limit 5 --verbose`, then read the notes, today's daily note and the last log rows.
6. Leave launchd as it is. Check `~/.claude/logs/ai-research-assistant.log` after the next 06:00 run.

**Rollback:** `git checkout master`. Written notes are plain Markdown. The only schema change is the nullable `pipeline_runs.error` column, which the old code ignores. Entries that failed permanently under the new code are marked processed, so the old code also skips them.

## Open Questions

- Use a separate Melious API key for this personal tool, so its cost doesn't show on another project's account? This changes only `.env`.
- Should reasoning be on or off? Task 1.1 showed it can be switched off and costs little: at the measured rates a 5,000-token article costs about EUR 0.002–0.003 with reasoning on. The default stays on (`llm.reasoning_effort: null`) because suggestion quality matters more than that cost, and the truncation retry covers its main risk. Task 9.1 compares one batch with `reasoning_effort: "none"` before the default is final.
