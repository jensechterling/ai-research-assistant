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
The setup wizard SHALL offer users the choice to link an existing interest profile or create one from the template.

#### Scenario: No existing profile — user chooses to create
- **WHEN** running first-time setup and the user selects "create from template"
- **THEN** the interest profile template is copied to the vault at the default path (`interest-profile.md`) and the user is told to fill it in

#### Scenario: User links an existing profile
- **WHEN** running first-time setup and the user selects "link existing file" and provides a vault-relative path (e.g., `About Me.md`)
- **THEN** the system SHALL validate the file exists in the vault, save the path to `profile.interest_profile` in `config/user.yaml`, and NOT copy the template

#### Scenario: Linked profile does not exist
- **WHEN** user provides a path to a file that does not exist in the vault
- **THEN** the system SHALL warn the user and prompt again

#### Scenario: Profile already exists at default path
- **WHEN** running first-time setup and `interest-profile.md` already exists in the vault and user chooses "create from template"
- **THEN** setup SHALL NOT overwrite it and SHALL inform the user

#### Scenario: Upgrade mode skips profile prompt
- **WHEN** running setup with existing `config/user.yaml`
- **THEN** the interest profile prompt is skipped entirely — the existing `profile.interest_profile` config value is preserved

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
