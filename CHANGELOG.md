# Changelog

All notable changes to this project will be documented in this file.

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
- **Project renamed** to `ai-research-assistant-for-obsidian`

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
