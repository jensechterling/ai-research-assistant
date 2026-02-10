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

## Input

**Required:** Podcast URL or RSS feed URL as argument
```
/podcast https://podcasts.apple.com/us/podcast/episode-name/id123456789
/podcast https://open.spotify.com/episode/EPISODE_ID
/podcast https://feeds.simplecast.com/feed_url.rss
```

**Optional:** Add context or specific questions after the URL
```
/podcast https://podcasts.apple.com/... What are the key product insights?
```

## Vault Configuration

**Vault Root:** Your Obsidian vault (accessed via MCP)
**Interest Profile:** `{{ profile.interest_profile }}`
**Output Folder:** `{{ folders.podcast }}/`

## Dependencies

**Optional (for advanced RSS parsing):**
```bash
# Only needed if basic curl/parsing doesn't work
pip3 install feedparser
```

**No other dependencies required** - uses existing transcripts only.

## Workflow

### 1. Extract Episode URL and Metadata

Parse the podcast URL to identify the platform and episode:

**Supported platforms:**
- Apple Podcasts: `https://podcasts.apple.com/...`
- Spotify: `https://open.spotify.com/episode/...`
- Direct RSS feed URLs
- Podcast websites with transcript pages

### 2. Fetch Episode Metadata and Transcript URL

**For RSS feeds:**

```bash
curl -s "RSS_FEED_URL" > /tmp/podcast_feed.xml

python3 << 'PARSE_EOF'
import xml.etree.ElementTree as ET
import re

tree = ET.parse('/tmp/podcast_feed.xml')
root = tree.getroot()
channel = root.find('channel')

# Podcast metadata
podcast_title = channel.find('title').text
podcast_description = channel.find('description').text

# Find the most recent episode (or search by title/date)
item = channel.find('item')

ep_title = item.find('title').text
ep_description = item.find('description').text if item.find('description') is not None else ""
pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""

# Find duration
duration_elem = item.find('.//{http://www.itunes.com/dtds/podcast-1.0.dtd}duration')
duration = duration_elem.text if duration_elem is not None else "Unknown"

# Find audio URL
enclosure = item.find('enclosure')
audio_url = enclosure.attrib['url'] if enclosure is not None else ""

# Look for transcript URLs in various formats
transcript_url = None

# Check for podcast:transcript tag (Podcast Namespace)
transcript_elem = item.find('.//{https://podcastindex.org/namespace/1.0}transcript')
if transcript_elem is not None:
    transcript_url = transcript_elem.attrib.get('url')

# Check for content:encoded (common for show notes with transcript links)
content_elem = item.find('.//{http://purl.org/rss/1.0/modules/content/}encoded')
if content_elem is not None and not transcript_url:
    # Look for transcript links in HTML content
    content = content_elem.text
    # Search for common transcript URL patterns
    match = re.search(r'href=["\']([^"\']*transcript[^"\']*)["\']', content, re.IGNORECASE)
    if match:
        transcript_url = match.group(1)

# Check description for transcript links
if not transcript_url and ep_description:
    match = re.search(r'https?://[^\s<>"]+transcript[^\s<>"]*', ep_description, re.IGNORECASE)
    if match:
        transcript_url = match.group(0)

print(f"Podcast: {podcast_title}")
print(f"Episode: {ep_title}")
print(f"Published: {pub_date}")
print(f"Duration: {duration}")
print(f"Audio URL: {audio_url}")
print(f"Transcript URL: {transcript_url if transcript_url else 'NOT FOUND'}")

# Save metadata for later use
with open('/tmp/podcast_metadata.txt', 'w') as f:
    f.write(f"podcast_title={podcast_title}\n")
    f.write(f"episode_title={ep_title}\n")
    f.write(f"pub_date={pub_date}\n")
    f.write(f"duration={duration}\n")
    f.write(f"audio_url={audio_url}\n")
    f.write(f"transcript_url={transcript_url if transcript_url else ''}\n")
    f.write(f"description={ep_description}\n")

PARSE_EOF
```

**For Apple Podcasts:**

Apple Podcasts episodes may have transcripts accessible via their web interface. Extract the podcast ID and episode ID from the URL, then:

