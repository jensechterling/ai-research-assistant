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

## Input

**Required:** YouTube URL as argument
```
/youtube https://www.youtube.com/watch?v=VIDEO_ID
```

**Optional:** Add context or specific questions after the URL
```
/youtube https://www.youtube.com/watch?v=VIDEO_ID What does this say about product strategy?
```

## Vault Configuration

**Vault Root:** Your Obsidian vault (accessed via MCP)
**Interest Profile:** `{{ profile.interest_profile }}`
**Output Folder:** `{{ folders.youtube }}/`

## Workflow

### 1. Extract Video ID

Parse the YouTube URL to get video ID. Support formats:
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/watch?v=VIDEO_ID&t=123s`

### 2. Fetch Video Metadata

```bash
yt-dlp --dump-json --skip-download "URL" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'Title: {d[\"title\"]}')
print(f'Channel: {d[\"channel\"]}')
print(f'Duration: {d[\"duration\"]//60}:{d[\"duration\"]%60:02d}')
print(f'Upload Date: {d[\"upload_date\"]}')
print(f'Views: {d.get(\"view_count\",\"N/A\")}')
print(f'Description: {d.get(\"description\",\"N/A\")[:1000]}')
"
```

### 3. Download Transcript

```bash
yt-dlp --write-auto-sub --write-sub --sub-lang en --skip-download --sub-format vtt \
  -o "/tmp/yt_transcript_VIDEO_ID" "URL" 2>&1
```

### 4. Parse VTT to Clean Transcript

Convert the VTT file to clean text with **compact timestamps** (no URLs yet - those are added in the final output):

```bash
python3 << 'PARSE_EOF'
import re

VIDEO_ID = "VIDEO_ID"  # Replace with actual video ID
vtt_file = f'/tmp/yt_transcript_{VIDEO_ID}.en.vtt'
out_file = f'/tmp/yt_transcript_{VIDEO_ID}_clean.txt'

with open(vtt_file, 'r') as f:
    content = f.read()

# Parse VTT and extract unique lines with timestamps
lines = content.split('\n')
entries = []
current_time = None

for line in lines:
    time_match = re.match(r'(\d{2}:\d{2}:\d{2})\.\d{3} --> ', line)
    if time_match:
        current_time = time_match.group(1)
    elif line.strip() and current_time:
        clean_line = re.sub(r'<[^>]+>', '', line)
        clean_line = re.sub(r'align:start position:\d+%', '', clean_line).strip()
        if clean_line and not clean_line.startswith('WEBVTT') and not clean_line.startswith('Kind:') and not clean_line.startswith('Language:'):
            entries.append((current_time, clean_line))

# Deduplicate consecutive duplicates
merged = []
prev_text = ""
for time, text in entries:
    if text != prev_text:
        merged.append((time, text))
        prev_text = text

# Output COMPACT format (no URLs) - saves ~40 tokens per line
with open(out_file, 'w') as f:
    for time, text in merged:
        parts = time.split(':')
        mins = int(parts[0])*60 + int(parts[1])
        secs = int(parts[2])
        f.write(f"[{mins:02d}:{secs:02d}] {text}\n")

print(f"Wrote {len(merged)} lines to {out_file}")
PARSE_EOF
```

**Output format:** `[MM:SS] text` (compact, no URLs)

Example:
```
[00:00] At the beginning of my day, I literally
[00:02] just write today and we can see what it
[16:54] really enough for Claude to work with
```

### 4b. Reading Long Transcripts

**IMPORTANT:** The Read tool has a 25,000 token limit. Long videos (30+ min) will exceed this. Use bash commands instead:

```bash
# Check transcript length
wc -l /tmp/yt_transcript_VIDEO_ID_clean.txt
```

**Strategy by line count:**

| Lines | Duration | Strategy |
|-------|----------|----------|
| < 500 | < 15 min | Single `head -500` read |
| 500-1000 | 15-30 min | Two chunks: `head -500`, `tail -500` |
| 1000-1500 | 30-50 min | Three chunks: `head -500`, `sed -n '500,1000p'`, `tail -500` |
| > 1500 | > 50 min | Four+ chunks, consider summary-only mode |

**Chunked reading commands:**

```bash
# First chunk (lines 1-500)
head -500 /tmp/yt_transcript_VIDEO_ID_clean.txt

# Middle chunk (lines 500-1000)
sed -n '500,1000p' /tmp/yt_transcript_VIDEO_ID_clean.txt

