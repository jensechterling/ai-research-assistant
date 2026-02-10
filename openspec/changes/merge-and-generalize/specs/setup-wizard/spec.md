## ADDED Requirements

### Requirement: Interactive first-time setup
The system SHALL provide a `setup` CLI subcommand that interactively collects user configuration (vault path, folder preferences) and writes `config/user.yaml`.

#### Scenario: First-time setup
- **WHEN** user runs `ai-research-assistant setup` with no existing `config/user.yaml`
- **THEN** the wizard asks for vault path, shows folder defaults, writes config, renders templates, installs skills, and checks dependencies

#### Scenario: Vault path is required
- **WHEN** user does not provide a vault path
- **THEN** setup refuses to proceed and prompts again

### Requirement: Template rendering
The setup wizard SHALL render all Jinja2 templates (skills and infrastructure) using the merged configuration.

#### Scenario: Skill templates rendered
- **WHEN** setup completes
- **THEN** `skills/article/`, `skills/youtube/`, `skills/podcast/`, `skills/evaluate-knowledge/` directories exist with rendered `.md` files containing no Jinja2 `{{ }}` syntax

#### Scenario: Infrastructure templates rendered
- **WHEN** setup completes
- **THEN** `config/mcp-minimal.json` contains the user's vault path, and `scripts/run.sh` contains the project directory path

### Requirement: Skill installation via symlinks
The setup wizard SHALL create symlinks from generated skill directories to `~/.claude/skills/`.

#### Scenario: Symlinks created
- **WHEN** setup completes
- **THEN** `~/.claude/skills/article` is a symlink pointing to the generated `skills/article/` directory

#### Scenario: Existing symlink replaced
- **WHEN** a symlink already exists at `~/.claude/skills/article`
- **THEN** setup removes the old symlink and creates a new one

### Requirement: Interest profile template
The setup wizard SHALL copy an interest profile template to the user's vault if one does not already exist.

#### Scenario: No existing profile
- **WHEN** `interest-profile.md` does not exist in the vault
- **THEN** setup copies the template and informs the user to fill it in

#### Scenario: Profile already exists
- **WHEN** `interest-profile.md` already exists in the vault
- **THEN** setup does not overwrite it

### Requirement: Silent upgrade mode
The setup wizard SHALL detect existing configuration and re-render templates without re-asking questions.

#### Scenario: Re-run with existing config
- **WHEN** user runs `ai-research-assistant setup` with existing `config/user.yaml`
- **THEN** setup loads existing config, re-renders all templates, re-installs symlinks, and reports completion without interactive prompts

### Requirement: Dependency checking
The setup wizard SHALL check for required external dependencies and warn about missing ones.

#### Scenario: Missing yt-dlp
- **WHEN** `yt-dlp` is not in PATH
- **THEN** setup warns the user and suggests `brew install yt-dlp`

#### Scenario: Missing claude CLI
- **WHEN** `claude` is not in PATH
- **THEN** setup warns the user with installation instructions