```bash
# Apple Podcasts URL format: https://podcasts.apple.com/us/podcast/name/id123456789?i=1000...
PODCAST_ID=$(echo "$URL" | grep -oP 'id\K[0-9]+')
EPISODE_ID=$(echo "$URL" | grep -oP 'i=\K[0-9]+')

# Try to fetch episode page and look for transcript
curl -s "https://podcasts.apple.com/us/podcast/id${PODCAST_ID}?i=${EPISODE_ID}" | \
  grep -i transcript || echo "No transcript found on Apple Podcasts page"

# Note: Apple Podcasts transcripts may require web scraping or API access
# Many Apple Podcasts also publish RSS feeds - try that first
```

**For Spotify:**

Spotify has started adding transcripts to episodes. Check the episode page:

```bash
# Spotify URL format: https://open.spotify.com/episode/EPISODE_ID
EPISODE_ID=$(echo "$URL" | grep -oP 'episode/\K[a-zA-Z0-9]+')

# Note: Spotify transcripts are not easily accessible via API
# Recommend finding the podcast's RSS feed instead
echo "Spotify episode detected. Please provide the podcast's RSS feed URL for transcript access."
echo "Most podcasts publish RSS feeds on their website."
```

### 3. Fetch Transcript

Once transcript URL is found:

```bash
TRANSCRIPT_URL="url_from_above"

# Download transcript
curl -s "$TRANSCRIPT_URL" > /tmp/podcast_transcript.txt

# Check if it's HTML, VTT, SRT, or plain text
file /tmp/podcast_transcript.txt | grep -q HTML && IS_HTML=true || IS_HTML=false

if [ "$IS_HTML" = true ]; then
  # Extract text from HTML (remove tags)
  python3 << 'HTML_PARSE'
from html.parser import HTMLParser
import sys

class TranscriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())

    def get_text(self):
        return '\n'.join(self.text)

with open('/tmp/podcast_transcript.txt', 'r') as f:
    content = f.read()

parser = TranscriptParser()
parser.feed(content)
text = parser.get_text()

with open('/tmp/podcast_transcript_clean.txt', 'w') as f:
    f.write(text)

print(f"Extracted {len(text)} characters from HTML transcript")
HTML_PARSE
else
  # Already plain text or needs VTT/SRT parsing
  cp /tmp/podcast_transcript.txt /tmp/podcast_transcript_clean.txt
fi
```

**If transcript is in VTT or SRT format:**

```bash
python3 << 'VTT_PARSE'
import re

with open('/tmp/podcast_transcript.txt', 'r') as f:
    content = f.read()

# Parse VTT or SRT format
lines = content.split('\n')
transcript = []
current_time = None

for line in lines:
    # VTT timestamp: 00:00:00.000 --> 00:00:05.000
    # SRT timestamp: 00:00:00,000 --> 00:00:05,000
    time_match = re.match(r'(\d{2}:\d{2}:\d{2})[.,]\d{3}\s*-->', line)
    if time_match:
        current_time = time_match.group(1)
    elif line.strip() and current_time:
        # Skip WEBVTT header and numbers
        if not line.startswith('WEBVTT') and not line.isdigit():
            # Convert HH:MM:SS to [MM:SS] format
            parts = current_time.split(':')
            mins = int(parts[0])*60 + int(parts[1])
            secs = int(parts[2])
            transcript.append(f"[{mins:02d}:{secs:02d}] {line.strip()}")

# If no timestamps found, just use plain text
if not transcript:
    transcript = [line.strip() for line in lines if line.strip() and not line.startswith('WEBVTT')]

with open('/tmp/podcast_transcript_clean.txt', 'w') as f:
    f.write('\n'.join(transcript))

print(f"Parsed {len(transcript)} lines from transcript")
VTT_PARSE
```

### 4. Verify Transcript Exists

```bash
if [ ! -s /tmp/podcast_transcript_clean.txt ]; then
    echo "ERROR: No transcript found for this episode"
    exit 1
fi

wc -l /tmp/podcast_transcript_clean.txt
```

### 5. Reading Long Transcripts

**Strategy by line count:**

| Lines | Duration | Strategy |
|-------|----------|----------|
| < 500 | < 20 min | Single read |
| 500-1000 | 20-40 min | Two chunks |
| 1000-1500 | 40-60 min | Three chunks |
| > 1500 | > 60 min | Four+ chunks, summary mode |

**Use Bash commands for reading** (never Read tool):

