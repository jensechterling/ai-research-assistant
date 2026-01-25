# Content Pipeline

Automated content aggregation pipeline that fetches articles, YouTube videos, and podcasts from RSS feeds and creates structured Obsidian notes using Claude Code skills.

## Features

- **Feed Management**: Subscribe to RSS feeds via CLI
- **Multi-Format Support**: Articles, YouTube, Podcasts
- **Personalized Summaries**: Uses your interest profile for relevant insights
- **Automatic Retry**: Failed items retry with exponential backoff
- **Daily Automation**: Runs automatically via launchd

## Quick Start

```bash
# Install dependencies
uv sync

# Add some feeds
uv run content-pipeline feeds add "https://stratechery.com/feed/" -c articles

# Run manually
uv run content-pipeline run

# Check status
uv run content-pipeline status
```

## Installation

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/content-pipeline.git
cd content-pipeline

# Install dependencies
uv sync

# Install automation (runs daily at 6 AM)
./scripts/install.sh
```

## Commands

| Command | Description |
|---------|-------------|
| `content-pipeline run` | Run the pipeline |
| `content-pipeline run --dry-run` | Preview without processing |
| `content-pipeline status` | Show pending items and stats |
| `content-pipeline feeds add URL` | Add a feed |
| `content-pipeline feeds list` | List all feeds |
| `content-pipeline feeds export` | Export to OPML |

## Dependencies

- Python 3.11+
- uv (package manager)
- Claude Code CLI

## License

MIT
