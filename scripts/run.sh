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

# Run pipeline. A stopped run exits non-zero; keep that status for launchd,
# but run the weekly backup first.
status=0
$UV run ai-research-assistant run || status=$?

# Weekly OPML backup (Mondays)
backup_status=0
UV="$UV" "$SCRIPT_DIR/backup_feeds.sh" || backup_status=$?

if [ "$status" -ne 0 ]; then
    exit "$status"
fi
exit "$backup_status"
