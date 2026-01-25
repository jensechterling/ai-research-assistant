#!/bin/bash
set -e

# Navigate to project directory
cd "/Users/jens.echterling/GitHub/Development/AI research assistant"

# Load environment variables (if any)
if [ -f .env ]; then
    source .env
fi

# Run pipeline
uv run ai-research-assistant run

# Export OPML and commit to GitHub (weekly backup - Mondays)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq 1 ]; then
    uv run ai-research-assistant feeds export
    git add exports/feeds.opml
    git diff --cached --quiet || git commit -m "Weekly OPML backup $(date +%Y-%m-%d)"
    git push
fi