```bash
# Check length
wc -l /tmp/podcast_transcript_clean.txt

# First chunk
head -500 /tmp/podcast_transcript_clean.txt

# Middle chunk
sed -n '500,1000p' /tmp/podcast_transcript_clean.txt

# Last chunk
tail -500 /tmp/podcast_transcript_clean.txt
```

### 6. Load Work Context

Before analysis, load context:

```
obsidian:read_note path="{{ profile.interest_profile }}"
```

### 7. Generate Analysis

Based on transcript and work context, generate:

#### Management Summary (2-3 paragraphs)
- Main topic and purpose of the episode
- Key message or thesis
- Host/guest background and credibility
- Target audience and value proposition

#### Key Findings (5-10 bullet points)
- Most important insights
- Actionable takeaways
- Notable quotes or claims
- Counterintuitive or contrarian ideas

#### Suggestions

**For Work** (3-5 bullets):
Connect episode insights to the user's role and priorities from `{{ profile.interest_profile }}`. Consider how the content applies to their:
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
- How the episode relates to user's specific interests
- Direct answers to any questions asked

#### Timeline with Key Moments

| Time | Topic | Key Content |
|------|-------|-------------|
| [00:00] | Introduction | Brief description |
| [15:30] | Main Discussion | Key points covered |

Create timestamps every 5-10 minutes or at major topic transitions (if transcript has timestamps).

### 8. Save to Obsidian

**Output Path:** `{{ folders.podcast }}/{Sanitized Title}.md`

Sanitize title: remove special characters, replace spaces with hyphens, truncate to 80 chars.

#### File Structure

```markdown
---
created: YYYY-MM-DD
tags: [type/reference, area/learning, status/inbox, podcast]
source: {Podcast URL}
podcast: {Podcast Name}
episode: {Episode Title}
---

# {Episode Title}

## Metadata
- **Podcast:** {podcast name}
- **Episode:** {episode title}
- **Duration:** {duration}
- **Published:** {formatted date}
- **Host/Guest:** {names}
- **URL:** {full URL}

## Management Summary

{2-3 paragraph summary of episode content, main thesis, and value}

## Key Findings

- {finding 1}
- {finding 2}
- {finding 3}
...

## Suggestions

### For Work
- {suggestion connecting insight to product strategy/growth}
- {suggestion for team/product organization}
- {suggestion for AI/analytics priorities}

### For Personal Life
- {personal learning or leadership suggestion}
- {PKM or productivity application}
- {tool, technique, or trend to explore}

## Relevance to Your Questions

{Only include if user provided specific questions or context}

## Episode Timeline

| Time | Topic | Key Content |
|------|-------|-------------|
| [00:00] | {topic} | {brief description} |
...

## Transcript

{For episodes < 60 min: Full transcript with timestamps if available}
{For episodes > 60 min: "Full transcript available on request" or key sections only}
```

## Duration-Based Processing Strategy

| Duration | Lines (approx) | Approach |
|----------|----------------|----------|
| < 20 min | < 500 | **Standard**: Full transcript, detailed analysis |
| 20-40 min | 500-1000 | **Chunked**: Read in 2 parts, full output |
| 40-60 min | 1000-2000 | **Chunked**: Read in 3-4 parts, full output |
| > 60 min | > 2000 | **Summary mode**: Timeline + key sections only |

**For episodes > 60 min**, inform user:
> "This is a long episode (X minutes). I've created a summary with timeline. Full transcript can be added if needed."

## Common Transcript Sources

### Podcast Namespace (RSS)
The modern standard for podcast transcripts:
```xml
<podcast:transcript url="https://example.com/transcript.txt" type="text/plain" />
<podcast:transcript url="https://example.com/transcript.vtt" type="text/vtt" />
<podcast:transcript url="https://example.com/transcript.srt" type="application/x-subrip" />
```

### Show Notes / Description
Many podcasts include transcript links in episode descriptions:
- Look for "Transcript:" or "Read the transcript:" in description
- Common patterns: `https://podcast.com/episodes/123/transcript`

### Podcast Websites
Most professional podcasts host transcripts on their website:
- Pattern: `https://podcast-website.com/episodes/episode-name-transcript`
- Try appending `/transcript` to episode URL
- Check show notes for "Transcript" links

### Third-Party Services
Some podcasts use transcript services:
- Otter.ai transcripts
- Rev.com transcripts
- Descript transcripts
- Usually linked in show notes

## Important Rules

