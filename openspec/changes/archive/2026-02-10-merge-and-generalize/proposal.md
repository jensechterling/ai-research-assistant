## Why

The project currently exists as two tightly coupled repos — a pipeline (AI research assistant) and skills (obsidian-workflow-skills) — both hardcoded to one user's setup (paths, vault structure, company references). Merging them into a single shareable project lets others use the same RSS-to-Obsidian workflow. The skills repo stays as-is for personal use; this repo becomes the generalised, distributable version.

## What Changes

- **Merge skills into this repo**: Copy article, youtube, podcast, and evaluate-knowledge skills into a `skills/_templates/` directory as Jinja2 templates. `update-obsidian-claude-md` does NOT come over.
- **Introduce configuration system**: A `config/defaults.yaml` (version-controlled) + `config/user.yaml` (gitignored) pattern. Python code loads merged config. Jinja2 renders skills and infrastructure files from templates.
- **Add setup wizard**: `uv run ai-research-assistant setup` — interactive first-time setup that asks vault path, folder preferences (with sensible defaults), copies interest-profile template to vault, generates skill files, symlinks to `~/.claude/skills/`, checks dependencies.
- **Remove all personal references**: Replace hardcoded `/Users/jens.echterling/` paths, "HeyJobs" section headers, and personal folder structures with config-driven values. Suggestion headers become "For Work" / "For Personal Life".
- **Make vault structure configurable**: Output folders (youtube, podcast, article, knowledge base, daily notes) are defined in config with sensible defaults. Skills and pipeline code read from the same config source.
- **Support clean upgrades**: `git pull && uv sync && uv run ai-research-assistant setup` re-renders templates from updated sources + existing user config. No user data lost.
- **Rename project**: `ai-research-assistant` → `ai-research-assistant-for-obsidian`
- **Generate infrastructure files from config**: `mcp-minimal.json`, `scripts/run.sh`, and launchd plist are rendered from templates using user config (vault path, project path, log dir, schedule).

## Capabilities

### New Capabilities
- `configuration`: Layered config system — defaults.yaml (version-controlled) merged with user.yaml (gitignored). Single source of truth for vault path, folder paths, schedule, and all user-specific settings.
- `setup-wizard`: Interactive CLI command that bootstraps a new installation — collects user input, writes config, renders templates, installs skills, copies interest-profile template, checks dependencies. Also handles upgrades (re-renders from existing config).
- `skill-templates`: Jinja2 template versions of article, youtube, podcast, and evaluate-knowledge skills. Rendered into usable skill .md files by the setup wizard using config values.

### Modified Capabilities

(No existing specs to modify)

## Impact

- **src/skill_runner.py**: Remove hardcoded `VAULT_PATH`, `SKILLS_PATH`. Read from config module.
- **src/pipeline.py**: Update to use config-driven paths for evaluate-knowledge post-processing.
- **config/**: New `defaults.yaml`, `user.yaml` (gitignored), `mcp-minimal.json` becomes a generated file.
- **skills/**: New directory with `_templates/` (version-controlled) and generated skill folders (gitignored).
- **scripts/run.sh**: Becomes a generated file from template.
- **templates/**: Interest-profile template added. Launchd plist stays as template but rendered from config.
- **pyproject.toml**: Add Jinja2 dependency. Rename project.
- **.gitignore**: Add `config/user.yaml`, `skills/article/`, `skills/youtube/`, `skills/podcast/`, `skills/evaluate-knowledge/`, `config/mcp-minimal.json`, `scripts/run.sh`.
- **README.md, CLAUDE.md**: Rewrite for public audience with setup instructions.
