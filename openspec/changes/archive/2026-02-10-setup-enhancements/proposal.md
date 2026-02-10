## Why

The setup wizard assumes every user starts fresh with no interest profile and only supports macOS for scheduled runs. Users who already have a profile in their vault (possibly with a different name or location) cannot link it during setup — they must manually edit `config/user.yaml`. And Linux users have no automated scheduling option at all, even though cron is universally available.

## What Changes

- **Interest profile linking**: Setup asks whether the user has an existing interest profile and lets them provide its vault-relative path. If they do, that path is saved to config. If they don't, the template is copied as before.
- **Cross-platform scheduling**: Add cron support for Linux via `--install-schedule`. The flag auto-detects the platform and uses launchd (macOS) or crontab (Linux). Windows users get a clear message with manual Task Scheduler instructions.
- **README update**: Document scheduling for all three platforms.

## Capabilities

### New Capabilities
- `cross-platform-scheduling`: Platform-aware `--install-schedule` flag supporting launchd (macOS) and cron (Linux), with documentation for Windows manual setup.

### Modified Capabilities
- `setup-wizard`: The interest profile step gains an "existing profile" flow. The `--install-schedule` flag becomes platform-aware instead of macOS-only.

## Impact

- `src/setup.py`: Modified — interest profile prompt logic, platform detection, cron installation
- `templates/crontab-entry.j2`: New — cron schedule template
- `README.md`: Updated — scheduling section expanded for Linux/Windows
- `config/defaults.yaml`: No changes (profile path config key already exists)
- Tests: New tests for profile linking logic and platform detection
