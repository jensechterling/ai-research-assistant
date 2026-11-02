#!/bin/bash
# Weekly OPML backup of the feed list (Mondays).
# Exports to a temporary file and commits it as exports/feeds.opml onto the backup/feeds
# branch through a temporary index, so the checked-out branch, its index and the working
# tree are never touched and nothing is pushed to master.
#
# Each run builds on the remote branch when it can be fetched, and pushes whenever the
# remote is not at the local tip. A failed push or a backup from another machine is
# therefore caught up the next Monday instead of being skipped or rejected for good.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

UV="${UV:-uv}"
DAY_OF_WEEK="${DAY_OF_WEEK:-$(date +%u)}"
BRANCH="backup/feeds"
LOCAL_REF="refs/heads/$BRANCH"
REMOTE_REF="refs/remotes/origin/$BRANCH"
FILE="exports/feeds.opml"

if [ "$DAY_OF_WEEK" -ne 1 ]; then
    exit 0
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

$UV run ai-research-assistant feeds export --output "$WORK_DIR/feeds.opml"

# Bring the remote branch in. A missing remote branch and an unreachable remote both
# leave FETCHED=0; the push below tells them apart.
FETCHED=0
if git fetch -q origin "+$LOCAL_REF:$REMOTE_REF" 2>/dev/null; then
    FETCHED=1
fi

# Build on the remote tip when known, so this machine never diverges from it.
PARENT="$(git rev-parse -q --verify "$REMOTE_REF^{commit}" || git rev-parse -q --verify "$LOCAL_REF^{commit}" || true)"

# A tree holding only the OPML file, built in an index of our own.
rm -f "$WORK_DIR/index"
BLOB="$(git hash-object -w "$WORK_DIR/feeds.opml")"
TREE="$(GIT_INDEX_FILE="$WORK_DIR/index" bash -c \
    'git update-index --add --cacheinfo "100644,$1,$2" && git write-tree' _ "$BLOB" "$FILE")"

if [ -n "$PARENT" ] && [ "$(git rev-parse "$PARENT^{tree}")" = "$TREE" ]; then
    COMMIT="$PARENT"
    echo "Weekly OPML backup: feeds.opml unchanged since the last backup"
else
    MESSAGE="Weekly OPML backup $(date +%Y-%m-%d)"
    if [ -n "$PARENT" ]; then
        COMMIT="$(git commit-tree "$TREE" -p "$PARENT" -m "$MESSAGE")"
    else
        COMMIT="$(git commit-tree "$TREE" -m "$MESSAGE")"
    fi
fi
git update-ref "$LOCAL_REF" "$COMMIT"

REMOTE_TIP="$(git rev-parse -q --verify "$REMOTE_REF^{commit}" || true)"
if [ "$FETCHED" -eq 1 ] && [ "$REMOTE_TIP" = "$COMMIT" ]; then
    exit 0
fi

git push -q origin "$LOCAL_REF:$LOCAL_REF"
git update-ref "$REMOTE_REF" "$COMMIT"
echo "Weekly OPML backup pushed to $BRANCH"
