---
created: '2026-01-25'
updated: '2026-01-25'
tags:
  - project
  - specification
  - claude-code
  - automation
---
# Content Pipeline - Build Specification

This document specifies a content aggregation pipeline that automatically imports articles, YouTube videos, and podcasts into Obsidian with personalized summaries. It is intended as a handover document for Claude Code to build the implementation.

---

## Project Overview

### Goal

Build an automated daily pipeline that:
1. Fetches new content from subscribed sources (blogs, newsletters, YouTube, podcasts)
2. Routes content to appropriate processors based on type
3. Delegates to Claude Code skills for summarization (`/article`, `/youtube`, `/podcast`)
4. Writes structured notes to the Obsidian vault
5. Triggers post-processing via existing `/evaluate-knowledge` skill on newly created files

### Design Principles

- **SQLite + feedparser** for feed management (lightweight, no Docker)
- **CLI for feed management** with automated OPML export to GitHub
- **iMac-only execution** with catch-up logic for missed runs
- **Delegate to skills for all content types** — `/article`, `/youtube`, `/podcast`
- **Verify before marking processed** — only mark items as done after confirming note exists
- **Retry failed items** — persist failures to SQLite, retry on subsequent runs
- **Clippings as inbox** — new content lands in Clippings folder with proper frontmatter
- **Post-processing via `/evaluate-knowledge`** — runs on list of newly created files only

### Repository Location

```
/Users/jens.echterling/GitHub/Development/AI research assistant/
```

Push to private GitHub repo after initial build.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FEED MANAGEMENT (SQLite + CLI)                    │
│                                                                      │
│  CLI commands for managing subscriptions:                            │
│  • content-pipeline feeds add <url> --category articles              │
│  • content-pipeline feeds remove <url>                               │
│  • content-pipeline feeds list                                       │
│  • content-pipeline feeds export  (OPML → GitHub)                   │
│                                                                      │
│  SQLite tracks:                                                      │
│  • Feed subscriptions (url, category, title)                        │
│  • Processed items (entry_id, processed_at, note_path)              │
│  • Failed items (entry_id, retry_count, last_error, next_retry)     │
│  • Pipeline runs (started_at, completed_at, items_processed)        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTENT PIPELINE (Python)                         │
│                                                                      │
│  1. CHECK last successful run → catch-up if missed                  │
│                              │                                       │
│  2. FETCH new entries via feedparser (not yet processed)            │
│                              │                                       │
│              ┌───────────────┼───────────────┐                      │
│              ▼               ▼               ▼                      │
│       ┌──────────┐    ┌──────────┐    ┌──────────┐                 │
│       │ YOUTUBE  │    │ PODCAST  │    │ ARTICLE  │                 │
│       │          │    │          │    │          │                 │
│       │ /youtube │    │ /podcast │    │ /article │                 │
│       │  skill   │    │  skill   │    │  skill   │  ← NEW SKILL    │
│       └──────────┘    └──────────┘    └──────────┘                 │
│              │               │               │                      │
│              └───────────────┴───────────────┘                      │
│                              │                                       │
│  3. VERIFY note exists in Obsidian                                  │
│                              │                                       │
│  4. Mark as processed in SQLite (or queue for retry)                │
│                              │                                       │
│  5. Trigger /evaluate-knowledge with list of new files              │
│                              │                                       │
│  6. NOTIFY with success count + failed items                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         OBSIDIAN VAULT                               │
│                                                                      │
│  ~/Obsidian/Professional vault/                                     │
│  ├── Clippings/                    ← New articles land here         │
│  ├── Clippings/Youtube extractions/ ← Via /youtube skill            │
│  └── (organized by /evaluate-knowledge)                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
AI research assistant/
├── README.md                               # Setup guide, usage docs
├── .env.example                            # Environment variables template
├── .env                                    # Local secrets (gitignored)
├── .gitignore
├── pyproject.toml                          # uv project definition
│
├── docs/
│   ├── Content Pipeline - Build Specification.md
│   └── plans/
│       └── 2026-01-25-content-pipeline.md
│
├── src/
│   ├── __init__.py
│   ├── main.py                             # CLI entry point
│   ├── pipeline.py                         # Main orchestration
│   ├── database.py                         # SQLite schema and operations
│   ├── feed_manager.py                     # feedparser + feed CRUD
│   ├── skill_runner.py                     # Claude Code CLI invocation
│   └── notifications.py                    # macOS notifications
│
├── skills/
│   └── article/
│       ├── SKILL.md                        # Quick reference (matches existing pattern)
│       └── article-workflow.md             # Detailed workflow
│
├── config/
│   └── settings.yaml                       # Pipeline configuration
│
├── templates/
│   └── com.claude.content-pipeline.plist   # launchd template
│
├── scripts/
│   ├── install.sh                          # Setup: copy plist, create dirs, wake schedule
│   ├── uninstall.sh                        # Teardown: remove plist
│   └── run.sh                              # Manual trigger wrapper
│
├── exports/
│   └── feeds.opml                          # Automated OPML export (committed)
│
├── data/                                   # Runtime data (gitignored)
│   └── pipeline.db                         # SQLite database
│
└── logs/                                   # Runtime logs (gitignored)
    └── .gitkeep
