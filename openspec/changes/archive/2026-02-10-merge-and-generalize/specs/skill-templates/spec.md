## ADDED Requirements

### Requirement: Skills stored as Jinja2 templates
The system SHALL store article, youtube, podcast, and evaluate-knowledge skills as Jinja2 templates in `skills/_templates/`. Generated skill files SHALL be gitignored.

#### Scenario: Template directory structure
- **WHEN** examining `skills/_templates/`
- **THEN** it contains `article/`, `youtube/`, `podcast/`, and `evaluate-knowledge/` subdirectories with `.md` template files

#### Scenario: Generated files gitignored
- **WHEN** checking `.gitignore`
- **THEN** `skills/article/`, `skills/youtube/`, `skills/podcast/`, `skills/evaluate-knowledge/` are listed

### Requirement: Configurable folder paths in skills
All skill templates SHALL use Jinja2 variables for vault folder paths instead of hardcoded values.

#### Scenario: YouTube output folder
- **WHEN** config has `folders.youtube: "My Videos/YouTube"`
- **THEN** the rendered youtube skill references `My Videos/YouTube` as its output folder

#### Scenario: Interest profile path
- **WHEN** config has `profile.interest_profile: "my-profile.md"`
- **THEN** all rendered skills reference `my-profile.md` instead of `interest-profile.md`

### Requirement: No personal references in skill templates
Skill templates SHALL NOT contain references to specific companies, people, or personal vault structures.

#### Scenario: No company name in templates
- **WHEN** searching `skills/_templates/` for "HeyJobs"
- **THEN** zero matches are found

#### Scenario: Generic suggestion headers
- **WHEN** examining rendered skill output format sections
- **THEN** headers read "For Work" and "For Personal Life"

### Requirement: Dynamic knowledge base folder discovery
The evaluate-knowledge skill template SHALL instruct Claude to discover existing subfolders in the knowledge base directory rather than using a hardcoded list of categories.

#### Scenario: Custom knowledge base structure
- **WHEN** a user's knowledge base has folders "Engineering", "Design", "Research"
- **THEN** the evaluate-knowledge skill uses those folders as filing targets

### Requirement: update-obsidian-claude-md excluded
The `update-obsidian-claude-md` skill SHALL NOT be included in the merged repository.

#### Scenario: Skill not present
- **WHEN** examining `skills/_templates/`
- **THEN** no `update-obsidian-claude-md/` directory exists
