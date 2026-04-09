# Lexicon Retry, Logging, and Phrase Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add shared lexicon CLI progress/logging, lower and parameterize realtime enrichment retries, and make phrase translated `usage_note` validation conditional on whether the source phrase note exists.

**Architecture:** Introduce a shared `tools/lexicon` runtime logger that command handlers can opt into, then thread an explicit retry policy through realtime enrichment. Phrase normalization will classify missing translated `usage_note` values as acceptable only when the source phrase note is absent, and otherwise raise a retryable validation error that the realtime loop can retry within bounded limits.

**Tech Stack:** Python 3.13, argparse CLI, JSONL artifacts, pytest/unittest, existing lexicon schemas and enrichment pipeline.

---

### Task 1: Add Failing Phrase Validation Tests

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/schemas/phrase_enrichment_schema.py`

**Step 1: Write the failing tests**

Add focused tests covering:

- phrase normalization accepts blank `translations.<locale>.usage_note` when the source phrase `usage_note` is `None`
- phrase normalization rejects blank `translations.<locale>.usage_note` when the source phrase `usage_note` is present
- the rejection uses a specific retryable reason label

**Step 2: Run the narrow test to verify it fails**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- the new phrase validation assertions fail for the current strict translation-note behavior

**Step 3: Write the minimal implementation**

Update `tools/lexicon/schemas/phrase_enrichment_schema.py` so phrase translation normalization:

- normalizes blank translated notes to `""` only when the source phrase note is absent/blank
- raises a distinct retryable runtime error when the source phrase note exists but a translated note is blank

**Step 4: Run the narrow test to verify it passes**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- the new phrase validation tests pass

### Task 2: Add Failing Realtime Phrase Retry Tests

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write the failing tests**

Add tests showing:

- phrase enrichment retries when the source phrase note is present and a translated note is blank
- phrase enrichment succeeds if a later retry returns a valid translated note
- phrase enrichment fails after the configured validation retry limit is exhausted

**Step 2: Run the narrow test to verify it fails**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- the phrase provider path fails immediately or does not honor configurable validation retry limits

**Step 3: Write the minimal implementation**

In `tools/lexicon/enrich.py`:

- add an explicit retry policy object for realtime enrichment
- reuse it for both word and phrase provider flows
- classify the new phrase validation error as retryable validation, not terminal on first occurrence

**Step 4: Run the narrow test to verify it passes**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- phrase retry behavior is bounded and deterministic

### Task 3: Add Failing CLI Retry-Policy Plumbing Tests

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write the failing tests**

Add tests covering:

- `lexicon enrich` accepts `--transient-retries` and `--validation-retries`
- CLI defaults are lower than the current hard-coded enrichment defaults
- parsed values are forwarded to `run_enrichment`

**Step 2: Run the narrow test to verify it fails**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q
```

Expected:

- CLI parsing/forwarding fails because the new flags and runtime fields do not exist yet

**Step 3: Write the minimal implementation**

Update:

- `tools/lexicon/cli.py` to add enrich retry-policy flags
- `tools/lexicon/enrich.py` to accept and thread retry-policy values through `run_enrichment` and `enrich_snapshot`

**Step 4: Run the narrow test to verify it passes**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q
```

Expected:

- CLI tests covering the new retry-policy options pass

### Task 4: Add Failing Shared Logging Utility Tests

**Files:**
- Create: `tools/lexicon/runtime_logging.py`
- Create: `tools/lexicon/tests/test_runtime_logging.py`

**Step 1: Write the failing tests**

Add tests for a shared runtime logger that:

- emits concise terminal lines at `info`
- writes structured JSONL-style events to a log file when configured
- suppresses payload bodies
- supports command/stage/event metadata consistently

**Step 2: Run the narrow test to verify it fails**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_runtime_logging.py -q
```

Expected:

- tests fail because the shared logger module does not exist yet

**Step 3: Write the minimal implementation**

Create `tools/lexicon/runtime_logging.py` with:

- a small config object
- a runtime logger that supports `quiet`, `info`, and `debug`
- methods for stage start, item progress, retry, warning, completion, and failure events
- optional file output with one structured event per line

