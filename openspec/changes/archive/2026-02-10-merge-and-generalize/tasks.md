## Tasks

### Task 1: Create configuration system
- [ ] Create `src/config.py` with `load_config()`, `get_vault_path()`, `get_skills_path()`, `get_folder()`, `get_project_dir()`, `is_configured()`
- [ ] Rewrite `config/defaults.yaml` with full config structure (vault, folders, profile, processing, retry, feeds, schedule)
- [ ] Add `config/user.yaml` to `.gitignore`
- [ ] Delete `config/settings.yaml` (replaced by defaults.yaml)

### Task 2: Create setup wizard
- [ ] Create `src/setup.py` with Click `setup` command
- [ ] Implement interactive vault path prompt and folder customization
- [ ] Implement `render_templates()` — Jinja2 rendering of skills and infra templates
- [ ] Implement `install_skills()` — symlink skills to `~/.claude/skills/`
- [ ] Implement interest profile template copy (skip if exists in vault)
- [ ] Implement dependency checking (claude, yt-dlp, npx)
- [ ] Add `--install-schedule` flag for launchd plist setup
- [ ] Register `setup` command in `src/main.py`
- [ ] Add `jinja2>=3.1` to `pyproject.toml` dependencies

### Task 3: Copy and templatize skills
- [ ] Copy `article/` from obsidian-workflow-skills to `skills/_templates/article/`
- [ ] Copy `youtube/` to `skills/_templates/youtube/`
- [ ] Copy `podcast/` to `skills/_templates/podcast/`
- [ ] Copy `evaluate-knowledge/` to `skills/_templates/evaluate-knowledge/`
- [ ] Convert all folder references to Jinja2 variables (`{{ folders.youtube }}`, etc.)
- [ ] Replace `### For HeyJobs` → `### For Work` in all templates
- [ ] Replace `### For Me Personally` → `### For Personal Life` in all templates
- [ ] Remove HeyJobs references from evaluate-knowledge examples
- [ ] Replace hardcoded knowledge base subfolder table with dynamic discovery instruction
- [ ] Add generated skill directories to `.gitignore`

### Task 4: Create infrastructure templates
- [ ] Create `templates/mcp-minimal.json.j2` with vault_path variable
- [ ] Create `templates/run.sh.j2` with project_dir and uv_path variables
- [ ] Rename `templates/com.claude.ai-research-assistant.plist` to `.j2` and templatize paths
- [ ] Create `templates/interest-profile.md` with Work/Private structure
- [ ] Add `config/mcp-minimal.json` and `scripts/run.sh` to `.gitignore`
- [ ] Delete `config/mcp-minimal.json` (now generated)
- [ ] Delete `scripts/run.sh` (now generated)
- [ ] Delete `scripts/install.sh` (replaced by setup command)

### Task 5: Update pipeline code to use config
- [ ] Refactor `src/skill_runner.py` — remove hardcoded paths, read from config
- [ ] Refactor `src/pipeline.py` — use config for vault_path instead of `skill_runner.VAULT_PATH`

### Task 6: Update project metadata
- [ ] Rename project in `pyproject.toml` to `ai-research-assistant-for-obsidian`
- [ ] Add `jinja2>=3.1` dependency
- [ ] Update `.gitignore` with all generated files
- [ ] Rewrite `README.md` for public audience
- [ ] Rewrite `CLAUDE.md` to reflect new architecture

### Task 7: Update tests
- [ ] Update existing tests that reference hardcoded paths
- [ ] Add tests for `src/config.py` (loading, merging, accessors)
- [ ] Add tests for template rendering (verify no unresolved variables)
- [ ] Run full test suite and lint
