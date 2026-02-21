#!/bin/bash
set -e

# Self-locate: derive project root from this script's location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ -f .env ]; then
    source .env
fi

# Discover uv at runtime (launchd PATH is minimal)
if command -v uv >/dev/null 2>&1; then
    UV="uv"
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV="$HOME/.local/bin/uv"
elif [ -x "$HOME/.cargo/bin/uv" ]; then
    UV="$HOME/.cargo/bin/uv"
else
    echo "ERROR: uv not found. Install from https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

# Run pipeline
$UV run ai-research-assistant run

# Weekly OPML backup (Mondays)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq 1 ]; then
    $UV run ai-research-assistant feeds export
    git add exports/feeds.opml
    git diff --cached --quiet || git commit -m "Weekly OPML backup $(date +%Y-%m-%d)"
    git push
fi
