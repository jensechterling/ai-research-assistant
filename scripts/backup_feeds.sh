#!/bin/bash
# Weekly OPML backup of the feed list (Mondays).
# Commits and pushes only when the checkout is on master, so a machine running
# a feature branch never commits to it or triggers CI by pushing it.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

UV="${UV:-uv}"
DAY_OF_WEEK="${DAY_OF_WEEK:-$(date +%u)}"
if [ "$DAY_OF_WEEK" -ne 1 ]; then
    exit 0
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
if [ "$BRANCH" != "master" ]; then
    echo "Skipping weekly OPML backup: checkout is on '$BRANCH', not master"
    exit 0
fi

$UV run ai-research-assistant feeds export
git add exports/feeds.opml
git diff --cached --quiet || git commit -m "Weekly OPML backup $(date +%Y-%m-%d)"
git push