```

---

## Component Specifications

### 1. SQLite Database

**File:** `src/database.py`

**Purpose:** Store feed subscriptions, track processed items, manage retry queue, and log pipeline runs.

**Schema:**

```sql
-- Feed subscriptions
CREATE TABLE feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    category TEXT NOT NULL CHECK (category IN ('articles', 'youtube', 'podcasts')),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_fetched_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Processed entries (prevents reprocessing)
CREATE TABLE processed_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_guid TEXT UNIQUE NOT NULL,  -- RSS guid or URL hash
    feed_id INTEGER NOT NULL,
    entry_url TEXT NOT NULL,
    entry_title TEXT,
    published_at TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note_path TEXT,  -- Path to created Obsidian note (for verification)
    FOREIGN KEY (feed_id) REFERENCES feeds(id)
);

-- Retry queue for failed items
CREATE TABLE retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_guid TEXT UNIQUE NOT NULL,
    feed_id INTEGER NOT NULL,
    entry_url TEXT NOT NULL,
    entry_title TEXT,
    category TEXT NOT NULL,
    first_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_attempt_at TIMESTAMP,
    next_retry_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    FOREIGN KEY (feed_id) REFERENCES feeds(id)
);

-- Pipeline run history (for catch-up logic)
CREATE TABLE pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    items_fetched INTEGER DEFAULT 0,
    items_processed INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    status TEXT CHECK (status IN ('running', 'completed', 'failed'))
);

-- Indexes for common queries
CREATE INDEX idx_processed_guid ON processed_entries(entry_guid);
CREATE INDEX idx_retry_next ON retry_queue(next_retry_at);
CREATE INDEX idx_feeds_category ON feeds(category);
```

**Key operations:**

```python
class Database:
    def __init__(self, db_path: Path):
        """Initialize database, run migrations if needed."""
        pass

    def is_processed(self, entry_guid: str) -> bool:
        """Check if entry has already been processed."""
        pass

    def mark_processed(self, entry_guid: str, feed_id: int, note_path: Path) -> None:
        """Mark entry as successfully processed with note path."""
        pass

    def add_to_retry_queue(self, entry: Entry, error: str) -> None:
        """Add failed entry to retry queue with exponential backoff."""
        pass

    def get_retry_candidates(self) -> list[Entry]:
        """Get entries due for retry (next_retry_at <= now)."""
        pass

    def get_last_successful_run(self) -> datetime | None:
        """Get timestamp of last completed pipeline run (for catch-up)."""
        pass

    def record_run_start(self) -> int:
        """Start a new pipeline run, return run_id."""
        pass

    def record_run_complete(self, run_id: int, processed: int, failed: int) -> None:
        """Mark pipeline run as complete with stats."""
        pass
```

### 2. Feed Manager

**File:** `src/feed_manager.py`

**Purpose:** Manage feed subscriptions and fetch new entries via feedparser.

**Key methods:**

```python
class FeedManager:
    def __init__(self, db: Database):
        """Initialize with database connection."""
        pass

    def add_feed(self, url: str, category: str) -> Feed:
        """Add a new feed subscription."""
        # Auto-detect title from feed
        pass

    def remove_feed(self, url: str) -> None:
        """Remove a feed subscription."""
        pass

    def list_feeds(self, category: str | None = None) -> list[Feed]:
        """List all feeds, optionally filtered by category."""
        pass

    def fetch_new_entries(self) -> list[Entry]:
        """Fetch all new (unprocessed) entries from all active feeds."""
        # Uses feedparser to fetch each feed
        # Filters out already-processed entries via database
        pass

    def export_opml(self, output_path: Path) -> None:
        """Export all feeds to OPML format."""
        pass

    def import_opml(self, opml_path: Path) -> int:
        """Import feeds from OPML file, return count added."""
        pass
```

**Entry dataclass:**

```python
@dataclass
class Entry:
    guid: str  # Unique identifier (RSS guid or URL hash)
    title: str
    url: str
    content: str  # May be partial (RSS excerpt)
    author: str | None
    published_at: datetime
    feed_id: int
    feed_title: str
    category: str  # articles, youtube, podcasts
```

**Auto-detecting category from URL:**

```python
def detect_category(url: str) -> str:
    """Detect feed category from URL pattern."""
    if "youtube.com/feeds" in url:
        return "youtube"
    # Podcast detection could use feed content inspection
    return "articles"  # Default
```

**YouTube channel RSS format:**
```
https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
```

**Newsletter-to-RSS conversion:**
Use Kill the Newsletter (https://kill-the-newsletter.com/) to convert email newsletters to RSS feeds.

### 3. Article Skill (NEW)

**Location:** `skills/article/` (following existing skill structure)

**Purpose:** New Claude Code skill that extracts, summarizes, and writes article notes to Obsidian. Follows the same patterns as `/youtube` and `/podcast` skills.

**Files:**
- `skills/article/SKILL.md` — Quick reference
- `skills/article/article-workflow.md` — Detailed workflow

**Reference:** Reuse patterns from existing skills at `/Users/jens.echterling/GitHub/Productivity/Skills/obsidian-workflow-skills/skills/`

---

#### skills/article/SKILL.md

```markdown
---
name: article
description: Extract and summarize web articles into Obsidian notes with personalized insights connecting content to your work priorities
---

# Article Analysis

## Overview

Transforms web articles into searchable Obsidian notes with personalized suggestions. Extracts full article content, generates summaries connecting insights to your work priorities, and creates structured reference material.

## When to Use

- Analyzing blog posts or newsletter articles for insights
- Extracting key learnings from industry publications
- Processing research into knowledge base
- Building searchable reference library from web content
- Need personalized suggestions connecting article to work priorities
- Want structured summaries instead of reading full articles

