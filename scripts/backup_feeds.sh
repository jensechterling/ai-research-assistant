#!/bin/bash
# Weekly OPML backup of the feed list (Mondays).
# Commits exports/feeds.opml onto the backup/feeds branch through a temporary index, so
# the checked-out branch, its index and the working tree are never touched and nothing
# is pushed to master. Pushes only when the file changed since the last backup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

UV="${UV:-uv}"
DAY_OF_WEEK="${DAY_OF_WEEK:-$(date +%u)}"
BRANCH="backup/feeds"
FILE="exports/feeds.opml"

if [ "$DAY_OF_WEEK" -ne 1 ]; then
    exit 0
fi

$UV run ai-research-assistant feeds export

# A machine without a local copy of the branch continues from the remote one, if any.
if ! git rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null; then
    git fetch -q origin "$BRANCH:refs/heads/$BRANCH" 2>/dev/null || true
fi
PARENT="$(git rev-parse -q --verify "refs/heads/$BRANCH^{commit}" || true)"

# Build a tree holding only the OPML file, using an index of our own.
TMP_INDEX="$(mktemp)"
trap 'rm -f "$TMP_INDEX"' EXIT
rm -f "$TMP_INDEX"  # git needs a valid index file or none at all
BLOB="$(git hash-object -w "$FILE")"
TREE="$(GIT_INDEX_FILE="$TMP_INDEX" bash -c \
    'git update-index --add --cacheinfo "100644,$1,$2" && git write-tree' _ "$BLOB" "$FILE")"

if [ -n "$PARENT" ] && [ "$(git rev-parse "$PARENT^{tree}")" = "$TREE" ]; then
    echo "Weekly OPML backup: feeds.opml unchanged since the last backup"
    exit 0
fi

MESSAGE="Weekly OPML backup $(date +%Y-%m-%d)"
if [ -n "$PARENT" ]; then
    COMMIT="$(git commit-tree "$TREE" -p "$PARENT" -m "$MESSAGE")"
    git update-ref "refs/heads/$BRANCH" "$COMMIT" "$PARENT"
else
    COMMIT="$(git commit-tree "$TREE" -m "$MESSAGE")"
    git update-ref "refs/heads/$BRANCH" "$COMMIT"
fi

git push -q origin "refs/heads/$BRANCH:refs/heads/$BRANCH"
echo "Weekly OPML backup pushed to $BRANCH"