**Step 4: Run the narrow test to verify it passes**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_runtime_logging.py -q
```

Expected:

- the shared runtime logging tests pass

### Task 5: Wire Shared Logging Into Enrichment

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Write the failing tests**

Add tests proving:

- `lexicon enrich` accepts `--log-level` and `--log-file`
- realtime enrichment emits start/retry/complete/fail events without printing enrichment payload content
- retries log the reason and retries remaining

**Step 2: Run the narrow tests to verify they fail**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q
```

Expected:

- enrichment logging expectations fail because the runtime logger is not wired in yet

**Step 3: Write the minimal implementation**

Update the enrichment runtime to emit shared logger events for:

- lexeme scheduled
- lexeme started
- retry scheduled
- retry reason
- retries remaining
- lexeme completed
- lexeme failed

Add CLI plumbing for the enrich logging flags and default log-file behavior.

**Step 4: Run the narrow tests to verify they pass**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q
```

Expected:

- enrich logging and CLI flag tests pass

### Task 6: Wire Shared Logging Into Other Lexicon CLI Commands

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/phrase_pipeline.py`
- Modify: `tools/lexicon/batch_ingest.py`
- Modify: `tools/lexicon/batch_prepare.py`
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Write the failing tests**

Add focused tests for representative non-enrichment commands showing:

- shared logging options are available to lexicon CLI commands beyond `enrich`
- longer-running commands emit stage/item progress through the shared logger
- final command JSON outputs or artifact writes remain unchanged

Prefer a representative slice instead of snapshot-testing every command output line.

**Step 2: Run the narrow tests to verify they fail**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q
```

Expected:

- representative non-enrichment command logging tests fail because the shared logger is not exposed broadly yet

**Step 3: Write the minimal implementation**

Wire the shared runtime logger into the command handlers and selected underlying iterators so:

- all lexicon commands can accept shared logging options
- commands that process many rows or stages emit progress
- short commands emit start/finish summaries only
- existing JSON result payloads stay stable

**Step 4: Run the narrow test to verify it passes**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q
```

Expected:

- shared logging is available across the targeted lexicon CLI surface without output regressions

### Task 7: Update Operator Docs and Live Status

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `docs/plans/2026-03-23-lexicon-retry-logging-and-phrase-validation-design.md`
- Modify: `docs/plans/2026-03-23-lexicon-retry-logging-and-phrase-validation-implementation-plan.md`

**Step 1: Re-read the design and implementation scope**

Confirm the final implementation still matches:

- lower, configurable realtime retries
- shared CLI logging/progress across lexicon tools
- conditional phrase translated-note validation

**Step 2: Update live status with fresh evidence**

Add a `Status Change Log` entry to `docs/status/project-status.md` describing:

- what changed for lexicon operators
- what was verified
- which tests provide evidence

**Step 3: Run the docs/status verification**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && rg -n "retry|logging|phrase" docs/status/project-status.md docs/plans/2026-03-23-lexicon-retry-logging-and-phrase-validation-design.md docs/plans/2026-03-23-lexicon-retry-logging-and-phrase-validation-implementation-plan.md
```

Expected:

- all three docs reflect the implemented scope accurately

### Task 8: Full Verification Before Completion

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_cli.py`

## Implementation Notes

Implemented runtime logging coverage in this slice:

- shared `--log-level` / `--log-file` options on all lexicon CLI subcommands
- command-start / command-complete / command-failure events across the CLI surface
- item-progress events for `build-base`, `build-phrases`, `phrase-build-base`, `batch-prepare`, `batch-ingest`, `import-db`, and `smoke-openai-compatible`
- per-lexeme lifecycle and retry events for realtime `enrich`
- Create: `tools/lexicon/tests/test_runtime_logging.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/schemas/phrase_enrichment_schema.py`
- Create: `tools/lexicon/runtime_logging.py`
- Modify: `docs/status/project-status.md`

**Step 1: Run the focused lexicon verification suite**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_runtime_logging.py -q
```

Expected:

- all targeted tests pass

**Step 2: Run a broader lexicon test sweep**

Run:

```bash
cd /Users/johnson/AI/src/words-v2/.worktrees/feat_lexicon_retry_logging_20260323 && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

Expected:

- the broader lexicon suite passes with no regressions

**Step 3: Record the exact evidence**

Capture:

- test command outputs
- pass counts
- any skipped checks

Only then report the work as complete.
