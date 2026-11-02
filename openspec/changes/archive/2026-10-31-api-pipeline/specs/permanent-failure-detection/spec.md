# Spec Delta

## ADDED Requirements

### Requirement: Detect permanent failures from extraction
The system SHALL classify a failure as permanent only when the content-extraction step reports it as permanent. Analysis and vault-output failures SHALL never be permanent.

#### Scenario: Paywalled article
- **WHEN** extraction reports a permanent "not extractable" failure
- **THEN** the processing result is marked permanent and its error message gives the extraction reason

#### Scenario: Analysis failure is not permanent
- **WHEN** extraction succeeds but analysis fails
- **THEN** the processing result is not marked permanent

### Requirement: Permanent failures are not attempted again
A permanently failed entry SHALL be recorded as processed with no note path, so later runs skip it.

#### Scenario: Paywalled article on the next day
- **WHEN** an entry failed permanently yesterday and is still in its feed today
- **THEN** today's run does not extract it again and does not count it again

## MODIFIED Requirements

### Requirement: Skip retry queue for permanent failures
When the pipeline encounters a permanent failure, it SHALL NOT add the entry to the retry queue. The entry SHALL be logged and counted separately from transient failures.

#### Scenario: Permanent failure skips retry queue
- **WHEN** the processing result for an entry is marked permanent
- **THEN** the pipeline SHALL NOT call `add_to_retry_queue()` for that entry
- **AND** the pipeline SHALL log a warning with `[PERMANENT]` prefix including the entry title and error

#### Scenario: Permanent failure on a retry entry
- **WHEN** an entry from the retry queue fails permanently
- **THEN** it is removed from the retry queue and recorded as processed with no note path

#### Scenario: Transient failure still retries
- **WHEN** the processing result for an entry is a failure that is not marked permanent
- **THEN** the pipeline SHALL add the entry to the retry queue as before

### Requirement: Notification includes permanent failure information
When permanent failures occur, the macOS notification SHALL include the permanent failure count in the message.

#### Scenario: Notification with permanent failures
- **WHEN** the pipeline completes with 3 processed, 1 failed, and 2 permanent failures
- **THEN** the notification message SHALL mention the permanent failure count as "2 skipped (not extractable)"

## REMOVED Requirements

### Requirement: Detect permanent failures from skill output
**Reason**: The pipeline no longer runs skills, so there is no skill stdout to match phrases against. Permanent failures are now decided by the extraction step from HTTP status and extracted word count.
**Migration**: None for users. The phrase list in `src/skill_runner.py` is deleted together with that module.
