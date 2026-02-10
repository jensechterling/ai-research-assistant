---
name: youtube
description: Use when you have a YouTube video URL and want personalized insights connecting the content to your work priorities
---

# YouTube Video Analysis

## Overview

Transforms YouTube videos into searchable, analyzable Obsidian notes with personalized suggestions. Extracts transcripts, generates summaries connecting insights to your work priorities, and creates clickable timelines for easy reference.

## When to Use

- Analyzing conference talks or product videos for insights
- Extracting key learnings from technical tutorials
- Processing educational content into knowledge base
- Building searchable reference library from videos
- Need personalized suggestions connecting video to work priorities
- Want to save time by reading transcripts instead of watching

## Quick Reference

| Task | Command | Output |
|------|---------|--------|
| Basic analysis | `/youtube URL` | Full analysis with transcript |
| With questions | `/youtube URL What does this say about X?` | Analysis + relevance section |
| Long video (>60min) | Automatic | Summary mode (timeline only) |

**Output location:** `{{ folders.youtube }}/`

## Process Summary

1. Extract video ID from URL
2. Download transcript using yt-dlp
3. Load {{ profile.interest_profile }} for context
4. Generate analysis (summary, findings, suggestions, timeline)
5. Save to Obsidian vault

**Duration-based strategy:**
- < 15min: Full transcript
- 15-60min: Full transcript (chunked reading)
- > 60min: Summary + timeline only

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing yt-dlp | Install with `brew install yt-dlp` before running |
| Video has no transcript | Check if captions exist; some videos don't have transcripts |
| Reading large transcript with Read tool | Always use head/sed/tail via Bash to avoid token limits |
| Missing {{ profile.interest_profile }} | Create profile in vault root first for personalized suggestions |
| Not handling long videos | Automatically uses summary mode for >60min videos |

## Dependencies

- **yt-dlp** – `brew install yt-dlp`
- **python3** – For VTT parsing (pre-installed macOS)
- **Obsidian MCP** – For vault access
- **{{ profile.interest_profile }}** – In vault root

## Detailed Documentation

For complete workflow, code examples, and troubleshooting, see **youtube-workflow.md**.
