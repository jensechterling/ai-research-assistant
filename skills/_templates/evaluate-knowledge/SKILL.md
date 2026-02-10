---
name: evaluate-knowledge
description: Use when reviewing knowledge notes for personalized takeaways, processing a folder of notes, or organizing the Clippings inbox
---

# Evaluate Knowledge

## Overview

Transforms passive knowledge into actionable insights by evaluating notes against your interest profile, generating personalized suggestions for work and personal life, and organizing clippings into your knowledge base.

## When to Use

- Reviewing a note and want personalized takeaways
- Processing new additions to your knowledge base
- Finding patterns across a folder of notes
- Refreshing stale evaluations after note updates
- Processing Clippings inbox (auto-organizes, tags, and moves to knowledge base)

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| Single note | `/evaluate-knowledge [[Note Name]]` | Evaluates one note |
| Folder (recursive) | `/evaluate-knowledge {{ folders.knowledge_base }}/Product/` | All .md files in folder and subfolders |
| Process Clippings | `/evaluate-knowledge {{ folders.clippings }}/` | Organizes, moves, tags, then evaluates |
| Force re-evaluate | `/evaluate-knowledge {{ folders.knowledge_base }}/ --force` | Ignores timestamps, re-evaluates all |

## Core Pattern

```
1. Load {{ profile.interest_profile }} from vault root
2. For each note in scope:
   - Skip if evaluated >= modified (unless --force)
   - Skip if < 100 words
   - If in {{ folders.clippings }}/: organize first (move + tag)
   - Generate evaluation (adaptive sizing)
   - Append to note + update frontmatter
   - Add entry to daily note (Daily Dose of Know-How)
3. Update evaluation-log.md (add/update entry for each evaluated note)
```

## Implementation

### Input Parsing

| Input | Interpretation |
|-------|----------------|
| `[[Note Name]]` | Single note in vault |
| `folder/path/` | All .md files recursively (including all subfolders) |
| `--force` | Ignore timestamps, re-evaluate all |

**Important:** Folder processing ALWAYS includes all subfolders. For example, `{{ folders.clippings }}/` processes both `{{ folders.clippings }}/*.md` AND `{{ folders.youtube }}/*.md`.

### Interest Profile

Read `{{ profile.interest_profile }}` from vault root. Extract:
- **Work section**: Role, priorities, professional interests
- **Private section**: Personal interests, life context

### Evaluation Output

Append to each note:

```markdown
---

## Evaluation

*Evaluated: YYYY-MM-DD*

### For Work
- [Suggestions connecting to work priorities]

### For Personal
- [Suggestions for personal life application]
```

Update frontmatter: `evaluated: YYYY-MM-DD`

### Adaptive Sizing

| Source length | Bullets per section |
|---------------|---------------------|
| < 500 words | 5-8 (full) |
| 500-1500 words | 3-5 (standard) |
| > 1500 words | 2-3 (condensed) |

### Evaluation Log (Always Updated)

Update `{{ folders.knowledge_base }}/evaluation-log.md` after **every** evaluation (single or batch):

**If log doesn't exist:** Create it with header and first entry.

**If log exists:**
- Add new entry to table (or update if note already listed)
- Re-analyze patterns section based on all entries

```markdown
# Knowledge Evaluation Log

Last updated: YYYY-MM-DD
Total evaluated: N notes

## Aggregated Patterns

### [Theme Name]
- [[Note]] - Key insight

## All Evaluations

| Note | Evaluated | Category | Key Insight |
|------|-----------|----------|-------------|
| [[Note path]] | 2026-01-18 | Leadership | One-line insight |
```

Group notes by detected themes (2+ notes sharing a pattern).

### Daily Dose of Know-How

After evaluating each note, append a summary to today's daily note.

**Daily note path:** `{{ folders.daily_notes }}/YYYY-MM-DD.md` (today's date)

**If daily note doesn't exist:**
1. Read template from `{{ folders.templates }}/Daily Note.md`
2. Create daily note with template content
3. Replace any date placeholders (e.g., `{{date}}`) with today's date

**If section doesn't exist:** Add `## Daily Dose of Know-How` section at the end of the note.

**Entry format** (append under the section):

```markdown
- [[Note Title]] → *{{ folders.knowledge_base }}/Product/AI & ML/*
  - **Takeaway:** One-line key insight from the evaluation
  - **Action:** Specific suggestion for applying this knowledge
```

**Field definitions:**

| Field | Source | Example |
|-------|--------|---------|
| Note Title | Wikilink to processed note | `[[How to give feedback]]` |
| Destination | Folder path where note was filed | `{{ folders.knowledge_base }}/Leadership/` |
| Takeaway | Most important insight (from evaluation) | "Feedback should be specific and timely" |
| Action | One actionable suggestion (from For Work or For Personal) | "Try the SBI framework in next 1:1" |

**Example daily note section:**

```markdown
## Daily Dose of Know-How

- [[How to give feedback]] → *{{ folders.knowledge_base }}/Leadership/*
  - **Takeaway:** The SBI (Situation-Behavior-Impact) framework makes feedback specific and actionable
  - **Action:** Use SBI format in your next 1:1 when discussing the delayed project delivery

- [[AI Product Strategy 2024]] → *{{ folders.knowledge_base }}/Product/AI & ML/*
  - **Takeaway:** AI features should solve existing user problems, not showcase technology
  - **Action:** Review your team's AI roadmap for features that might be "tech-first" vs "problem-first"
```

### Skip Conditions

- `evaluated >= modified` (already current)
- Word count < 100 (stubs)
- Filename starts with `_` (drafts)
- Frontmatter has `status: template`

### Clippings Inbox Processing

When note is in `{{ folders.clippings }}/` or any subfolder:

1. **Analyze content** → determine best-fit folder in `{{ folders.knowledge_base }}/`
2. **Add tags** → max 5 relevant tags to frontmatter properties
3. **Move note** → to target folder (delete from {{ folders.clippings }})
4. **Continue** → with normal evaluation

**Target folders**: List existing subfolders in `{{ folders.knowledge_base }}/` using Obsidian MCP and pick the best-fit folder for each note. If no good fit exists, create a new subfolder with a descriptive name.

**Tag format:** Frontmatter properties
```yaml
tags:
  - leadership
  - feedback
  - management
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Running on entire vault | Scope to `{{ folders.knowledge_base }}/` or specific subfolder |
| Missing {{ profile.interest_profile }} | Create profile in vault root first |
| Evaluating templates | Add `status: template` to frontmatter |
| Daily note not created | Skill creates from template; ensure `{{ folders.templates }}/Daily Note.md` exists |

## Dependencies

- **Obsidian MCP** - read/write notes
- **{{ profile.interest_profile }}** - in vault root with Work/Private sections
- **Daily Notes folder** - `{{ folders.daily_notes }}/` with date-named files (YYYY-MM-DD.md)
- **Daily note template** - `{{ folders.templates }}/Daily Note.md` (used when creating new daily notes)
