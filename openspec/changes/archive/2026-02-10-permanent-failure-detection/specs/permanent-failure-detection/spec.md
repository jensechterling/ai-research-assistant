## ADDED Requirements

### Requirement: Detect permanent failures from skill output
When a skill completes without producing a note path, the system SHALL check the skill's stdout against a list of known permanent failure patterns (case-insensitive). If any pattern matches, the failure SHALL be classified as permanent.

#### Scenario: Paywall detected in skill output
- **WHEN** a skill returns exit code 0 but output contains "behind a paywall" and no note path is found
- **THEN** the `SkillResult.permanent` flag SHALL be `True` and the error message SHALL indicate the content is behind a paywall

#### Scenario: No permanent pattern matched
- **WHEN** a skill returns exit code 0 but no note path is found and output does not match any permanent failure pattern
- **THEN** the `SkillResult.permanent` flag SHALL be `False` and the error message SHALL indicate no note path was found

#### Scenario: Skill exits with non-zero code
- **WHEN** a skill exits with a non-zero return code
- **THEN** permanent failure detection SHALL NOT be applied (the failure is treated as transient)

### Requirement: Skip retry queue for permanent failures
When the pipeline encounters a permanent failure, it SHALL NOT add the entry to the retry queue. The entry SHALL be logged and counted separately from transient failures.

#### Scenario: Permanent failure skips retry queue
- **WHEN** `SkillResult.permanent` is `True`
- **THEN** the pipeline SHALL NOT call `add_to_retry_queue()` for that entry
- **AND** the pipeline SHALL log a warning with `[PERMANENT]` prefix including the entry title and error

#### Scenario: Transient failure still retries
- **WHEN** `SkillResult.permanent` is `False` and `SkillResult.success` is `False`
- **THEN** the pipeline SHALL add the entry to the retry queue as before

### Requirement: Track permanent failure count in PipelineResult
`PipelineResult` SHALL include a `permanent_failures` counter to distinguish permanent failures from transient ones in the `failed` count.

#### Scenario: Permanent failures counted separately
- **WHEN** the pipeline finishes processing entries with 2 permanent failures and 1 transient failure
- **THEN** `PipelineResult.permanent_failures` SHALL be 2 and `PipelineResult.failed` SHALL be 1

### Requirement: Notification includes permanent failure information
When permanent failures occur, the macOS notification SHALL include the permanent failure count in the message.

#### Scenario: Notification with permanent failures
- **WHEN** the pipeline completes with 3 processed, 1 failed, and 2 permanent failures
- **THEN** the notification message SHALL mention the permanent failure count (e.g., "2 skipped (paywall)")