## Quick Reference

| Task | Command | Output |
|------|---------|--------|
| Basic analysis | `/article URL` | Full analysis with content |
| With questions | `/article URL What does this say about X?` | Analysis + relevance section |
| Long article (>5000 words) | Automatic | Summary mode |

**Output location:** `Clippings/`

## Process Summary

1. Extract article content using WebFetch or trafilatura
2. Load interest-profile.md for context
3. Generate analysis (summary, findings, suggestions)
4. Auto-generate source tag from domain
5. Save to Obsidian vault

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Paywalled content | Falls back to RSS excerpt if available |
| Missing interest-profile.md | Create profile in vault root first for personalized suggestions |
| JavaScript-rendered pages | Some SPAs won't extract properly; note as limitation |

## Dependencies

- **Obsidian MCP** – For vault access
- **interest-profile.md** – In vault root

## Detailed Documentation

For complete workflow, code examples, and troubleshooting, see **article-workflow.md**.
```

---

#### skills/article/article-workflow.md

```markdown
# Article Analysis

## Overview

Transforms web articles into searchable Obsidian notes with personalized suggestions. Extracts article content, generates summaries connecting insights to your work priorities, and creates structured reference material.

## When to Use

- Analyzing blog posts or newsletter articles for insights
- Extracting key learnings from industry publications
- Processing research into knowledge base
- Building searchable reference library from web content
- Need personalized suggestions connecting article to work priorities

## Input

**Required:** Article URL as argument
\`\`\`
/article https://stratechery.com/article-name
\`\`\`

**Optional:** Add context or specific questions after the URL
\`\`\`
/article https://stratechery.com/article-name What does this say about AI strategy?
\`\`\`

## Vault Configuration

**Vault Root:** Your Obsidian vault (accessed via MCP)
**Interest Profile:** `interest-profile.md`
**Output Folder:** `Clippings/`

## Workflow

### 1. Extract Article Content

Use WebFetch tool to retrieve and parse the article:

\`\`\`
WebFetch URL with prompt: "Extract the full article content including title, author, publication date, and body text. Return as structured text."
\`\`\`

**Fallback for complex pages:** If WebFetch fails, try trafilatura via Python:

\`\`\`bash
pip3 install trafilatura 2>/dev/null
python3 << 'EXTRACT_EOF'
import trafilatura
import json

url = "ARTICLE_URL"
downloaded = trafilatura.fetch_url(url)
result = trafilatura.extract(downloaded, include_comments=False, include_tables=True,
                              output_format='json', with_metadata=True)
if result:
    data = json.loads(result)
    print(f"Title: {data.get('title', 'Unknown')}")
    print(f"Author: {data.get('author', 'Unknown')}")
    print(f"Date: {data.get('date', 'Unknown')}")
    print(f"Source: {data.get('sitename', 'Unknown')}")
    print("---CONTENT---")
    print(data.get('text', ''))
else:
    print("ERROR: Could not extract article content")
EXTRACT_EOF
\`\`\`

### 2. Load Work Context

Before generating analysis, load context for personalized suggestions:

\`\`\`
obsidian:read_note path="interest-profile.md"
\`\`\`

**Key context to extract:**
- **Work section**: Role, company, team size, current priorities, professional interests
- **Private section**: Personal interests, life context, hobbies

### 3. Generate Analysis

Based on the article content and work context, generate:

#### Management Summary (2-3 paragraphs)
- Main topic and thesis of the article
- Key argument or insight
- Target audience and value proposition

#### Key Findings (5-10 bullet points)
- Most important insights
- Actionable takeaways
- Notable quotes or claims
- Counterintuitive or contrarian ideas

#### Suggestions

**For HeyJobs** (3-5 bullets):
Connect article insights to the user's role and priorities from \`interest-profile.md\`. Consider how the content applies to their:
- Current role and responsibilities (CPO at jobs marketplace)
- Product strategy and growth challenges
- AI/ML applications and analytics
- Team and organizational leadership
- Monetization and business models

**For Me Personally** (3-5 bullets):
Connect to the user's personal interests from \`interest-profile.md\`. Consider applications for:
- Personal development and learning
- PKM and productivity systems
- Hobbies and side projects
- Tools and techniques to explore

#### Relevance Section (if user provided questions)
- How the article relates to user's specific interests
- Direct answers to any questions asked

### 4. Auto-Generate Source Slug

Generate tag-friendly slug from URL domain:

\`\`\`python
from urllib.parse import urlparse
domain = urlparse(url).netloc
domain = domain.removeprefix("www.")
name = domain.rsplit(".", 1)[0]
slug = name.replace(".", "-").replace("_", "-").lower()
\`\`\`

Examples:
- \`www.lennysnewsletter.com\` → \`lennysnewsletter\`
- \`stratechery.com\` → \`stratechery\`
- \`review.firstround.com\` → \`review-firstround\`
- \`oneusefulthing.substack.com\` → \`oneusefulthing-substack\`

### 5. Save to Obsidian

**Output Path:** \`Clippings/{Sanitized Title}.md\`

Sanitize title: remove special characters, replace spaces with hyphens, truncate to 80 chars.

#### File Structure

\`\`\`markdown
---
created: YYYY-MM-DD
tags: [type/reference, area/learning, status/inbox, source/{source_slug}]
source: {Article URL}
author: "[[{Author Name}]]"
---

# {Article Title}

## Metadata
- **Source:** {publication/site name}
- **Author:** {author}
- **Published:** {formatted date}
- **URL:** {full URL}

## Management Summary

{2-3 paragraph summary of the article content, main thesis, and value}

## Key Findings

- {finding 1}
- {finding 2}
- {finding 3}
...

## Suggestions

### For HeyJobs
- {suggestion connecting insight to product strategy/growth}
- {suggestion for team/product organization}
- {suggestion for AI/analytics/monetization priorities}

### For Me Personally
- {personal learning or leadership suggestion}
- {PKM or productivity application}
- {tool, technique, or trend to explore}

## Relevance to Your Questions

{Only include if user provided specific questions or context}

## Original Content

> [!info]- Full Article Text
> {Full article text in collapsed callout for searchability}
\`\`\`

## Content Length Strategy

| Word Count | Approach |
|------------|----------|
| < 2000 | **Standard**: Full analysis, complete text in callout |
| 2000-5000 | **Standard**: Full analysis, complete text in callout |
| > 5000 | **Summary mode**: Analysis + key excerpts only |

## Important Rules

1. **Always load interest profile** – Read \`interest-profile.md\` before analysis
2. **Handle extraction failures gracefully** – Clear error message with suggestions
3. **Sanitize filenames** – Remove \`/ \\ : * ? " < > |\` from titles
4. **Create folder structure** – Ensure \`Clippings/\` exists
5. **Use Obsidian MCP** – Write output using \`obsidian:write_note\` tool
6. **Include full text** – Store in collapsed callout for search
7. **Auto-generate source slug** – Don't rely on manual mapping

## Error Handling

**Paywalled content:**
\`\`\`
This article appears to be behind a paywall.

Extracted what was available:
- Title: {title}
- Excerpt: {available excerpt}

Options:
1. If you have access, copy/paste the article text
2. Check if there's an RSS feed with full content
3. Skip this article
\`\`\`

**JavaScript-rendered page:**
\`\`\`
Could not extract article content (page may require JavaScript).

Options:
1. Try a different URL for the same article
2. Copy/paste the article text manually
3. Use a reader-mode URL if available
\`\`\`

**Network error:**
\`\`\`
Could not access article URL.

Please check:
- URL is correct and publicly accessible
- No network connectivity issues
\`\`\`

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Paywalled content | Falls back to excerpt; inform user |
| Missing interest-profile.md | Create profile in vault root first |
| JavaScript-rendered pages | Note limitation; suggest alternatives |
| Very long articles | Use summary mode for >5000 words |

## Example Usage

\`\`\`
/article https://stratechery.com/2024/some-article-name
\`\`\`

\`\`\`
/article https://www.lennysnewsletter.com/p/article-title What are the key product insights?
\`\`\`

## Dependencies

- **Obsidian MCP** – For reading/writing notes to vault
- **WebFetch tool** – For article extraction (built into Claude Code)
- **trafilatura** (optional) – Fallback for complex pages: \`pip3 install trafilatura\`
\`\`\`

### 4. Skill Runner

**File:** `src/skill_runner.py`

**Purpose:** Unified Claude Code CLI invocation for all content types with permission handling and output verification.

**Implementation:**

```python
import subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class SkillResult:
    success: bool
    note_path: Path | None
    error: str | None
    stdout: str
    stderr: str

