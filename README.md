# AI Research Assistant for Obsidian

Automated RSS pipeline that fetches articles, YouTube videos, and podcasts, then uses [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills to create personalized analysis notes in your Obsidian vault.

```
RSS Feeds → Pipeline → Claude Code Skills → Obsidian Notes
```

Each note includes a management summary, key findings, and personalized suggestions for work and personal life — based on your interest profile.

## What It Does

- **Articles**: Extracts web articles, generates analysis with key findings and suggestions
- **YouTube**: Downloads transcripts, creates summaries with clickable timestamp timelines
- **Podcasts**: Finds existing transcripts from RSS feeds, generates analysis
- **Evaluate Knowledge**: Post-processes new notes with personalized takeaways

## Requirements

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
- **Claude Code CLI** — [install instructions](https://docs.anthropic.com/en/docs/claude-code)
- **Obsidian** with a vault you want notes delivered to
- **Node.js** (for Obsidian MCP server via npx)
- **yt-dlp** (for YouTube transcripts) — `brew install yt-dlp`

## Quick Start

```bash
# Clone and install
git clone https://github.com/jensechterling/ai-research-assistant.git
cd ai-research-assistant
uv sync

# Run setup wizard
uv run ai-research-assistant setup

# Add some feeds
uv run ai-research-assistant feeds add https://example.com/feed.xml -c articles
uv run ai-research-assistant feeds add "https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID" -c youtube

# Test run
uv run ai-research-assistant run --dry-run

# Real run
uv run ai-research-assistant run -v
```

## Setup

The setup wizard (`ai-research-assistant setup`) handles everything:

1. Asks for your Obsidian vault path
2. Shows default folder structure (customizable)
3. Generates skill files and configuration
4. Installs skills to `~/.claude/skills/`
5. Creates an interest profile template in your vault
6. Checks dependencies

### Interest Profile

During setup, you can either create a new interest profile from a template or link an existing file in your vault. Fill it in with your work context and personal interests — this is how the skills personalize suggestions for you.

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

## Configuration

All configuration lives in `config/user.yaml` (created by setup). Defaults are in `config/defaults.yaml`.

```yaml
# config/user.yaml — your overrides
vault:
  path: "~/Obsidian/My vault"

folders:
  youtube: "Clippings/Youtube extractions"
  podcast: "Clippings/Podcast extractions"
  article: "Clippings/Article extractions"
  knowledge_base: "Knowledge Base"
  daily_notes: "Daily Notes"
  clippings: "Clippings"
  templates: "Templates"

schedule:
  hour: 6
  minute: 0
```

After editing config, re-run `ai-research-assistant setup` to regenerate templates.

## Commands

```bash
# Pipeline
ai-research-assistant run                  # Process all pending items
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
skills/
  _templates/            # Jinja2 templates (version-controlled)
    article/
    youtube/
    podcast/
    evaluate-knowledge/
  article/               # Generated from templates (gitignored)
  youtube/               # Symlinked to ~/.claude/skills/
  ...
src/
  pipeline.py            # Main orchestration
  skill_runner.py        # Invokes Claude Code skills
  config.py              # Configuration loading
  setup.py               # Setup wizard
  feed_manager.py        # RSS feed management
  database.py            # SQLite tracking
```

## How It Works

1. `FeedManager` fetches unprocessed RSS entries
2. `Database` retrieves failed items due for retry (exponential backoff: 1h, 4h, 12h, 24h)
3. For each entry, `SkillRunner` invokes the appropriate Claude Code skill (`/article`, `/youtube`, `/podcast`)
4. Skills read your interest profile, process content, and write notes to Obsidian via MCP
5. New notes are post-processed with `/evaluate-knowledge` for additional personalized takeaways
6. Results are tracked in SQLite (`data/pipeline.db`)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Logging

**Log files:** `~/code/ai-research-assistant/logs/pipeline.log`

Daily rotating logs with automatic cleanup (30 day retention).

**Log levels:**
- File: DEBUG (all details)
- Console: INFO (summary only)

**Verbose mode:**
```bash
uv run ai-research-assistant run --verbose  # Shows DEBUG in console too
```

**View logs:**
```bash
# Today's log
tail -f ~/code/ai-research-assistant/logs/pipeline.log

# Last 100 lines
tail -100 ~/code/ai-research-assistant/logs/pipeline.log

# Search for errors
grep ERROR ~/code/ai-research-assistant/logs/*.log

# Performance analysis
grep "Created:" ~/code/ai-research-assistant/logs/pipeline.log
```

**Configuration:**
- Retention days: `config/user.yaml` → `logging.retention_days: 30`

## Contributing

This is a personal project. I'm not accepting pull requests or feature requests, but you're welcome to fork and adapt it for your own use.

## License

MIT
