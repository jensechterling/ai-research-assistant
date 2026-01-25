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
