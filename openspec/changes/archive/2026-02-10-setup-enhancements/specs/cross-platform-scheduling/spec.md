## ADDED Requirements

### Requirement: Cron-based scheduling on Linux
The system SHALL install a cron job when `--install-schedule` is used on Linux, using the configured schedule hour and minute.

#### Scenario: Install cron on Linux
- **WHEN** user runs `ai-research-assistant setup --install-schedule` on a Linux system
- **THEN** a crontab entry is added that runs `scripts/run.sh` at the configured schedule time, with output redirected to `~/.claude/logs/ai-research-assistant.log`

#### Scenario: Replace existing cron entry
- **WHEN** a cron entry with the `# ai-research-assistant` comment marker already exists
- **THEN** the existing entry is replaced with the updated schedule

#### Scenario: Preserve other cron entries
- **WHEN** user has existing crontab entries unrelated to ai-research-assistant
- **THEN** those entries SHALL remain unchanged after installation

### Requirement: Platform-aware schedule installation
The system SHALL detect the current platform and use the appropriate scheduling mechanism.

#### Scenario: macOS uses launchd
- **WHEN** `--install-schedule` is used on macOS (darwin)
- **THEN** a launchd plist is installed (existing behavior, unchanged)

#### Scenario: Linux uses cron
- **WHEN** `--install-schedule` is used on Linux
- **THEN** a crontab entry is installed

#### Scenario: Unsupported platform shows instructions
- **WHEN** `--install-schedule` is used on an unsupported platform (e.g., Windows)
- **THEN** the system SHALL print instructions for manual scheduling setup and NOT attempt automated installation

### Requirement: Cron entry template
The system SHALL render cron entries from a Jinja2 template using the same config variables as other infrastructure templates.

#### Scenario: Template renders with config values
- **WHEN** schedule is configured as hour=7, minute=30
- **THEN** the rendered cron entry contains `30 7 * * *`