1. **Always check for transcript first** – Don't attempt to download audio
2. **Try multiple sources** – RSS feed, show notes, website
3. **Handle missing transcripts gracefully** – Clear error message with suggestions
4. **Sanitize filenames** – Remove special characters from titles
5. **Create folder structure** – Ensure `{{ folders.podcast }}/` exists
6. **NEVER use Read tool on transcripts** – Always use head/sed/tail via Bash
7. **Load interest profile** – Always read {{ profile.interest_profile }} before analysis
8. **Use Obsidian MCP** – Write output using `obsidian:write_note` tool
9. **Clean up temp files** – Delete downloaded transcripts after processing
10. **Support multiple transcript formats** – Plain text, VTT, SRT, HTML

## Error Handling

**No transcript found in RSS feed:**
```
No transcript found for this episode.

This episode does not provide a transcript in the RSS feed.

Options:
1. Check the podcast's website for a transcript page
2. Try a different episode (many podcasts only transcribe recent episodes)
3. Provide a direct transcript URL if you know it

Note: This skill only works with existing transcripts.
If the podcast doesn't provide transcripts, this episode cannot be analyzed.
```

**Invalid RSS feed:**
```
Could not parse RSS feed.

Please check:
- URL is correct and publicly accessible
- RSS feed is properly formatted XML
- Feed is not behind authentication

Try:
- Using the podcast's official RSS feed URL
- Checking the podcast website for the RSS feed link
```

**Transcript URL found but inaccessible:**
```
Found transcript URL but could not download it.

Transcript URL: {url}

Possible issues:
- Transcript requires authentication
- URL is broken or moved
- Network/connectivity issues

Try:
- Opening the URL in your browser to verify it works
- Checking if you need to be logged in
- Using a different episode
```

**Empty transcript:**
```
Downloaded transcript is empty.

This could mean:
- Transcript file is malformed
- URL points to wrong file
- Transcript is not yet available

Try:
- Using a different episode
- Checking the podcast website directly
```

**HTML transcript with no text:**
```
Transcript appears to be HTML but contains no readable text.

This could mean:
- Transcript requires JavaScript to load
- Page structure is complex
- Transcript is behind a paywall

Try:
- Copying the transcript text manually and providing it
- Using a different source for this episode
```

## Platform-Specific Notes

### Apple Podcasts
- Many Apple Podcasts include transcripts in their RSS feeds
- Check the podcast's original RSS feed (linked on Apple Podcasts page)
- Transcripts may be on the podcast's website

### Spotify
- Spotify displays transcripts but doesn't provide easy API access
- **Best approach**: Find the podcast's RSS feed from their website
- Most podcasts publish to multiple platforms with the same RSS feed

### RSS Feeds (Recommended)
- Most reliable method for transcript access
- Modern podcasts use Podcast Namespace `<podcast:transcript>` tag
- Older podcasts may link transcripts in show notes
- Check both `<description>` and `<content:encoded>` tags

### Podcast Websites
- Many podcasts host transcripts on their website
- Common patterns:
  - `podcast.com/episodes/123/transcript`
  - `podcast.com/transcripts/episode-name`
  - `podcast.com/episodes/123` (transcript on same page)

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Episode has no transcript | Not all podcasts provide transcripts; try different episode or podcast |
| Using Spotify URL directly | Find podcast's RSS feed instead for transcript access |
| Reading large transcript with Read tool | Always use head/sed/tail via Bash to avoid token limits |
| Missing {{ profile.interest_profile }} | Create profile in vault root first for personalized suggestions |
| Invalid RSS feed URL | Verify URL is publicly accessible and properly formatted |

## Example Usage

```
/podcast https://feeds.simplecast.com/54nAGcIl
```

```
/podcast https://podcasts.apple.com/us/podcast/lenny-podcast/id1627920305
```

```
/podcast https://feeds.transistor.fm/lenny-podcast What does this say about product prioritization?
```

## Finding Podcast RSS Feeds

If you have a Spotify or Apple Podcasts URL but need the RSS feed:

1. **Find podcast website** – Google the podcast name
2. **Look for RSS icon** – Usually in footer or "Subscribe" section
3. **Check podcast directories**:
   - Podcast Index: podcastindex.org
   - Listen Notes: listennotes.com
4. **Use browser tools** – View page source, search for "RSS" or ".xml"

Most professional podcasts publish RSS feeds for distribution.

