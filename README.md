# AI Research Assistant for Obsidian

Automated RSS pipeline that reads the articles from your feeds every morning, analyzes each one with an LLM against your interest profile, and files a personalized note into your Obsidian knowledge base.

```
RSS feeds → extract article text → one LLM call (Melious) → note filed in your vault
```

Each note includes a management summary, key findings, and personalized suggestions for work and personal life, based on your interest profile. Each processed article also gets an entry in your daily note and a row in your evaluation log.

## What It Does

- **Scheduled pipeline (articles):** downloads each new article, extracts the main text (falling back to the feed's own full text), asks the model for a structured analysis, and writes the note into the best-fitting knowledge-base folder.
- **Daily Dose:** adds a takeaway and an action for every new note to today's daily note.
- **Evaluation log:** adds a row per note to `evaluation-log.md` in your knowledge base.
- **Manual skills:** `/article`, `/youtube`, `/podcast` and `/evaluate-knowledge` are Claude Code skills you can run yourself. The scheduled pipeline does not use them, and it does not process YouTube or podcast feeds.

The pipeline calls [Melious](https://melious.ai), an EU inference API that speaks the OpenAI request format, with `deepseek-v4.1-flash` by default. Article text and your interest profile are sent to Melious with every request.

## Requirements

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
- **A Melious API key**
- **Obsidian** with a vault you want notes delivered to
- Optional, for the manual skills only: the **Claude Code CLI** ([install instructions](https://docs.anthropic.com/en/docs/claude-code)) and **yt-dlp** (`brew install yt-dlp`)

## Quick Start

```bash
# Clone and install
git clone https://github.com/jensechterling/ai-research-assistant.git
cd ai-research-assistant
uv sync

# Add your Melious API key
cp .env.example .env
# then edit .env: MELIOUS_API_KEY=...

# Run setup wizard (also tests the key)
uv run ai-research-assistant setup

# Add some article feeds
uv run ai-research-assistant feeds add https://example.com/feed.xml -c articles

# Test run
uv run ai-research-assistant run --dry-run

# Real run, a few items first
uv run ai-research-assistant run -v --limit 3
```

## Setup

The setup wizard (`ai-research-assistant setup`) handles everything:

1. Asks for your Obsidian vault path
2. Shows default folder structure (customizable)
3. Generates skill files and the launchd plist
4. Installs the manual skills to `~/.claude/skills/`
5. Creates an interest profile template in your vault
6. Checks dependencies and sends one small request to Melious to check your key and model

### API Key

The pipeline looks for the Melious key in this order:

1. The `MELIOUS_API_KEY` environment variable
2. `MELIOUS_API_KEY=...` in the project's `.env` file (gitignored)
3. The macOS Keychain, under the service name in `llm.keychain_service` (default `melious-api-key`):
   `security add-generic-password -s melious-api-key -a ai-research-assistant -w`

For scheduled runs, use `.env`: the Keychain can be locked when the job fires.

### Interest Profile

During setup, you can either create a new interest profile from a template or link an existing file in your vault. Fill it in with your work context and personal interests. This is how the analysis personalizes suggestions for you.

### Scheduled Runs

To run the pipeline daily on a schedule:

```bash
uv run ai-research-assistant setup --install-schedule
```

This auto-detects your platform:

- **macOS**: Installs a launchd job (default: daily at 6:00 AM)
- **Linux**: Installs a cron job (default: daily at 6:00 AM)
- **Windows**: Prints instructions for manual Task Scheduler setup

To customize the schedule time, set `schedule.hour` and `schedule.minute` in `config/user.yaml` and re-run setup.

To remove the schedule:
- **macOS**: `launchctl unload ~/Library/LaunchAgents/com.claude.ai-research-assistant.plist`
- **Linux**: `crontab -e` and remove the `# ai-research-assistant` lines

On Mondays the scheduled script also exports your feed list to `exports/feeds.opml`, commits it and pushes, but only when the checkout is on `master`.

## Configuration

All configuration lives in `config/user.yaml` (created by setup). Defaults are in `config/defaults.yaml`.

```yaml
# config/user.yaml — your overrides
vault:
  path: "~/Obsidian/My vault"

folders:
  knowledge_base: "Knowledge Base"   # notes are filed into its top-level subfolders
  daily_notes: "Daily Notes"
  templates: "Templates"             # needs "Daily Note.md" (Templater dates are filled in)
  kb_fallback: "Misc"                # used when the model names an unusable folder

llm:
  model: "deepseek-v4.1-flash"
  reasoning_effort: null             # "none" turns reasoning off
  max_cost_per_run_eur: 2.00

extraction:
  min_words: 150                     # shorter articles are skipped as not extractable

processing:
  max_entry_age_days: 14             # older new entries are skipped
  max_run_minutes: 60

schedule:
  hour: 6
  minute: 0
```

After editing folder settings, re-run `ai-research-assistant setup` to regenerate the skill files.

### Cost

At Melious's prices for `deepseek-v4.1-flash` (EUR 0.20 per million input tokens, EUR 1.00 per million output tokens), a typical article costs well under one cent. Each run logs the cost per article and in total, shows the total in its notification, and stops starting new articles once `llm.max_cost_per_run_eur` is reached.

## Commands

```bash
# Pipeline
ai-research-assistant run                  # Process all pending articles
ai-research-assistant run --dry-run        # Preview without processing
ai-research-assistant run -v --limit 3     # Verbose, max 3 items
ai-research-assistant status               # Show pending items and last run

# Feeds
ai-research-assistant feeds add URL -c articles|youtube|podcasts
ai-research-assistant feeds list
ai-research-assistant feeds remove URL
ai-research-assistant feeds export         # OPML export
ai-research-assistant feeds import file.opml
```

## Upgrading

```bash
git pull
uv sync
uv run ai-research-assistant setup
```

The setup wizard detects existing configuration and silently re-renders templates from updated sources. Your `config/user.yaml` and vault content are never touched.

## Architecture

```
config/
  defaults.yaml          # Sensible defaults (version-controlled)
  user.yaml              # Your overrides (gitignored, created by setup)
templates/
  prompts/               # System and user prompt for the analysis call
  notes/article.md.j2    # Note layout
skills/
  _templates/            # Manual Claude Code skills as Jinja2 templates
src/
  pipeline.py            # Run loop: selection, limits, outcomes, notification
  processor.py           # One entry: extract → analyze → write → bookkeeping
  extraction.py          # Article download and text extraction
  analysis.py            # Prompt, JSON validation, repair and truncation retries
  llm.py                 # Melious client and API key resolution
  vault_writer.py        # Notes, Daily Dose, evaluation log
  feed_manager.py        # RSS feed management
  database.py            # SQLite tracking
  config.py              # Configuration loading
  setup.py               # Setup wizard
```

## How It Works

1. `FeedManager` downloads each feed (with a timeout) and returns entries not yet processed.
2. The run skips non-article feeds, entries older than `max_entry_age_days`, and failed entries still waiting for their retry time (backoff: 1h, 4h, 12h, 24h).
3. For each entry, the article text is extracted. Blocked or too-short articles are skipped for good; network problems are retried later.
4. One request to Melious returns a JSON analysis, which is validated. Invalid replies get one repair request, and replies cut off at the token limit are retried with a larger limit.
5. The note is written into the chosen knowledge-base folder, then the daily note and evaluation log are updated.
6. A rejected API key, an empty account, an unknown model or a missing profile stops the run without queueing anything. Results are tracked in SQLite (`data/pipeline.db`).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Contributing

This is a personal project. I'm not accepting pull requests or feature requests, but you're welcome to fork and adapt it for your own use.

## License

MIT
