# content-extraction Specification

## Purpose
Turns an article feed entry into the title, metadata and main text needed for analysis, using deterministic code rather than an LLM, and says whether a failure is worth retrying.

## Requirements

### Requirement: Article text extraction
For an `articles` entry the system SHALL download the entry URL, with a timeout of `feeds.request_timeout` seconds and the `feeds.user_agent` header, and extract the main text, title, author, publication date and site name.

#### Scenario: Readable article
- **WHEN** the page returns HTTP 200 with at least `extraction.min_words` words of main text
- **THEN** extraction succeeds with the page text and its metadata

#### Scenario: Metadata missing from page
- **WHEN** the page has no detectable author or date
- **THEN** extraction succeeds and uses the feed entry's author and published date, or leaves them empty if the entry has none

### Requirement: Full feed text stored with each entry
When the system reads a feed, it SHALL store the item's full content (`content:encoded` or Atom `content`) as the entry content when present, and the item summary otherwise.

#### Scenario: Full-text feed
- **WHEN** a feed item has both a 40-word summary and a 1,200-word `content:encoded`
- **THEN** the entry content is the 1,200-word text

### Requirement: Fallback to feed text
When the downloaded page yields fewer than `extraction.min_words` words or the download fails, the system SHALL use the entry's feed content if that has at least `extraction.min_words` words.

#### Scenario: Blocked page rescued by feed text
- **WHEN** the page returns HTTP 403 and the entry content has 1,200 words
- **THEN** extraction succeeds using the feed content and records that the text came from the feed

#### Scenario: Retry entry no longer in the feed
- **WHEN** an entry from the retry queue is no longer in its feed and so has no content
- **THEN** extraction uses the downloaded page only

### Requirement: Input size bound
The system SHALL cap the extracted text at `extraction.max_words` words, and SHALL record when text was cut.

#### Scenario: Very long article
- **WHEN** an article has 45,000 words and `extraction.max_words` is 30,000
- **THEN** analysis and the note receive the first 30,000 words and the result is marked as truncated

### Requirement: Bounded page download
A page download SHALL finish within 90 seconds in total and SHALL NOT read more than 10 MB, however slowly the server sends data. A page whose content type is neither `text/*` nor `application/xhtml+xml` SHALL NOT be read as a page. Exceeding the deadline is transient; an oversized or non-HTML page is permanent unless the feed text is usable.

#### Scenario: Server trickles bytes
- **WHEN** a server keeps sending one byte every few seconds
- **THEN** the download is abandoned after 90 seconds and the entry is treated as a transient failure

#### Scenario: Link points at a PDF
- **WHEN** an entry's link returns `application/pdf` and the feed has no usable text
- **THEN** the entry is a permanent failure naming the content type

### Requirement: Extraction failure classification
Every extraction failure SHALL be classified as permanent (retrying cannot help) or transient (a later attempt may succeed).

#### Scenario: Paywall or blocked page with no usable feed text
- **WHEN** the page returns HTTP 401, 402, 403, 404, 410 or 451, or fewer than `extraction.min_words` words, and the feed content is also below that threshold
- **THEN** the failure is permanent with the reason "not extractable"

#### Scenario: Short post
- **WHEN** a link post has 60 words on the page and 60 words in the feed, and `extraction.min_words` is 150
- **THEN** the failure is permanent with the reason "not extractable"

#### Scenario: Network or server problem
- **WHEN** the request times out, the connection fails, or the server returns HTTP 429 or 5xx, and the feed content is below `extraction.min_words`
- **THEN** the failure is transient