class SkillRunner:
    """Invoke Claude Code skills via CLI."""

    SKILL_CONFIG = {
        "articles": {
            "skill": "article",
            "timeout": 120,
            "output_folder": "Clippings",
        },
        "youtube": {
            "skill": "youtube",
            "timeout": 300,
            "output_folder": "Clippings/Youtube extractions",
        },
        "podcasts": {
            "skill": "podcast",
            "timeout": 600,
            "output_folder": "Clippings",
        },
    }

    VAULT_PATH = Path.home() / "Obsidian" / "Professional vault"

    def run_skill(self, entry: Entry) -> SkillResult:
        """Invoke appropriate skill for entry and verify output."""
        config = self.SKILL_CONFIG[entry.category]
        skill_name = config["skill"]
        timeout = config["timeout"]
        output_folder = config["output_folder"]

        # Claude Code CLI with auto-confirm permissions
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                f"/{skill_name} {entry.url}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return SkillResult(
                success=False,
                note_path=None,
                error=f"Skill exited with code {result.returncode}: {result.stderr}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        # Verify note was created
        note_path = self._find_created_note(entry.title, output_folder)

        if note_path is None:
            return SkillResult(
                success=False,
                note_path=None,
                error="Skill completed but no note found in expected location",
                stdout=result.stdout,
                stderr=result.stderr,
            )

        return SkillResult(
            success=True,
            note_path=note_path,
            error=None,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _find_created_note(self, title: str, folder: str) -> Path | None:
        """Find the note created by the skill."""
        output_dir = self.VAULT_PATH / folder
        safe_title = sanitize_filename(title)

        # Check for exact match
        expected_path = output_dir / f"{safe_title}.md"
        if expected_path.exists():
            return expected_path

        # Check for recently modified files (within last 60 seconds)
        # as backup in case title sanitization differs
        import time
        now = time.time()
        for path in output_dir.glob("*.md"):
            if now - path.stat().st_mtime < 60:
                return path

        return None


def sanitize_filename(title: str) -> str:
    """Remove/replace characters invalid in filenames."""
    replacements = {
        "/": "-",
        "\\": "-",
        ":": " -",
        "*": "",
        "?": "",
        '"': "'",
        "<": "",
        ">": "",
        "|": "-",
    }
    result = title
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result.strip()[:100]
```

**Permission handling:**

The `--dangerously-skip-permissions` flag bypasses all permission prompts. This is acceptable because:
- Pipeline runs in automated context on user's own machine
- Skills only access Obsidian vault and temp directories
- No network operations beyond fetching content

**Alternative:** Configure specific permissions in `~/.claude/settings.json` if finer control is needed.

### 5. Main Pipeline

**File:** `src/pipeline.py`

**Purpose:** Orchestrate the full pipeline with catch-up logic, retry handling, and verification.

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class PipelineResult:
    processed: int = 0
    failed: int = 0
    retried: int = 0
    skipped: int = 0
    created_notes: list[Path] = field(default_factory=list)
    failures: list[tuple[Entry, str]] = field(default_factory=list)


def run_pipeline(dry_run: bool = False) -> PipelineResult:
    """Execute the content pipeline."""

    # 1. Initialize components
    db = Database(Path("data/pipeline.db"))
    feed_manager = FeedManager(db)
    skill_runner = SkillRunner()

    # 2. Check for catch-up (missed runs)
    last_run = db.get_last_successful_run()
    if last_run:
        hours_since = (datetime.now() - last_run).total_seconds() / 3600
        if hours_since > 36:  # More than 1.5 days
            logger.warning(f"Catch-up mode: {hours_since:.1f} hours since last run")

    # 3. Start pipeline run
    run_id = db.record_run_start()

    # 4. Fetch new entries + retry candidates
    new_entries = feed_manager.fetch_new_entries()
    retry_entries = db.get_retry_candidates()
    all_entries = new_entries + retry_entries

    logger.info(f"Found {len(new_entries)} new entries, {len(retry_entries)} retries")

    if dry_run:
        for entry in all_entries:
            logger.info(f"[DRY RUN] Would process: {entry.title} ({entry.category})")
        return PipelineResult(skipped=len(all_entries))

    # 5. Process entries sequentially
    result = PipelineResult()

    for entry in all_entries:
        is_retry = entry in retry_entries

        try:
            # Run appropriate skill
            skill_result = skill_runner.run_skill(entry)

            if skill_result.success:
                # Verify note exists, then mark processed
                db.mark_processed(
                    entry_guid=entry.guid,
                    feed_id=entry.feed_id,
                    note_path=skill_result.note_path,
                )
                result.created_notes.append(skill_result.note_path)
                result.processed += 1
                if is_retry:
                    result.retried += 1
                logger.info(f"✓ Processed: {entry.title}")
            else:
                # Skill failed - add to retry queue
                db.add_to_retry_queue(entry, skill_result.error)
                result.failed += 1
                result.failures.append((entry, skill_result.error))
                logger.error(f"✗ Failed: {entry.title} - {skill_result.error}")

        except Exception as e:
            db.add_to_retry_queue(entry, str(e))
            result.failed += 1
            result.failures.append((entry, str(e)))
            logger.error(f"✗ Exception processing {entry.title}: {e}")

    # 6. Post-process with /evaluate-knowledge (only new files)
    if result.created_notes:
        logger.info(f"Running /evaluate-knowledge on {len(result.created_notes)} new notes")
        file_list = " ".join(f'"{p}"' for p in result.created_notes)
        subprocess.run(
            [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                f"/evaluate-knowledge {file_list}",
            ],
            timeout=600,
        )

    # 7. Record run completion
    db.record_run_complete(run_id, result.processed, result.failed)

    # 8. Send notification with stats
    send_notification(result)

    return result


def send_notification(result: PipelineResult) -> None:
    """Send macOS notification with pipeline results."""
    if result.failed == 0:
        title = "Content Pipeline ✓"
        message = f"Processed {result.processed} items"
    else:
        title = "Content Pipeline ⚠️"
        message = f"Processed {result.processed}, Failed {result.failed}"

    if result.failures:
        # Include first failure in notification
        first_fail = result.failures[0]
        message += f"\nFirst failure: {first_fail[0].title[:30]}..."

    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}"'
    ])
```

**Retry queue behavior:**

```python
def add_to_retry_queue(self, entry: Entry, error: str) -> None:
    """Add failed entry with exponential backoff."""
    # Backoff schedule: 1h, 4h, 12h, 24h, then give up
    backoff_hours = [1, 4, 12, 24]

    existing = self._get_retry_entry(entry.guid)
    if existing:
        retry_count = existing.retry_count + 1
        if retry_count >= len(backoff_hours):
            logger.warning(f"Giving up on {entry.title} after {retry_count} retries")
            self._remove_from_retry_queue(entry.guid)
            return
        next_retry = datetime.now() + timedelta(hours=backoff_hours[retry_count])
    else:
        retry_count = 0
        next_retry = datetime.now() + timedelta(hours=backoff_hours[0])

    self._upsert_retry_entry(entry, error, retry_count, next_retry)
```

### 6. CLI Entry Point

**File:** `src/main.py`

```python
import click
from pathlib import Path
from .database import Database
from .feed_manager import FeedManager
from .pipeline import run_pipeline

DB_PATH = Path(__file__).parent.parent / "data" / "pipeline.db"

@click.group()
def cli():
    """Content Pipeline - Import articles, videos, and podcasts to Obsidian."""
    pass


# === Pipeline Commands ===

@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be processed without doing it")
def run(dry_run: bool):
    """Run the content pipeline."""
    result = run_pipeline(dry_run=dry_run)
    click.echo(f"Processed: {result.processed}, Failed: {result.failed}")
    if result.retried:
        click.echo(f"Retried: {result.retried}")

@cli.command()
def status():
    """Show pipeline status: pending items, retry queue, last run."""
    db = Database(DB_PATH)
    feed_manager = FeedManager(db)

    # Last run info
    last_run = db.get_last_successful_run()
    if last_run:
        click.echo(f"Last successful run: {last_run.strftime('%Y-%m-%d %H:%M')}")
    else:
        click.echo("No previous runs")

    # Pending items
    new_entries = feed_manager.fetch_new_entries()
    click.echo(f"Pending items: {len(new_entries)}")

    # Retry queue
    retry_entries = db.get_retry_candidates()
    click.echo(f"In retry queue: {len(retry_entries)}")

    # Feed counts by category
    feeds = feed_manager.list_feeds()
    by_category = {}
    for f in feeds:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    click.echo(f"Feeds: {by_category}")


# === Feed Management Commands ===

@cli.group()
def feeds():
    """Manage feed subscriptions."""
    pass

@feeds.command("add")
@click.argument("url")
@click.option("--category", "-c", type=click.Choice(["articles", "youtube", "podcasts"]),
              help="Feed category (auto-detected if not specified)")
def feeds_add(url: str, category: str | None):
    """Add a new feed subscription."""
    db = Database(DB_PATH)
    feed_manager = FeedManager(db)

    feed = feed_manager.add_feed(url, category)
    click.echo(f"Added: {feed.title} ({feed.category})")

@feeds.command("remove")
@click.argument("url")
def feeds_remove(url: str):
    """Remove a feed subscription."""
    db = Database(DB_PATH)
    feed_manager = FeedManager(db)

    feed_manager.remove_feed(url)
    click.echo(f"Removed: {url}")

@feeds.command("list")
@click.option("--category", "-c", type=click.Choice(["articles", "youtube", "podcasts"]),
              help="Filter by category")
def feeds_list(category: str | None):
    """List all feed subscriptions."""
    db = Database(DB_PATH)
    feed_manager = FeedManager(db)

    feeds = feed_manager.list_feeds(category)
    for feed in feeds:
        click.echo(f"[{feed.category}] {feed.title}")
        click.echo(f"    {feed.url}")

@feeds.command("export")
@click.option("--output", "-o", default="exports/feeds.opml",
              help="Output file path (default: exports/feeds.opml)")
def feeds_export(output: str):
    """Export feeds to OPML format."""
    db = Database(DB_PATH)
    feed_manager = FeedManager(db)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    feed_manager.export_opml(output_path)
    click.echo(f"Exported to: {output_path}")

@feeds.command("import")
@click.argument("opml_file", type=click.Path(exists=True))
def feeds_import(opml_file: str):
    """Import feeds from OPML file."""
    db = Database(DB_PATH)
    feed_manager = FeedManager(db)

    count = feed_manager.import_opml(Path(opml_file))
    click.echo(f"Imported {count} feeds")


if __name__ == "__main__":
    cli()
```

---

## Configuration

### settings.yaml

```yaml
# Obsidian vault
obsidian:
  vault_path: "~/Obsidian/Professional vault"
  clippings_folder: "Clippings"
  youtube_folder: "Clippings/Youtube extractions"

# Processing settings
processing:
  article_timeout_seconds: 120
  youtube_timeout_seconds: 300
  podcast_timeout_seconds: 600

# Retry settings
retry:
  max_attempts: 4
  backoff_hours: [1, 4, 12, 24]  # Exponential backoff schedule

# Feed polling
feeds:
  request_timeout_seconds: 30
  user_agent: "ContentPipeline/1.0"
```

### .env.example

```bash
# No secrets required for basic operation
# Claude Code CLI handles its own authentication

# Optional: Override database location
# PIPELINE_DB_PATH=/custom/path/pipeline.db
```

### .gitignore

```
# Environment
.env
.venv/

# Runtime data
data/

# Logs
logs/*.log

# Python
__pycache__/
*.pyc
.pytest_cache/

# macOS
.DS_Store

# IDE
.idea/
.vscode/
```

**Note:** The `exports/` folder is NOT gitignored — OPML exports are committed for backup.

---

## Dependencies

### pyproject.toml

```toml
[project]
name = "content-pipeline"
version = "0.1.0"
description = "Automated content aggregation pipeline for Obsidian"
requires-python = ">=3.11"

dependencies = [
    "feedparser>=6.0",          # RSS/Atom feed parsing
    "httpx>=0.27",              # HTTP client for feed fetching
    "pyyaml>=6.0",              # Configuration files
    "click>=8.1",               # CLI framework
    "python-dotenv>=1.0",       # Environment variable loading
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
]

[project.scripts]
content-pipeline = "src.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Note:** No `anthropic` SDK needed — all Claude interactions go through Claude Code CLI.

---

## Scheduling (launchd + Wake)

### Wake Schedule

To ensure the iMac wakes before the scheduled run:

```bash
# Set wake schedule (run once during install)
sudo pmset repeat wake MTWRFSU 05:55:00
```

This wakes the machine at 5:55 AM daily, giving 5 minutes before the 6:00 AM pipeline run.

### templates/com.claude.content-pipeline.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.content-pipeline</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/jens.echterling/GitHub/Development/AI research assistant/scripts/run.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/jens.echterling/.claude/logs/content-pipeline.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/jens.echterling/.claude/logs/content-pipeline.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>/Users/jens.echterling</string>
    </dict>
</dict>
</plist>
```

### scripts/run.sh

```bash
#!/bin/bash
set -e

# Navigate to project directory
cd "/Users/jens.echterling/GitHub/Development/AI research assistant"

# Load environment variables (if any)
if [ -f .env ]; then
    source .env
fi

# Run pipeline (catch-up logic is built into the pipeline itself)
uv run content-pipeline run

# Export OPML and commit to GitHub (weekly backup)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq 1 ]; then  # Monday
    uv run content-pipeline feeds export
    git add exports/feeds.opml
    git diff --cached --quiet || git commit -m "Weekly OPML backup $(date +%Y-%m-%d)"
    git push
fi
```

### scripts/install.sh

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing content-pipeline..."

# Create directories
mkdir -p ~/.claude/logs
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/exports"

# Make scripts executable
chmod +x "$PROJECT_DIR/scripts/run.sh"
chmod +x "$PROJECT_DIR/scripts/uninstall.sh"

# Copy launchd plist
cp "$PROJECT_DIR/templates/com.claude.content-pipeline.plist" ~/Library/LaunchAgents/

# Load the job
launchctl load ~/Library/LaunchAgents/com.claude.content-pipeline.plist

# Set wake schedule (requires sudo)
echo "Setting wake schedule..."
sudo pmset repeat wake MTWRFSU 05:55:00

echo ""
echo "✓ Installed successfully!"
echo ""
echo "  Pipeline will run daily at 6:00 AM"
echo "  Machine will wake at 5:55 AM"
echo ""
echo "  Manual run:   cd $PROJECT_DIR && uv run content-pipeline run"
echo "  Check status: cd $PROJECT_DIR && uv run content-pipeline status"
echo "  View logs:    tail -f ~/.claude/logs/content-pipeline.log"
```

### scripts/uninstall.sh

```bash
#!/bin/bash
set -e

echo "Uninstalling content-pipeline..."

# Unload launchd job
launchctl unload ~/Library/LaunchAgents/com.claude.content-pipeline.plist 2>/dev/null || true

# Remove plist
rm -f ~/Library/LaunchAgents/com.claude.content-pipeline.plist

# Optionally remove wake schedule
read -p "Remove wake schedule? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo pmset repeat cancel
    echo "Wake schedule removed"
fi

echo "✓ Uninstalled"
```

---

## Initial Feed Subscriptions

Add these feeds after setup using the CLI:

```bash
# Articles
content-pipeline feeds add "https://www.lennysnewsletter.com/feed" -c articles
content-pipeline feeds add "https://stratechery.com/feed/" -c articles
content-pipeline feeds add "https://review.firstround.com/feed.xml" -c articles
content-pipeline feeds add "https://www.nfx.com/feed" -c articles
content-pipeline feeds add "https://caseyaccidental.com/feed/" -c articles
content-pipeline feeds add "https://oneusefulthing.substack.com/feed" -c articles
content-pipeline feeds add "https://www.recruitingbrainfood.com/feed/" -c articles
content-pipeline feeds add "https://www.reforge.com/blog/rss.xml" -c articles
content-pipeline feeds add "https://newsletter.pragmaticengineer.com/feed" -c articles
```

### Category: youtube

Find channel IDs and construct feed URLs:
```bash
# Format: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
content-pipeline feeds add "https://www.youtube.com/feeds/videos.xml?channel_id=UC..." -c youtube
```

### Category: podcasts

Add podcast RSS feeds as discovered:
```bash
content-pipeline feeds add "https://podcast-rss-url.com/feed" -c podcasts
```

---

## Implementation Phases

### Phase 1: Project Setup + Database

1. Create repo structure at `/Users/jens.echterling/GitHub/Development/AI research assistant/`
2. Set up `pyproject.toml` with dependencies
3. Implement `src/database.py` with SQLite schema
4. Write `.env.example`
5. Initialize database with `uv run python -c "from src.database import Database; Database('data/pipeline.db')"`

**Verification:** `data/pipeline.db` exists with correct tables.

### Phase 2: Feed Manager + CLI

1. Implement `src/feed_manager.py` with feedparser integration
2. Implement CLI in `src/main.py` with feed management commands
3. Test feed operations:
   - `uv run content-pipeline feeds add "https://stratechery.com/feed/" -c articles`
   - `uv run content-pipeline feeds list`
   - `uv run content-pipeline feeds export`
4. Add 3-5 test feeds

**Verification:** Feeds stored in database, OPML export works.

### Phase 3: Article Skill

1. Create `skills/article/SKILL.md` (quick reference)
2. Create `skills/article/article-workflow.md` (detailed workflow)
3. Reference existing skills at `/Users/jens.echterling/GitHub/Productivity/Skills/obsidian-workflow-skills/skills/` for patterns
4. Install skill to Claude Code (symlink or copy to skill location)
5. Test manually: `/article https://stratechery.com/some-article/`
6. Verify note created in Clippings with correct format

**Verification:** Article note appears with frontmatter, "For HeyJobs"/"For Me Personally" suggestions, and content in collapsed callout.

### Phase 4: Skill Runner + Basic Pipeline

1. Implement `src/skill_runner.py` with CLI invocation
2. Implement basic `src/pipeline.py` that:
   - Fetches new entries
   - Invokes skills
   - Verifies output
   - Marks as processed
3. Test: `uv run content-pipeline run --dry-run`
4. Test: `uv run content-pipeline run` with single article

**Verification:** Article processed via /article skill, marked as processed in database.

### Phase 5: YouTube + Podcast Integration

1. Add YouTube feed: `content-pipeline feeds add "https://www.youtube.com/feeds/..." -c youtube`
2. Test `/youtube` skill delegation
3. Add podcast feed (if available)
4. Test full pipeline with mixed content types

**Verification:** All content types process correctly, notes appear in correct locations.

### Phase 6: Retry Queue + Catch-up

1. Implement retry queue logic in `src/database.py`
2. Add catch-up check to pipeline
3. Implement `add_to_retry_queue` with exponential backoff
4. Test failure handling (e.g., invalid URL)
5. Test retry on subsequent runs

**Verification:** Failed items appear in retry queue, get retried with backoff.

### Phase 7: Post-Processing + Notifications

1. Add `/evaluate-knowledge` trigger with file list
2. Implement `src/notifications.py` with success/failure stats
3. Test notification content

**Verification:** Notification shows processed count and any failures.

### Phase 8: Automation + Documentation

1. Create `scripts/run.sh` with weekly OPML backup
2. Create `scripts/install.sh` with wake schedule
3. Create `scripts/uninstall.sh`
4. Create launchd plist
5. Install and test scheduled execution
6. Write README.md with setup instructions
7. Push to GitHub

**Verification:** Pipeline runs at 6 AM, machine wakes, OPML committed weekly.

---

## Open Design Decisions

These can be decided during implementation:

1. **Article content storage:** Include full original text in notes (good for search) or just summary (lighter)?
   - Recommendation: Include full text in a collapsed callout section

2. **Skill installation location:** Where does the `/article` skill live?
   - Option A: In this repo's `skills/` folder, symlinked to Claude Code skill location
   - Option B: Directly in Claude Code's skill directory
   - Decide based on Claude Code's skill loading mechanism

3. **Daily digest:** Generate a summary note linking all new items?
   - Skip for v1, add later if wanted

## Future Improvements

Track these for post-MVP iterations:

1. **Parallel processing** — Process multiple items concurrently for faster runs
2. **JavaScript-rendered content** — Use Playwright for SPAs that don't work with readability
3. **Duplicate detection** — Hash-based detection across feeds to prevent duplicate notes
4. **1Password integration** — Automated login for paywalled content
5. **Manual override controls** — Skip specific items, re-prioritize queue

---

## Testing Strategy

### Unit Tests

- `test_database.py`: Schema creation, CRUD operations, retry logic
- `test_feed_manager.py`: Feed parsing, OPML import/export
- `test_skill_runner.py`: Mock subprocess calls, output verification

### Integration Tests

- Test feed fetching with real RSS feeds
- Test skill delegation (requires Claude Code available)
- Test end-to-end pipeline with single item

### Manual Testing Checklist

- [ ] Database initializes with correct schema
- [ ] `feeds add` stores feed with auto-detected title
- [ ] `feeds list` shows all feeds by category
- [ ] `feeds export` creates valid OPML
- [ ] `--dry-run` shows items without processing
- [ ] `/article` skill creates note with correct format
- [ ] `/youtube` skill delegated → note in Youtube extractions
- [ ] `/podcast` skill delegated → note in Clippings
- [ ] Items marked as processed after note verified
- [ ] Failed items added to retry queue
- [ ] Retry queue items processed on subsequent run
- [ ] `/evaluate-knowledge` receives list of new files only
- [ ] Notification shows success count and failures
- [ ] launchd job triggers at scheduled time
- [ ] Machine wakes at 5:55 AM
- [ ] Weekly OPML export committed to GitHub

---

## Reference: Existing Infrastructure

### Existing Skills Repository
```
/Users/jens.echterling/GitHub/Productivity/Skills/obsidian-workflow-skills/
```

**Use as pattern reference for `/article` skill:**
- `skills/youtube/SKILL.md` + `youtube-workflow.md`
- `skills/podcast/SKILL.md` + `podcast-workflow.md`

**Reusable patterns:**
- Interest profile loading: `obsidian:read_note path="interest-profile.md"`
- Suggestion sections: "For HeyJobs" + "For Me Personally"
- Chunked reading with bash (head/sed/tail)
- Error handling structure
- Common mistakes table

### Obsidian Vault Location
```
~/Obsidian/Professional vault/
```

### Existing Clippings Format

See any file in `Clippings/` for reference. Key frontmatter fields:
- `title`
- `source`
- `author` (as wikilink)
- `published`
- `created`
- `description`
- `tags`

### Existing Skills

- `/youtube` — Extracts transcript, generates summary, writes to `Clippings/Youtube extractions/`
- `/podcast` — Extracts transcript, generates analysis, writes to Clippings
- `/evaluate-knowledge` — Evaluates notes against `interest-profile.md`, organizes and tags

### Interest Profile Location
```
~/Obsidian/Professional vault/interest-profile.md
```

Use this for personalizing article summaries in the `/article` skill.

### Claude Code CLI

The pipeline uses Claude Code CLI for all content processing:

```bash
# Basic invocation
claude --print "/skill-name argument"

# With auto-confirm for automated contexts
claude --print --dangerously-skip-permissions "/skill-name argument"
```

---

*Document created: 2026-01-25*
*Updated: 2026-01-25*
*For: Claude Code implementation*