# Last chunk (final 500 lines)
tail -500 /tmp/yt_transcript_VIDEO_ID_clean.txt
```

**NEVER use the Read tool directly on transcript files** – always use head/sed/tail via Bash to avoid token limits.

### 4c. Load Work Context

Before generating analysis, load context for personalized suggestions:

```
obsidian:read_note path="{{ profile.interest_profile }}"
```

**Key context to extract:**
- **Work section**: Role, company, team size, current priorities, professional interests
- **Private section**: Personal interests, life context, hobbies

### 5. Generate Analysis

Based on the transcript and work context, generate:

#### Management Summary (2-3 paragraphs)
- Main topic and purpose of the video
- Key message or thesis
- Target audience and value proposition

#### Key Findings (5-10 bullet points)
- Most important insights
- Actionable takeaways
- Notable quotes or claims

#### Suggestions

**For Work** (3-5 bullets):
Connect video insights to the user's role and priorities from `{{ profile.interest_profile }}`. Consider how the content applies to their:
- Current role and responsibilities
- Team and organizational challenges
- Professional interests and growth areas
- Industry-specific applications

**For Personal** (3-5 bullets):
Connect to the user's personal interests from `{{ profile.interest_profile }}`. Consider applications for:
- Personal development and learning
- Hobbies and side projects
- Life context (family, health, etc.)
- Tools and techniques to explore

#### Relevance Section (if user provided questions)
- How the video relates to user's specific interests
- Direct answers to any questions asked

#### Timeline with Jumpmarks
| Time | Topic | Key Content |
|------|-------|-------------|
| [00:00](url&t=0s) | Introduction | Brief description |
| [05:30](url&t=330s) | Main Topic | Key points covered |

Create timestamps every 3-5 minutes or at major topic transitions.

### 6. Save to Obsidian

**Output Path:** `{{ folders.youtube }}/{Sanitized Title}.md`

Sanitize title: remove special characters, replace spaces with hyphens, truncate to 80 chars.

#### 6a. Converting Compact Timestamps to Full Links

When writing the final transcript to Obsidian, convert compact `[MM:SS]` format to full clickable links.

**Conversion formula:**
- Input: `[MM:SS] text`
- Output: `[MM:SS](https://www.youtube.com/watch?v=VIDEO_ID&t=Xs) text`
- Where `X` = `MM * 60 + SS`

**Example conversions:**
- `[00:00]` → `[00:00](https://www.youtube.com/watch?v=VIDEO_ID&t=0s)`
- `[05:30]` → `[05:30](https://www.youtube.com/watch?v=VIDEO_ID&t=330s)`
- `[49:37]` → `[49:37](https://www.youtube.com/watch?v=VIDEO_ID&t=2977s)`

**For long videos (1000+ lines):** Default to summary + timeline only (per user preference). Include only key timestamps rather than full transcript.

#### 6b. File Structure

```markdown
---
created: YYYY-MM-DD
tags: [type/reference, area/learning, status/inbox]
source: {YouTube URL}
---

# {Video Title}

## Metadata
- **Channel:** {channel}
- **Duration:** {duration}
- **Published:** {formatted date}
- **Views:** {view count}
- **URL:** {full URL}

## Management Summary

{2-3 paragraph summary of the video content, main thesis, and value}

## Key Findings

- {finding 1}
- {finding 2}
- {finding 3}
...

## Suggestions

### For Work
- {suggestion connecting insight to product strategy/growth}
- {suggestion for team/product organization}
- {suggestion for AI/analytics/monetization priorities}

### For Personal Life
- {personal learning or leadership suggestion}
- {PKM or productivity application}
- {tool, technique, or trend to explore}

## Relevance to Your Questions

{Only include if user provided specific questions or context}

## Video Timeline

| Time | Topic | Key Content |
|------|-------|-------------|
| [00:00]({url}&t=0s) | {topic} | {brief description} |
...

## Complete Transcript

{For videos < 60 min: Full transcript with timestamp links}
{For videos > 60 min: "Full transcript available on request" or key sections only}
```

## Duration-Based Processing Strategy

**User Preference:** Default to summary mode for long videos (Option C)

| Duration | Lines (approx) | Approach |
|----------|----------------|----------|
| < 15 min | < 500 | **Standard**: Single-pass transcript, full detail |
| 15-30 min | 500-1000 | **Chunked**: Read in 2 parts, full transcript in output |
| 30-60 min | 1000-2000 | **Chunked**: Read in 3-4 parts, full transcript in output |
| > 60 min | > 2000 | **Summary mode**: Timeline + key sections only (compact) |

**For videos > 60 min**, inform user:
> "This is a long video (X minutes). I've created a summary with timeline. Full transcript can be added if needed."

## Important Rules

1. **Check yt-dlp installed** – If missing, prompt user to install: `brew install yt-dlp`
2. **Handle missing transcripts** – Some videos don't have captions; inform user
3. **Sanitize filenames** – Remove `/ \ : * ? " < > |` from titles
4. **Create folder structure** – Ensure `{{ folders.youtube }}/` exists
5. **Preserve timestamp links** – All timestamps should be clickable YouTube links
6. **Language fallback** – Try `en` first, then `en-US`, then any available
7. **NEVER use Read tool on transcript files** – Always use head/sed/tail via Bash
8. **Use compact format during analysis** – Only add full URLs when writing final output
9. **Load interest profile** – Always read `{{ profile.interest_profile }}`
10. **Use Obsidian MCP** – Write output using `obsidian:write_note` tool

## Error Handling

**No transcript available:**
```
This video doesn't have captions/subtitles available.
Options:
1. Try a different video
2. Use a third-party transcription service
3. Watch the video and take manual notes
```

**yt-dlp not installed:**
```
yt-dlp is required but not installed.
Install with: brew install yt-dlp
```

**Network/access error:**
```
Could not access video. Possible issues:
- Video is private or age-restricted
- Geographic restrictions
- Video was deleted
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing yt-dlp | Install with `brew install yt-dlp` before running |
| Video has no transcript | Check if captions exist; some videos don't have transcripts |
| Reading large transcript with Read tool | Always use head/sed/tail via Bash to avoid token limits |
| Missing {{ profile.interest_profile }} | Create profile in vault root first for personalized suggestions |
| Not handling long videos | Automatically uses summary mode for >60min videos |

## Example Usage

```
/youtube https://www.youtube.com/watch?v=uBJdwRPO1QE
```

```
/youtube https://www.youtube.com/watch?v=abc123 What does this say about product-led growth?
```

## Dependencies

- **yt-dlp** – Install via `brew install yt-dlp`
- **python3** – For parsing VTT files (pre-installed on macOS)
- **Obsidian MCP** – For reading/writing notes to vault

