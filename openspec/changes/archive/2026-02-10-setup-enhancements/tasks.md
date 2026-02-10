## 1. Interest Profile Linking

- [x] 1.1 Add interest profile prompt to first-time setup flow in `src/setup.py`: ask "existing profile or create from template?", validate file exists if linking, save path to config
- [x] 1.2 Update `_copy_interest_profile()` to respect the config path — skip copying template when user linked an existing file
- [x] 1.3 Add tests for profile linking logic (link existing, create template, file-not-found re-prompt, upgrade mode skips)

## 2. Cross-Platform Scheduling

- [x] 2.1 Create `templates/crontab-entry.j2` with comment marker, schedule variables, and log redirect
- [x] 2.2 Add `_install_cron()` function in `src/setup.py`: read existing crontab, replace or append entry, write back via `crontab -`
- [x] 2.3 Refactor `--install-schedule` block in `setup()` to branch on `sys.platform`: `darwin` → launchd (existing), `linux` → `_install_cron()`, else → print manual instructions
- [x] 2.4 Add tests for platform detection branching and cron entry rendering

## 3. Documentation

- [x] 3.1 Update README scheduling section: add Linux (cron) instructions, add Windows (manual Task Scheduler) guidance
- [x] 3.2 Update CHANGELOG with setup-enhancements entry
