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
```
/article https://stratechery.com/article-name
```

**Optional:** Add context or specific questions after the URL
```
/article https://stratechery.com/article-name What does this say about AI strategy?
```

## Vault Configuration

**Vault Root:** Your Obsidian vault (accessed via MCP)
**Interest Profile:** `interest-profile.md`
**Output Folder:** `Clippings/`

## Workflow

### 1. Extract Article Content

Use WebFetch tool to retrieve and parse the article:

```
WebFetch URL with prompt: "Extract the full article content including title, author, publication date, and body text. Return as structured text."
```

**Fallback for complex pages:** If WebFetch fails, try trafilatura via Python:

```bash
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
```

### 2. Load Work Context

Before generating analysis, load context for personalized suggestions:

```
obsidian:read_note path="interest-profile.md"
```

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
Connect article insights to the user's role and priorities from `interest-profile.md`. Consider how the content applies to their:
- Current role and responsibilities (CPO at jobs marketplace)
- Product strategy and growth challenges
- AI/ML applications and analytics
- Team and organizational leadership
- Monetization and business models

**For Me Personally** (3-5 bullets):
Connect to the user's personal interests from `interest-profile.md`. Consider applications for:
- Personal development and learning
- PKM and productivity systems
- Hobbies and side projects
- Tools and techniques to explore

#### Relevance Section (if user provided questions)
- How the article relates to user's specific interests
- Direct answers to any questions asked

### 4. Auto-Generate Source Slug

Generate tag-friendly slug from URL domain:

```python
from urllib.parse import urlparse
domain = urlparse(url).netloc
domain = domain.removeprefix("www.")
name = domain.rsplit(".", 1)[0]
slug = name.replace(".", "-").replace("_", "-").lower()
```

Examples:
- `www.lennysnewsletter.com` → `lennysnewsletter`
- `stratechery.com` → `stratechery`
- `review.firstround.com` → `review-firstround`
- `oneusefulthing.substack.com` → `oneusefulthing-substack`

### 5. Save to Obsidian

**Output Path:** `Clippings/{Sanitized Title}.md`

Sanitize title: remove special characters, replace spaces with hyphens, truncate to 80 chars.

#### File Structure

```markdown
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
```

## Content Length Strategy

| Word Count | Approach |
|------------|----------|
| < 2000 | **Standard**: Full analysis, complete text in callout |
| 2000-5000 | **Standard**: Full analysis, complete text in callout |
| > 5000 | **Summary mode**: Analysis + key excerpts only |

## Important Rules

1. **Always load interest profile** – Read `interest-profile.md` before analysis
2. **Handle extraction failures gracefully** – Clear error message with suggestions
3. **Sanitize filenames** – Remove `/ \ : * ? " < > |` from titles
4. **Create folder structure** – Ensure `Clippings/` exists
5. **Use Obsidian MCP** – Write output using `obsidian:write_note` tool
6. **Include full text** – Store in collapsed callout for search
7. **Auto-generate source slug** – Don't rely on manual mapping

## Error Handling

**Paywalled content:**
```
This article appears to be behind a paywall.

Extracted what was available:
- Title: {title}
- Excerpt: {available excerpt}

Options:
1. If you have access, copy/paste the article text
2. Check if there's an RSS feed with full content
3. Skip this article
```

**JavaScript-rendered page:**
```
Could not extract article content (page may require JavaScript).

Options:
1. Try a different URL for the same article
2. Copy/paste the article text manually
3. Use a reader-mode URL if available
```

**Network error:**
```
Could not access article URL.

Please check:
- URL is correct and publicly accessible
- No network connectivity issues
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Paywalled content | Falls back to excerpt; inform user |
| Missing interest-profile.md | Create profile in vault root first |
| JavaScript-rendered pages | Note limitation; suggest alternatives |
| Very long articles | Use summary mode for >5000 words |

## Example Usage

```
/article https://stratechery.com/2024/some-article-name
```

```
/article https://www.lennysnewsletter.com/p/article-title What are the key product insights?
```

## Dependencies

- **Obsidian MCP** – For reading/writing notes to vault
- **WebFetch tool** – For article extraction (built into Claude Code)
- **trafilatura** (optional) – Fallback for complex pages: `pip3 install trafilatura`
