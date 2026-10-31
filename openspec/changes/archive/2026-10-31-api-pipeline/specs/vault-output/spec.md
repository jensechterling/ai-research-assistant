# Spec Delta

## Purpose

Writes each analyzed entry into the Obsidian vault as a filed knowledge-base note and records it in the daily note and the evaluation log. This replaces the scheduled `/evaluate-knowledge` pass.

## ADDED Requirements

### Requirement: Note content and layout
Each note SHALL contain frontmatter with `created`, `tags`, `source`, `author` and `evaluated`, followed in this order by: Metadata, Management Summary, Key Findings, Suggestions (with For Work and For Personal Life subsections), and the extracted text inside a collapsed `[!info]-` callout.

#### Scenario: Article note
- **WHEN** an article is analyzed successfully
- **THEN** the note has the frontmatter fields and sections above in that order, and `created` and `evaluated` are today's date

#### Scenario: Truncated text
- **WHEN** the extracted text was cut at `extraction.max_words`
- **THEN** the Metadata section states that the original text was truncated

### Requirement: Tags
The note's `tags` SHALL contain the analysis's topical tags (at most five, lower-case, hyphenated) plus `source/<slug>`. The slug SHALL be derived from the entry URL's domain.

#### Scenario: Source slug
- **WHEN** the entry URL is `https://www.lennysnewsletter.com/p/x`
- **THEN** the tags include `source/lennysnewsletter`

### Requirement: Filing into the knowledge base
The note SHALL be written into the top-level knowledge-base subfolder named by the analysis. Before matching, the name SHALL be trimmed, a leading knowledge-base folder prefix and trailing slashes removed, and it SHALL be compared case-insensitively with existing subfolders. A name matching no existing subfolder SHALL be created as a new subfolder.

#### Scenario: Existing folder
- **WHEN** `folders.knowledge_base` is `2 Know-how` and the analysis names `AI & ML`
- **THEN** the note is written to `2 Know-how/AI & ML/`

#### Scenario: Prefixed or differently cased name
- **WHEN** the analysis names `2 Know-how/ai & ml/`
- **THEN** the note is written to the existing `2 Know-how/AI & ML/`

#### Scenario: New folder
- **WHEN** the analysis names `Health Tech`, which does not exist
- **THEN** `2 Know-how/Health Tech/` is created and the note written there

#### Scenario: Unsafe folder name
- **WHEN** the normalised name still contains `/`, `\` or `..`, or is empty
- **THEN** the note is written to `folders.kb_fallback` inside the knowledge base, and nothing is written outside the knowledge base

### Requirement: File naming
The filename SHALL be the title with the characters `/ \ : * ? " < > | # [ ] ^` removed, spaces replaced by hyphens, cut to 80 characters, plus `.md`.

#### Scenario: Same title, different source
- **WHEN** a note with the same filename exists in the target folder and its `source` differs from the entry URL
- **THEN** the new note is written as `<name>-2.md`, or the next free number

#### Scenario: Same source already written
- **WHEN** a note with the same filename exists and its `source` equals the entry URL
- **THEN** that note is replaced

### Requirement: Note links
Links to a note in the daily note and the evaluation log SHALL use the note's filename without `.md`, with the title as display text: `[[<filename>|<title>]]`. Inside the evaluation-log table the `|` in the link SHALL be escaped as `\|`.

#### Scenario: Hyphenated filename
- **WHEN** the note `Agent Evals` is saved as `Agent-Evals.md`
- **THEN** the daily note links it as `[[Agent-Evals|Agent Evals]]` and the log as `[[Agent-Evals\|Agent Evals]]`

#### Scenario: Title with pipe or brackets
- **WHEN** the title is `Weekly | Roundup [[draft]]`
- **THEN** the display text is `Weekly - Roundup draft`, so the link and the log row keep their structure

### Requirement: Templater commands neutralised
Text from articles and from the model SHALL NOT be written to the vault as a Templater command: every `<%` in notes, Daily Dose entries and evaluation-log rows SHALL be written as `<\%`.

#### Scenario: Article contains a Templater command
- **WHEN** an article's text contains `<%* app.vault.delete() %>`
- **THEN** the note contains `<\%* app.vault.delete() %>`, which Templater does not run

### Requirement: Safe writes
Notes, daily notes and the evaluation log SHALL be written by creating a temporary file in the same folder and renaming it into place. A rewritten file SHALL keep its permissions; a new file SHALL be readable by others (mode 0644).

#### Scenario: Crash during write
- **WHEN** the process is killed while writing a note
- **THEN** the target path either does not exist or holds a complete previous version

### Requirement: Daily Dose entry
After a note is written, the system SHALL add an entry under the "Daily Dose of Know-How" heading of today's daily note (`folders.daily_notes/YYYY-MM-DD.md`). The entry gives the note link, the target folder, the takeaway and the action. Heading matching SHALL ignore case and heading level. The section SHALL end at the next heading of any level, and only empty `-` lines inside that section SHALL be removed. An entry SHALL NOT be added if today's section already links the same note.

#### Scenario: Entry format
- **WHEN** the note `Agent Evals` is filed in `2 Know-how/AI & ML/`
- **THEN** the daily note gains `- [[Agent-Evals|Agent Evals]] → *2 Know-how/AI & ML/*` followed by indented `**Takeaway:**` and `**Action:**` lines

#### Scenario: Daily note missing
- **WHEN** today's daily note does not exist
- **THEN** it is created from `folders.templates/Daily Note.md`, with Templater expressions of the form `<% tp.date.now("FORMAT") %>` replaced by today's date in that format

#### Scenario: Heading missing
- **WHEN** the daily note has no matching heading
- **THEN** `## Daily Dose of Know-How` is appended at the end of the note, with the entry under it

### Requirement: Evaluation log row
After a note is written, the system SHALL add a row to the table in `folders.knowledge_base/evaluation-log.md`, or replace the row that already links that note. The row gives the note link, today's date, the folder and the takeaway. "Last updated" SHALL be set to today and "Total evaluated" to the number of table rows. The "Aggregated Patterns" section SHALL be left unchanged.

#### Scenario: Pipe character in takeaway
- **WHEN** the takeaway contains `|`
- **THEN** it is escaped so the table row stays valid

#### Scenario: Note replaced
- **WHEN** a note with the same source is written again
- **THEN** its existing row is updated and the row count does not change

#### Scenario: Log missing
- **WHEN** `evaluation-log.md` does not exist
- **THEN** it is created with the standard header and the first row

### Requirement: Bookkeeping failures do not fail the entry
A failure to update the daily note or the evaluation log SHALL be logged as a warning and SHALL NOT change the entry's outcome once its note is written.

#### Scenario: Daily note not writable
- **WHEN** writing the daily note raises a permission error
- **THEN** the entry still counts as processed and the run log contains a warning
