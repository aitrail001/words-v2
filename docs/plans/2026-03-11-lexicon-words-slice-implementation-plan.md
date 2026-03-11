# Lexicon Words Slice Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the first learner-first lexicon slice that generates and imports common English single-word entries into the local DB end-to-end, while laying the shared foundations for later multiword categories.

**Architecture:** Build a shared entry-oriented pipeline that supports `entry_type`, normalized IDs, and source provenance now, but ingest/generate only `word` entries in this PR. Use `wordfreq` for the top-common-word inventory, WordNet as grounded meaning context, and LLM per-entry generation for learner-facing meanings and enrichment. Keep review as a narrow exception path and validate/import only learner-ready entries.

**Tech Stack:** Python lexicon admin tool, `wordfreq`, WordNet, local JSONL snapshots, existing FastAPI/Postgres importer, pytest, targeted backend import tests, bounded smoke validation, GitHub Actions CI.

---

### Task 1: Freeze the shared entry contract for the words slice

**Files:**
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Test: `tools/lexicon/tests/test_models.py`

**Step 1: Write failing model tests**
- Add tests for `entry_type`, `entry_id`, `normalized_form`, and source provenance fields in the shared entry model.

**Step 2: Run the targeted model tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_models.py -q`

**Step 3: Implement the shared entry contract**
- Extend the base lexeme/compiled record models with the new shared fields needed for later categories.
- Keep compatibility with the current words-only flow.

**Step 4: Re-run the targeted model tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_models.py -q`

### Task 2: Add a `wordfreq`-driven common-word inventory builder

**Files:**
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/cli.py`
- Test: `tools/lexicon/tests/test_build_base.py`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing tests for top-common-word sourcing**
- Add tests covering a words-only inventory mode sourced from `wordfreq`.
- Add tests for normalized output IDs and retained provenance.

**Step 2: Run the targeted build/CLI tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_cli.py -q`

**Step 3: Implement the words inventory builder**
- Add a words-only path that can build a bounded top-N English inventory from `wordfreq`.
- Preserve the ability to run small staged rollouts (`100`, `1000`, `5000`, `30000`).
- Stamp source provenance as `wordfreq`.

**Step 4: Re-run the targeted tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_cli.py -q`

### Task 3: Add learner-first word filtering and normalization

**Files:**
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/wordfreq_utils.py`
- Test: `tools/lexicon/tests/test_build_base.py`

**Step 1: Write failing tests for junk-token filtering**
- Cover malformed tokens, obvious non-entries, and normalization behavior.

**Step 2: Run the targeted tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py -q`

**Step 3: Implement minimal filtering rules**
- Filter malformed tokens/junk.
- Preserve legitimate learner words even when short/high-frequency.
- Keep the rules deterministic and documented.

**Step 4: Re-run the targeted tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py -q`

### Task 4: Reframe meaning selection as LLM-chosen learner meanings with WordNet grounding

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/models.py`
- Test: `tools/lexicon/tests/test_enrich.py`
- Test: `tools/lexicon/tests/test_compile_export.py`

**Step 1: Write failing tests for grounded learner-meaning generation**
- Cover prompts/outputs where WordNet is context only and the LLM returns learner-selected meanings.
- Cover adaptive max meaning caps for common words.

**Step 2: Run targeted enrichment/compile tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_compile_export.py -q`

**Step 3: Implement per-entry learner-first meaning generation**
- Build word-level prompts that include bounded WordNet grounding.
- Ask the LLM to choose the top learner-friendly meanings rather than mirroring deterministic selected senses blindly.
- Enforce adaptive caps by word frequency band.

**Step 4: Re-run the targeted tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_compile_export.py -q`

### Task 5: Strengthen schema validation for learner-ready word entries

**Files:**
- Modify: `tools/lexicon/validate.py`
- Modify: `tools/lexicon/models.py`
- Test: `tools/lexicon/tests/test_validate.py`

**Step 1: Write failing validation tests for the new shared/word fields**
- Cover `entry_type`, `entry_id`, `normalized_form`, source provenance, adaptive meaning count limits, and strict forms/example structure.

**Step 2: Run targeted validation tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_validate.py -q`

**Step 3: Implement validation updates**
- Make learner-ready compiled output fail loudly on invalid structure.
- Keep validation messages field-specific.

**Step 4: Re-run the targeted tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_validate.py -q`

### Task 6: Keep review as an exception path, not the main publication path

**Files:**
- Modify: `tools/lexicon/selection_review.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Test: `tools/lexicon/tests/test_selection_review.py`

**Step 1: Write failing tests for the words-slice exception policy**
- Cover cases where clean, valid words bypass review.
- Cover cases where only unstable/low-confidence outputs are staged.

**Step 2: Run targeted review tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_selection_review.py -q`

**Step 3: Implement narrow review gating**
- Keep the words slice review path minimal and explicitly exceptional.
- Document that main DB import receives only learner-ready entries.

**Step 4: Re-run the targeted tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_selection_review.py -q`

### Task 7: Verify local import into the existing DB model

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`
- Verify: `backend/app/api/words.py`

**Step 1: Write failing importer tests for the words slice contract**
- Cover the shared fields that should persist now.
- Ensure words-only learner-ready imports remain stable and idempotent.

**Step 2: Run targeted importer tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`

**Step 3: Implement importer updates**
- Preserve compatibility with current DB schema.
- Import the learner-ready word slice cleanly without requiring future phrase tables yet.

**Step 4: Re-run targeted importer tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`

### Task 8: Add bounded rollout commands and operator docs

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing CLI tests for staged words rollouts**
- Cover `100`, `1000`, `5000`, and `30000` style bounded words-only flows.

**Step 2: Run targeted CLI tests to confirm failure**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q`

**Step 3: Implement staged words-rollout support**
- Add explicit operator-facing commands or flags for bounded staged runs.
- Keep the flow scriptable for CI smoke and local ops.

**Step 4: Re-run the targeted tests**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q`

### Task 9: Run verification matrix for the words slice

**Files:**
- Verify: `tools/lexicon/tests/*`
- Verify: `docs/status/project-status.md`

**Step 1: Run the full lexicon test suite**
Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`

**Step 2: Run a bounded local words smoke**
Run the words-only flow for a very small staged size and verify:
- build-base
- enrich
- validate
- compile-export
- import-db dry-run or real local import

**Step 3: Update project status with fresh evidence**
- Add an evidence-backed status row to `docs/status/project-status.md`.

### Task 10: Commit, PR, CI, merge, and cleanup

**Files:**
- Modify: `docs/status/project-status.md`
- Verify: branch, PR, CI, cleanup state

**Step 1: Commit focused changes**
Run: `git add ... && git commit -m "feat: add learner-first words lexicon slice"`

**Step 2: Push and open PR**
- Open one focused PR for the words slice only.

**Step 3: Watch required checks**
- Resolve CI drift if needed.
- Merge only after verification evidence is fresh.

**Step 4: Clean merged resources**
- Remove merged feature branch/worktree.
- Leave follow-up multiword categories for fresh branches/worktrees.
