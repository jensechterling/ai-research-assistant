## ADDED Requirements

### Requirement: Pipeline mutual exclusion
The system SHALL prevent concurrent pipeline runs using a file-based lock.

#### Scenario: First run acquires lock
- **WHEN** `ai-research-assistant run` is invoked and no other pipeline run is in progress
- **THEN** the pipeline acquires the lock, writes its PID to `data/pipeline.lock`, and proceeds normally

#### Scenario: Second run blocked by lock
- **WHEN** `ai-research-assistant run` is invoked while another pipeline run holds the lock
- **THEN** the command SHALL exit immediately with a non-zero exit code and print a message including the PID of the holding process

#### Scenario: Lock released on completion
- **WHEN** the pipeline run completes (success or failure)
- **THEN** the lock SHALL be released automatically

#### Scenario: Lock released on crash
- **WHEN** the pipeline process is killed or crashes
- **THEN** the OS SHALL release the `fcntl.flock()` lock automatically

#### Scenario: Dry run does not acquire lock
- **WHEN** `ai-research-assistant run --dry-run` is invoked
- **THEN** the pipeline SHALL NOT acquire the lock

### Requirement: Force override
The system SHALL provide a `--force` flag to bypass the pipeline lock.

#### Scenario: Force flag overrides lock
- **WHEN** `ai-research-assistant run --force` is invoked while another run holds the lock
- **THEN** the pipeline SHALL log a warning and proceed without acquiring the lock

#### Scenario: Force flag without existing lock
- **WHEN** `ai-research-assistant run --force` is invoked with no lock held
- **THEN** the pipeline SHALL proceed normally (acquires lock as usual)
