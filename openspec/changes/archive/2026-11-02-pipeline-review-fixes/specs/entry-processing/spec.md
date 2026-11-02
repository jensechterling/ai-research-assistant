# Spec Delta

## MODIFIED Requirements

### Requirement: Per-entry processing order
For each entry the system SHALL first check for an existing note with the entry's URL as its source, then run extraction, then analysis, then vault output, and SHALL stop at the first step that fails. When an existing note is found, no later step SHALL run.

#### Scenario: Extraction fails
- **WHEN** extraction fails for an entry
- **THEN** no API request is made for that entry

#### Scenario: Note for the URL already exists
- **WHEN** a note whose `source` equals the entry URL already exists in the vault
- **THEN** the page is not downloaded and no API request is made for that entry

### Requirement: Success definition
An entry SHALL count as processed only when its note file exists at the path the vault writer returned. Its guid and note path SHALL then be stored as processed, and it SHALL be removed from the retry queue if it was there. An entry matched to an existing note SHALL be stored as processed with that note's path and removed from the retry queue, but SHALL NOT count as processed or retried in the run's totals.

#### Scenario: Successful retry
- **WHEN** an entry from the retry queue produces a note
- **THEN** it is marked processed, removed from the retry queue, and counted as retried

#### Scenario: Entry matched to an existing note
- **WHEN** a run finds 4 entries, 1 of which matches an existing note and 3 of which produce new notes
- **THEN** the notification reports "Processed 3", the run log names the matched entry and its note, and all 4 are stored as processed

### Requirement: Repeated analysis failures stop the run
When the first 3 entries of a run that reach analysis all fail at analysis, before any analysis has worked in that run, the system SHALL queue those 3 for retry as usual and then stop the run as a fatal error naming the last error. Failures at extraction SHALL NOT count, and an entry matched to an existing note SHALL NOT count as an analysis that worked.

#### Scenario: Config error rejected for every request
- **WHEN** Melious answers HTTP 400 for every analysis request and 20 entries are pending
- **THEN** 3 entries are queued for retry, 17 are left untouched, the run is recorded as `failed`, and the notification names the error

#### Scenario: Failures after a success
- **WHEN** the first analysis of the run succeeds and later ones fail
- **THEN** the run continues and the failed entries are queued as transient failures

#### Scenario: Existing-note match before failures
- **WHEN** the first entry of a run matches an existing note and the next 3 entries all fail at analysis
- **THEN** the run stops as a fatal error after the third failure
