## Context

Two tightly coupled repos — a Python pipeline (AI research assistant) and markdown skills (obsidian-workflow-skills) — both hardcoded to one user. The pipeline shells out to `claude` CLI to invoke skills that live in `~/.claude/skills/`. Skills are markdown instruction files that Claude reads at runtime. Both repos reference personal vault paths, company name ("HeyJobs"), and specific folder structures.

Current architecture: Pipeline → shells out to `claude /{skill} {url}` → skill reads its SKILL.md → Claude follows instructions → writes note to Obsidian via MCP.

## Goals / Non-Goals

**Goals:**
- Merge 4 skills (article, youtube, podcast, evaluate-knowledge) into this repo
- Make all paths, folders, and personal references configurable
- Provide setup wizard for first-time users and clean upgrade path
- Keep the same runtime architecture (pipeline → claude CLI → skill → Obsidian MCP)

**Non-Goals:**
- Changing how skills are invoked at runtime (still `~/.claude/skills/` symlinks)
- Making the pipeline cross-platform (stays macOS for launchd scheduling)
- Adding new skills or changing skill behavior
- Renaming the GitHub repository (manual step)
- Modifying the original obsidian-workflow-skills repo

## Decisions

### D1: Jinja2 templates for skills
**Choice**: Store skills as Jinja2 templates, render during setup.
**Why**: Skills are markdown — they can't import config at runtime. Templates let us inject folder paths at setup time while keeping skills as normal `.md` files at runtime.
**Alternative considered**: Skills read a config note from the vault via Obsidian MCP at runtime. Rejected because it adds latency/fragility to every invocation and complicates skill instructions.

### D2: Layered YAML config
**Choice**: `config/defaults.yaml` (version-controlled) + `config/user.yaml` (gitignored), deep-merged by `src/config.py`.
**Why**: Upgrades ship new defaults without touching user config. One file to configure everything.
**Alternative considered**: Environment variables. Rejected because too many settings and templates need structured data (folder mappings).

### D3: Setup wizard as CLI subcommand
**Choice**: `uv run ai-research-assistant setup` — interactive Click command.
**Why**: Reuses existing CLI infrastructure. Can also be run non-interactively for upgrades (detects existing config, re-renders silently).
**Alternative considered**: Separate shell script. Rejected because Python gives us Jinja2 rendering, YAML handling, and better UX.

### D4: Dynamic knowledge base subfolders
**Choice**: Replace hardcoded folder categories in evaluate-knowledge with "list existing subfolders and pick best fit."
**Why**: The current categories (Business models, Leadership, Product, etc.) are one person's taxonomy. Dynamic discovery adapts to any vault.

### D5: Generic suggestion headers
**Choice**: `### For Work` / `### For Personal Life` everywhere.
**Why**: The skills already read the interest profile for content personalization. Section headers just need to be generic. The suggestions themselves are personalized by Claude reading the profile.

## Risks / Trade-offs

- **Template rendering adds a setup step** → Mitigated by making it part of `setup` command and upgrade flow
- **Jinja2 syntax in markdown could confuse editors** → Templates are in `_templates/` subdirectory, clearly marked. Generated files are gitignored.
- **Config schema changes on upgrade could break user.yaml** → Mitigated by deep-merge (new defaults fill gaps) and keeping user.yaml minimal (only overrides)
- **Dynamic subfolder discovery in evaluate-knowledge less predictable than hardcoded list** → Acceptable trade-off for generalizability. Users who want a fixed list can add it to their vault's README or the skill template.
