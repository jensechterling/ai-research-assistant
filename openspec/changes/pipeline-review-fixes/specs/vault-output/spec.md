# Spec Delta

## ADDED Requirements

### Requirement: Existing note for the same source
Before an entry is analyzed, the system SHALL look for a note anywhere in the vault, outside hidden folders, whose frontmatter `source` equals the entry URL. If one exists, the entry SHALL be recorded as processed with that note's path, with no analysis, no new or changed note, and no Daily Dose or evaluation-log change.

#### Scenario: Article already clipped by hand
- **WHEN** the user clipped an article into `2 Know-how/Product/` with `source: https://example.com/a` and annotated it, and a feed later delivers `https://example.com/a` under a new guid
- **THEN** the entry is recorded as processed with the path of the clipped note, the clipped note is unchanged, and no model call is made

#### Scenario: Same URL in two feeds
- **WHEN** the pipeline filed a note for `https://example.com/a` yesterday and a second feed delivers the same URL today
- **THEN** today's entry is recorded as processed with yesterday's note and nothing is written

## MODIFIED Requirements

### Requirement: File naming
The filename SHALL be the title with the characters `/ \ : * ? " < > | # [ ] ^` removed, spaces replaced by hyphens, cut to 80 characters, plus `.md`. The name SHALL be unique across the vault, because links to the note use the bare filename.

#### Scenario: Same title, different source
- **WHEN** a note with the same filename exists in the target folder and its `source` differs from the entry URL
- **THEN** the new note is written as `<name>-2.md`, or the next free number

#### Scenario: Same source already written
- **WHEN** a note whose `source` equals the entry URL exists anywhere in the vault
- **THEN** no note is written or replaced, as set out in "Existing note for the same source"

#### Scenario: Same title in another folder
- **WHEN** `Weekly-Roundup.md` exists in `2 Know-how/AI/` and a new note titled `Weekly Roundup` is filed in `2 Know-how/Leadership/`
- **THEN** the new note is written as `2 Know-how/Leadership/Weekly-Roundup-2.md`, and its Daily Dose entry and evaluation-log row link `[[Weekly-Roundup-2|Weekly Roundup]]`

### Requirement: Daily Dose entry
After a note is written, the system SHALL add an entry under the "Daily Dose of Know-How" heading of today's daily note (`folders.daily_notes/YYYY-MM-DD.md`). The entry gives the note link, the target folder, the takeaway and the action. Heading matching SHALL ignore case and heading level. The section SHALL end at the next heading of any level, and only empty `-` lines inside that section SHALL be removed. An entry SHALL NOT be added if today's section already links the same note.

#### Scenario: Entry format
- **WHEN** the note `Agent Evals` is filed in `2 Know-how/AI & ML/`
- **THEN** the daily note gains `- [[Agent-Evals|Agent Evals]] → *2 Know-how/AI & ML/*` followed by indented `**Takeaway:**` and `**Action:**` lines

#### Scenario: Daily note missing
- **WHEN** today's daily note does not exist
- **THEN** it is created from `folders.templates/Daily Note.md`, with Templater expressions of the form `<% tp.date.now("FORMAT") %>` or `<% tp.date.now("FORMAT", N) %>` replaced by today's date shifted by N days, in that format

#### Scenario: Previous and next day links
- **WHEN** the template contains `<% tp.date.now("YYYY-MM-DD", -1) %>` and `<% tp.date.now("YYYY-MM-DD", 1) %>` and today is 2026-11-02
- **THEN** the daily note contains `2026-11-01` and `2026-11-03` in their places

#### Scenario: Day and month tokens
- **WHEN** the template contains `<% tp.date.now("dddd, MMMM Do YYYY") %>` or `<% tp.date.now("D.M.YYYY") %>` and today is 2026-11-02
- **THEN** the daily note contains `Monday, November 2nd 2026` or `2.11.2026`

#### Scenario: Heading missing
- **WHEN** the daily note has no matching heading
- **THEN** `## Daily Dose of Know-How` is appended at the end of the note, with the entry under it

### Requirement: Evaluation log row
After a note is written, the system SHALL add a row to the table in `folders.knowledge_base/evaluation-log.md`, or replace the row that already links that note. The row gives the note link, today's date, the folder and the takeaway. "Last updated" SHALL be set to today and "Total evaluated" to the number of table rows. The "Aggregated Patterns" section SHALL be left unchanged.

#### Scenario: Pipe character in takeaway
- **WHEN** the takeaway contains `|`
- **THEN** it is escaped so the table row stays valid

#### Scenario: Note replaced
- **WHEN** the log already has a row linking `[[Agent-Evals\|...]]` and the note `Agent-Evals.md` is written
- **THEN** that row is updated and the row count does not change

#### Scenario: Log missing
- **WHEN** `evaluation-log.md` does not exist
- **THEN** it is created with the standard header and the first row
