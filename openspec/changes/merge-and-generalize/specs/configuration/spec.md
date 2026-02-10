## ADDED Requirements

### Requirement: Layered configuration loading
The system SHALL load configuration from `config/defaults.yaml` and deep-merge with `config/user.yaml` (if present). User values SHALL override defaults at any nesting level.

#### Scenario: Defaults only (no user config)
- **WHEN** `config/user.yaml` does not exist
- **THEN** the system loads all values from `config/defaults.yaml`

#### Scenario: User overrides a single value
- **WHEN** `config/user.yaml` contains only `vault: { path: "~/my-vault" }`
- **THEN** the merged config has the user's vault path and all other values from defaults

#### Scenario: User overrides a nested value
- **WHEN** `config/user.yaml` contains `folders: { youtube: "Videos/YouTube" }`
- **THEN** the merged config has the user's youtube folder and all other folder defaults unchanged

### Requirement: Configuration accessors
The system SHALL provide accessor functions for common config values: vault path, skills path, folder paths, project directory, and a check for whether the user has configured the system.

#### Scenario: Vault path resolution
- **WHEN** config contains `vault: { path: "~/Obsidian/My vault" }`
- **THEN** `get_vault_path()` returns expanded absolute Path

#### Scenario: Not configured
- **WHEN** `config/user.yaml` does not exist
- **THEN** `is_configured()` returns False

### Requirement: No hardcoded personal paths
The system SHALL NOT contain any hardcoded references to specific usernames, vault names, or absolute user paths in Python source code. All such values SHALL come from configuration.

#### Scenario: Grep for personal references
- **WHEN** searching `src/` for "jens", "echterling", "HeyJobs", or "Professional vault"
- **THEN** zero matches are found
