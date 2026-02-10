## MODIFIED Requirements

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
