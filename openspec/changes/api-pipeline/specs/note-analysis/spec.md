# Spec Delta

## Purpose

Produces the written parts of a research note (summary, findings, personalized suggestions, filing decision) from one structured LLM call to Melious per entry.

## ADDED Requirements

### Requirement: Single Melious call per entry
The system SHALL analyze each extracted entry with one chat-completion request to the endpoint `llm.base_url` using model `llm.model`. Defaults are `https://api.melious.ai/v1` and `deepseek-v4.1-flash`. No other provider is supported.

#### Scenario: Default configuration
- **WHEN** `config/user.yaml` sets no `llm` values
- **THEN** requests go to `https://api.melious.ai/v1` with model `deepseek-v4.1-flash`

### Requirement: API key resolution
The system SHALL read the API key from the first of these that provides one: the `MELIOUS_API_KEY` environment variable, `MELIOUS_API_KEY` in the project's `.env` file, or the macOS Keychain generic password with service `llm.keychain_service` (default `melious-api-key`). A Keychain lookup SHALL time out after 10 seconds. The key SHALL never be written to logs, notes, notifications, the database or config files.

#### Scenario: Key from environment
- **WHEN** `MELIOUS_API_KEY` is set in the environment
- **THEN** that value is used and neither `.env` nor the Keychain is read

#### Scenario: Key from .env in an interactive shell
- **WHEN** the environment has no `MELIOUS_API_KEY` and `.env` contains `MELIOUS_API_KEY=abc` without `export`
- **THEN** `abc` is used

#### Scenario: Key from Keychain
- **WHEN** neither the environment nor `.env` provides a key and the Keychain item exists
- **THEN** the Keychain value is used

#### Scenario: Keychain lookup hangs
- **WHEN** the Keychain lookup does not return within 10 seconds
- **THEN** it is treated as not found

#### Scenario: No key anywhere
- **WHEN** no source provides a key
- **THEN** the run stops before processing any entry, with an error naming all three sources

### Requirement: Analysis inputs
The request SHALL include the extracted text and metadata, the full interest profile, the names of the existing top-level knowledge-base subfolders, today's date, and an instruction to write in `llm.output_language` (default English).

#### Scenario: Output language instruction
- **WHEN** `llm.output_language` is `English`
- **THEN** the request instructs the model to write all analysis fields in English regardless of the source language

#### Scenario: Interest profile missing
- **WHEN** the configured interest profile file does not exist in the vault
- **THEN** the run stops before processing any entry, with an error naming the expected path

### Requirement: Structured analysis result
The model's reply SHALL be a JSON object that the system validates against a fixed schema. Its fields are the summary, key findings, work suggestions, personal suggestions, up to five topical tags, the target knowledge-base folder, a one-line takeaway and a one-line action.

#### Scenario: Valid reply
- **WHEN** the reply parses as JSON and matches the schema
- **THEN** analysis succeeds with those fields

#### Scenario: Invalid reply repaired
- **WHEN** the first reply is complete but is not valid JSON or fails the schema
- **THEN** the system sends one follow-up request containing the validation error, and uses that reply if it is valid

#### Scenario: Repair also fails
- **WHEN** the follow-up reply is also invalid
- **THEN** analysis fails as a transient failure with the validation error as the message

### Requirement: Truncated replies
A reply that stopped because it reached the output-token limit SHALL NOT be sent to repair. The system SHALL repeat the request once with the limit doubled, up to the model's 32,000-token maximum. If that reply is also truncated, analysis fails as a transient failure with the reason "output truncated".

#### Scenario: Reasoning used up the budget
- **WHEN** the first reply ends with finish reason `length` at 8,000 tokens and the second, at 16,000, completes
- **THEN** analysis uses the second reply

### Requirement: Model output never sets source facts
The source URL, title, author, publication date and original text in the note SHALL come from extraction, not from the model's reply.

#### Scenario: Model returns a different URL
- **WHEN** the model's reply contains a URL that differs from the entry URL
- **THEN** the note still contains the exact entry URL character for character

### Requirement: Request timeout and retry
Each request SHALL time out after `llm.timeout_seconds`. Timeouts, connection errors, HTTP 429 and HTTP 5xx SHALL be retried up to `llm.max_retries` times with increasing delay before the analysis counts as a transient failure.

#### Scenario: One server error then success
- **WHEN** the first request returns HTTP 503 and the retry returns a valid reply
- **THEN** analysis succeeds

#### Scenario: Persistent timeouts
- **WHEN** every attempt times out
- **THEN** analysis fails as a transient failure after `llm.max_retries` retries

### Requirement: Account-level API errors are fatal
HTTP 401, 402, 403 and 404 from the API SHALL stop the run instead of failing only the current entry. These mean a rejected key, no credit, no access, or an unknown model, and would fail every entry the same way.

#### Scenario: Revoked key
- **WHEN** the API returns HTTP 401 for the first entry
- **THEN** the run stops, the entry is not added to the retry queue, and the remaining entries are left for the next run

#### Scenario: Model renamed
- **WHEN** the API returns HTTP 404 because `llm.model` no longer exists
- **THEN** the run stops and the error names the model

### Requirement: Usage and cost reporting
For each analyzed entry the system SHALL log input tokens, cached input tokens, reasoning tokens, output tokens, cost in EUR, and the serving provider ID when the response includes one. A request's cost SHALL be the response's reported billed cost when present. Otherwise it is computed from `llm.price_input_per_mtok`, `llm.price_cached_input_per_mtok` and `llm.price_output_per_mtok`. The entry's cost is summed over every request, including repair and truncation retries.

#### Scenario: Cost computed when not reported
- **WHEN** a response without a billed cost uses 10,000 input and 2,000 output tokens, none cached, at EUR 0.20 and EUR 1.00 per million
- **THEN** the log shows a cost of EUR 0.0040 for that entry

#### Scenario: Reported cost preferred
- **WHEN** a response reports a billed cost of 0.0004698
- **THEN** that figure is used for the request's cost

### Requirement: Reasoning setting
When `llm.reasoning_effort` is set, the system SHALL send it as the request's `reasoning_effort`. When it is unset, the parameter SHALL be omitted, so the model default applies.

#### Scenario: Reasoning turned off
- **WHEN** `llm.reasoning_effort` is `none`
- **THEN** every analysis request includes `reasoning_effort: "none"`
