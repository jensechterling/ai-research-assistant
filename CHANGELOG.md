# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

The scheduled pipeline no longer runs Claude Code. It extracts articles in Python and analyzes each one with a single call to Melious.

### Added

- **Melious analysis** — one JSON-mode request per article to `deepseek-v4.1-flash`, validated against a schema, with one repair request for invalid replies and a retry with a larger token budget for cut-off replies
- **Article extraction** — trafilatura on the downloaded page, falling back to the feed's full text, which is now stored for each entry
- **Direct filing** — notes go straight into the best-fitting knowledge-base folder, with a Daily Dose entry and an evaluation-log row
- **Run limits** — stale-entry filter (14 days), run time limit (60 minutes) and cost ceiling (EUR 2.00), with cost per article and per run in the log and notification
- **Setup key check** — setup tests the Melious key and model with one small request
- **`scripts/probe_melious.py`** — records Melious API behaviour

### Changed

- **BREAKING:** the scheduled pipeline processes `articles` feeds only; YouTube and podcast feeds are skipped (the manual skills still handle them)
- **BREAKING:** a Melious API key is required (`MELIOUS_API_KEY` in `.env`, or the Keychain)
- Permanent failures are decided by the extraction step (HTTP status, word count) instead of phrases in skill output, and are recorded so they are not tried again
- Account-level API errors and a missing profile stop the run instead of failing every entry
- Three analysis failures in a row at the start of a run stop it, so an outage or config error does not use up every entry's retry attempts
- An unexpected crash shows a "Run stopped" notification
- The notification passes its text to `osascript` as arguments
- The Monday OPML backup moved to `scripts/backup_feeds.sh` and only commits and pushes on `master`

### Fixed

- An entry that was both new and in the retry queue was processed twice per run
- Entries still in their feed ignored their retry backoff and were attempted every run
- Entries dropped by the retry queue came back as new and started over
- Failed runs were recorded as completed
- Feed downloads had no timeout
- Downloads could hang a run when a server sent data very slowly: feeds and pages now have a total deadline and a size cap, and links to PDFs or other non-HTML files are not read as pages
- A `|` or `]]` in a title broke the evaluation-log table and the note link
- Templater commands (`<%`) in article or model text are neutralised before they reach the vault
- Rewritten vault files kept the temporary file's owner-only permissions

### Removed

- `src/skill_runner.py` and the headless `/evaluate-knowledge` post-step
- `config/mcp-minimal.json` and the `npx` dependency check

## [0.3.0] - 2026-02-10

Repository made public and hardened for open-source visibility.

### Added

- **Pipeline lock** — prevents concurrent pipeline runs using `fcntl.flock()`; second invocation exits with clear error message and PID of holding process
- **`--force` flag** — `ai-research-assistant run --force` bypasses the lock when needed
- **Permanent failure detection** — paywalled and inaccessible content is detected via pattern matching on skill output, skipping the retry queue with a `[PERMANENT]` log prefix and paywall count in notifications
- **SECURITY.md** — vulnerability reporting policy
- **Contributing policy** — README section clarifying this is a personal project

### Changed

- **Repository made public** — open for viewing and forking
- **Project renamed** to `ai-research-assistant` (dropped `-for-obsidian` suffix)
- **GitHub settings** — issues, wiki, and projects disabled; branch protection enabled; topics added for discoverability

## [0.2.0] - 2026-02-10

First shareable release. Skills merged into this repository and the project generalized so anyone with an Obsidian vault and Claude Code can use it.

### Added

- **Setup wizard** (`ai-research-assistant setup`) — interactive first-time setup and silent upgrade mode
- **Interest profile linking** — setup wizard asks whether to create a new profile or link an existing file in the vault
- **Cross-platform scheduling** — `--install-schedule` supports cron on Linux in addition to launchd on macOS; other platforms get manual setup instructions
- **Configuration system** — layered YAML config (`config/defaults.yaml` + `config/user.yaml`) with deep merge
- **Jinja2 skill templates** — skills stored as templates in `skills/_templates/`, rendered during setup with user config
- **Infrastructure templates** — MCP config, run script, and launchd plist generated from templates
- **Interest profile template** — shipped template copied to vault during setup
- **Dependency checker** — setup verifies `claude`, `yt-dlp`, and `npx` are installed
- **Upgrade flow** — `git pull && uv sync && ai-research-assistant setup` re-renders all templates from existing config

### Changed

- **Skills bundled** — article, youtube, podcast, and evaluate-knowledge skills now live in this repo (previously in separate `obsidian-workflow-skills` repo)
- **All paths configurable** — vault path, folder structure, and interest profile name read from config instead of hardcoded
- **Generic suggestion headers** — "For Work" / "For Personal Life" instead of personal references
- **Dynamic knowledge base discovery** — evaluate-knowledge skill lists existing subfolders instead of using a hardcoded category table
- **Project renamed** to `ai-research-assistant-for-obsidian` (later shortened to `ai-research-assistant` in 0.3.0)

### Removed

- Hardcoded vault path (`~/Obsidian/Professional vault/`)
- Hardcoded skill paths and class-level `SKILL_CONFIG`
- `config/settings.yaml` (replaced by `defaults.yaml` + `user.yaml`)
- `scripts/install.sh` (replaced by setup wizard)

## [0.1.0] - 2026-01-19

Initial release. RSS pipeline with feed management, retry queue, and Claude Code skill invocation.

### Added

- RSS feed management (add, list, remove, OPML import/export)
- Pipeline orchestration with SQLite tracking
- Skill runner invoking Claude Code CLI (`/article`, `/youtube`, `/podcast`)
- Retry queue with exponential backoff (1h, 4h, 12h, 24h)
- Post-processing with `/evaluate-knowledge` skill
- Dry-run mode and verbose output
- Scheduled runs via launchd (macOS)
