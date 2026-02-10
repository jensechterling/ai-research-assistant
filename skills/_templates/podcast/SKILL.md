---
name: podcast
description: Use when you have a podcast episode URL and want personalized insights, or need to find transcripts from RSS feeds
---

# Podcast Analysis

## Overview

Transforms podcast episodes into searchable Obsidian notes with personalized insights. Extracts existing transcripts from RSS feeds and podcast platforms, generates summaries connecting content to your work priorities, and creates searchable reference material.

**Note:** Only works with podcasts that provide existing transcripts.

## When to Use

- Analyzing product/business podcasts for strategic insights
- Extracting learnings from leadership or management episodes
- Processing industry trend discussions into knowledge base
- Building searchable reference from podcast content
- Need personalized suggestions connecting episode to work priorities
- Want to read transcripts instead of listening to full episodes

## Quick Reference

| Task | Command | Output |
|------|---------|--------|
| Analyze episode | `/podcast URL` | Full analysis with transcript |
| With questions | `/podcast URL What does this say about X?` | Analysis + relevance section |
| Long episode (>60min) | Automatic | Summary mode (timeline only) |

**Supported sources:** RSS feeds, Apple Podcasts (via RSS), Spotify (via RSS), podcast websites

**Output location:** `{{ folders.podcast }}/`

## Process Summary

1. Parse URL and fetch episode metadata
2. Extract transcript from RSS or website
3. Load {{ profile.interest_profile }} for context
4. Generate analysis (summary, findings, suggestions, timeline)
5. Save to Obsidian vault

**Transcript sources (in priority order):**
1. Podcast Namespace `<podcast:transcript>` tag (RSS)
2. Show notes/description links
3. Podcast website transcript pages
4. Third-party transcript services

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Episode has no transcript | Not all podcasts provide transcripts; try different episode or podcast |
| Using Spotify URL directly | Find podcast's RSS feed instead for transcript access |
| Reading large transcript with Read tool | Always use head/sed/tail via Bash to avoid token limits |
| Missing {{ profile.interest_profile }} | Create profile in vault root first for personalized suggestions |
| Invalid RSS feed URL | Verify URL is publicly accessible and properly formatted |

## Dependencies

- **python3** – For RSS/VTT parsing (pre-installed macOS)
- **curl** – For fetching feeds (pre-installed macOS)
- **Obsidian MCP** – For vault access
- **{{ profile.interest_profile }}** – In vault root

## Detailed Documentation

For complete workflow, platform-specific guides, and troubleshooting, see **podcast-workflow.md**.
