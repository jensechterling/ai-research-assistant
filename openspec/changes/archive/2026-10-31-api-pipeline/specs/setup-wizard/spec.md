# Spec Delta

## MODIFIED Requirements

### Requirement: Template rendering
The setup wizard SHALL render all Jinja2 templates (skills and infrastructure) using the merged configuration.

#### Scenario: Skill templates rendered
- **WHEN** setup completes
- **THEN** `skills/article/`, `skills/youtube/`, `skills/podcast/`, `skills/evaluate-knowledge/` directories exist with rendered `.md` files containing no Jinja2 `{{ }}` syntax

#### Scenario: Infrastructure templates rendered
- **WHEN** setup completes
- **THEN** the launchd plist contains the project directory path, and `config/mcp-minimal.json` is not created

### Requirement: Dependency checking
The setup wizard SHALL check for required external dependencies and warn about missing ones.

#### Scenario: Missing yt-dlp
- **WHEN** `yt-dlp` is not in PATH
- **THEN** setup warns that the manually used YouTube skill needs it and suggests `brew install yt-dlp`

#### Scenario: Missing claude CLI
- **WHEN** `claude` is not in PATH
- **THEN** setup warns that the manually used skills need the Claude Code CLI, and states that the scheduled pipeline does not

#### Scenario: npx not checked
- **WHEN** setup runs
- **THEN** it does not check for `npx`

#### Scenario: Missing Melious API key
- **WHEN** no key is found in the environment, `.env` or the configured Keychain item
- **THEN** setup warns the user and shows how to add `MELIOUS_API_KEY` to `.env` or to the Keychain

#### Scenario: Melious API key present
- **WHEN** a key is found
- **THEN** setup sends one minimal request to the configured endpoint and model, and reports whether the key and model were accepted, without printing the key
