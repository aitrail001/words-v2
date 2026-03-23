# 2026-03-23 Lexicon Retry, Logging, and Phrase Validation Design

## Goal

Improve the lexicon tooling so operators can control retry cost, see what the tools are doing while they run, and avoid unnecessary phrase failures caused by inconsistent `usage_note` rules.

## Problems

### 1. Retry cost is too high and mostly fixed

The realtime enrichment path currently hard-codes retry counts in `tools/lexicon/enrich.py`. In the worst case a single lexeme can burn through multiple transient retries plus multiple repair attempts before failing, and operators cannot tune that from the CLI.

### 2. Lexicon CLI runs are too quiet

Most lexicon commands write only a final JSON payload or artifact files. During long runs it is difficult to tell:

- which entry is currently processing
- whether a retry happened
- why it retried
- how many retries remain
- whether the tool is stalled or making progress

### 3. Phrase `usage_note` rules are internally inconsistent

Phrase senses already allow `usage_note` to be absent, but phrase translation normalization currently requires every locale translation `usage_note` to be non-empty. This turns a missing optional source note into a hard runtime failure for translated fields.

## Approved Behavior

### Phrase validation rule

For phrase enrichment only:

- if the English phrase sense `usage_note` is absent or blank, each `translations.<locale>.usage_note` may be absent or blank
- if the English phrase sense `usage_note` is present, each `translations.<locale>.usage_note` must be non-blank
- when the English phrase sense note is present and a translated note is blank, treat that as a retryable realtime validation error

This is not a QC-only rule. It belongs in the realtime validation and retry path because the failure happens before QC today.

### Retry control

Retry behavior should become explicit runtime policy, passed from CLI into the enrichment flow instead of hard-coded constants.

Recommended defaults:

- lower transient retries from the current fixed default
- lower validation/repair retries from the current fixed default
- keep retries bounded and visible

The initial scope for configurable retries is realtime enrichment, because that is where the current retry loop exists.

### Logging and progress scope

Progress and logging should not be limited to realtime enrichment. The broader lexicon CLI surface should have a shared operator-facing logging/progress capability so long-running commands can surface progress consistently.

This includes commands such as:

- `enrich`
- `build-base`
- `build-phrases`
- `phrase-build-base`
- batch preparation / retry / ingest flows
- materialization / validation / import flows where the runtime is meaningful enough to report progress

Short commands can emit only start/finish summaries, while longer commands should emit per-item or per-stage progress when available.

## Recommended Architecture

## 1. Shared lexicon CLI runtime logger

Add a small shared runtime logging/progress helper for `tools/lexicon` commands.

Responsibilities:

- write concise terminal progress messages
- optionally write structured log events to a log file
- support log levels such as `quiet`, `info`, and `debug`
- avoid printing enrichment payload bodies
- standardize event shape across commands

Suggested event fields:

- timestamp
- command
- stage
- event
- snapshot_dir or output_dir when relevant
- lexeme_id / entry_id / lemma when relevant
- attempt number when relevant
- retry class when relevant
- retries remaining when relevant
- short reason string when relevant

This should be a shared utility, not ad hoc `print()` statements added independently to each command.

## 2. Realtime enrichment retry policy

Introduce a small retry policy object for realtime enrichment with separate counters for:

- transient transport/model errors
- retryable validation errors

Recommended initial CLI flags on `lexicon enrich`:

- `--transient-retries`
- `--validation-retries`
- `--log-level`
- `--log-file`

The runtime should log:

- lexeme queued
- lexeme started
- validation retry
- transient retry
- retry reason
- retries remaining
- lexeme completed
- lexeme failed

Phrase enrichment should use the same bounded retry policy as word enrichment rather than failing immediately on the first retryable validation issue.

## 3. Phrase-specific validation normalization

Update phrase schema normalization so translated `usage_note` validation depends on the English phrase sense note.

Behavior:

- source phrase note blank -> translated notes may be blank and normalize to `""`
- source phrase note present -> translated notes must be non-blank
- blank translated note in that second case -> raise a specific retryable validation error

The error reason should be explicit, for example:

- `missing_translated_usage_note_with_source_note_present`

This keeps phrase rules coherent without silently relaxing the contract for cases where the source note really exists and should be translated.

## CLI Surface

Shared lexicon CLI options should be added where they provide operator value.

Recommended minimum:

- add logging options to long-running or multi-stage commands
- keep the default terminal output concise
- write richer detail to the log file when requested

For `enrich`, add both logging options and retry-control options.

For other commands, add logging options first and expose progress events where the command already iterates records or stages.

Implemented scope for this slice:

- all lexicon CLI subcommands accept shared `--log-level` and `--log-file` options
- command-level start/complete/failure events are emitted consistently across the CLI surface
- `build-base`, `build-phrases`, `phrase-build-base`, `batch-prepare`, `batch-ingest`, `import-db`, and `smoke-openai-compatible` emit item-progress events
- `enrich` additionally emits per-lexeme retry/lifecycle events with retry reasons and retries remaining

## Out of Scope

- redesigning lexicon QC policy broadly
- changing word-enrichment translation `usage_note` rules unless a separate requirement appears
- emitting full model payloads to the terminal
- building a persistent job framework for all CLI commands in this slice

## Testing

### Realtime enrichment

- phrase validation accepts blank translated note when source phrase note is absent
- phrase validation raises retryable error when source phrase note is present and translated note is blank
- phrase enrichment retries boundedly on that retryable error
- retry counters honor configured limits

### Shared CLI logging

- commands can construct a shared runtime logger
- `info` output includes high-signal stage/progress lines
- `debug` log file receives structured events without payload bodies

### CLI plumbing

- new CLI flags parse and reach runtime code
- default retry values are lower than the current fixed defaults
- non-enrichment commands can opt into the shared logger without altering their result artifacts

## Risks

- applying logging inconsistently across commands would create a mixed operator experience
- retry classification that is too broad could hide genuine schema defects
- retry classification that is too narrow will preserve the current phrase failure pain
- adding logging to many commands without a shared helper will create drift and duplicated formatting logic

## Recommendation

Proceed with three coordinated changes:

1. add a shared lexicon CLI logger/progress utility
2. parameterize and lower realtime enrichment retries while making retry state visible
3. make phrase translated `usage_note` validation conditional on the source phrase note, with retryable handling when translation is missing but required
