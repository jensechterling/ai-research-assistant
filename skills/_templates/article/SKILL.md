---
name: article
description: Use when you have a blog post, newsletter article, or industry publication URL and want personalized insights connecting the content to your work priorities
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

**Output location:** `{{ folders.article }}/`

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Paywalled content | Falls back to RSS excerpt if available |
| Missing {{ profile.interest_profile }} | Create profile in vault root first for personalized suggestions |
| JavaScript-rendered pages | Some SPAs won't extract properly; note as limitation |

## Dependencies

- **Obsidian MCP** – For vault access
- **{{ profile.interest_profile }}** – In vault root

## Detailed Documentation

For complete workflow, code examples, and troubleshooting, see **article-workflow.md**.
