## Context

The setup wizard (`src/setup.py`) was introduced in v0.2.0. It handles first-time configuration (vault path, folder structure), template rendering, skill installation, and dependency checking. Two gaps were identified:

1. **Interest profile**: Setup copies a template to the vault but has no way to link to an existing profile file. The config key `profile.interest_profile` exists but is never exposed to the user during setup.
2. **Scheduling**: The `--install-schedule` flag only supports macOS launchd. Linux users (cron) and Windows users (Task Scheduler) have no automated option.

## Goals / Non-Goals

**Goals:**
- Let users link an existing interest profile during setup instead of always copying a template
- Support cron-based scheduling on Linux via the same `--install-schedule` flag
- Provide clear documentation for Windows users to set up scheduling manually

**Non-Goals:**
- Windows Task Scheduler automation (too many permission variants; manual docs are sufficient)
- Supporting profile formats other than `.md` in the vault root or subfolders
- Changing the scheduling approach for macOS (launchd stays as-is)

## Decisions

### D1: Interest profile flow — prompt during first-time setup only

During first-time setup (no `config/user.yaml`), after folder configuration, ask:

```
Do you have an existing interest profile in your vault?
  [1] No, create one from template (default)
  [2] Yes, link an existing file
```

If "Yes": prompt for the vault-relative path (e.g., `About Me.md`), validate the file exists, save to `profile.interest_profile` in `user.yaml`.

If "No": copy template as before.

In upgrade mode (existing config), skip this prompt entirely — the profile config is already set.

**Why not auto-detect?** A vault may have hundreds of `.md` files. Asking the user is simpler and more reliable than scanning for candidate profiles.

### D2: Platform detection via `sys.platform`

Use `sys.platform` to branch:
- `darwin` → launchd (existing code, no changes)
- `linux` → cron via `crontab` command
- anything else → print instructions for manual setup

**Why `sys.platform` over `platform.system()`?** It's already available without imports and is the standard approach in Python. `darwin`/`linux` covers the two platforms we support.

### D3: Cron installation via `crontab -l` / `crontab -`

Read existing crontab, check if our entry already exists (by comment marker), append or replace, write back. The entry uses the same `scripts/run.sh` that launchd uses.

Cron entry template (`templates/crontab-entry.j2`):
```
# ai-research-assistant scheduled run
{{ minute }} {{ hour }} * * * {{ project_dir }}/scripts/run.sh >> {{ home_dir }}/.claude/logs/ai-research-assistant.log 2>&1
```

Uninstall: not needed for v1 — users can remove the line manually. Document in README.

### D4: No changes to config structure

The existing `schedule.hour` and `schedule.minute` config keys are sufficient. The `profile.interest_profile` key already exists. No new config keys needed.

## Risks / Trade-offs

- **Cron environment differences** → `scripts/run.sh` already handles PATH and `uv` location; cron inherits minimal environment but the script is self-contained. Low risk.
- **Profile path validation** → We validate the file exists at setup time, but the user could move/rename it later. Acceptable — skills will fail with a clear error if the profile is missing at runtime.
- **Crontab manipulation** → Reading/writing crontab is well-understood but could theoretically conflict with other entries. Using a comment marker (`# ai-research-assistant`) to identify our entry minimizes this risk.
