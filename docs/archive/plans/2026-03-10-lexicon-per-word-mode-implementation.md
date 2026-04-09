# Lexicon Per-Word Enrichment + Mode C Filtering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new per-word lexicon enrichment mode with bounded parallelism, first-class Mode C compile filtering, and a reviewer-friendly admin UI, while preserving the current per-sense fallback path.

**Architecture:** The implementation keeps the current per-sense enrichment pipeline intact and adds a parallel per-word enrichment artifact path that compiles into the same downstream learner-facing export shape. `compile-export` becomes decisions-aware for Mode C safe compilation, and the admin review API/UI is upgraded to render candidate sense evidence cleanly without changing the staging architecture.

**Tech Stack:** Python 3.9, JSONL lexicon pipeline, FastAPI, SQLAlchemy, Next.js 15, React Testing Library, pytest, Playwright, GitHub Actions.

---

### Task 1: Add per-word lexicon models and validation

**Files:**
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/validate.py`
- Test: `tools/lexicon/tests/test_models.py`
- Test: `tools/lexicon/tests/test_enrich.py`
- Test: `tools/lexicon/tests/test_validate.py`

**Step 1: Write failing tests**

Add tests for:
- a new word-level enrichment record shape keyed by `lexeme_id`
- validation of per-word response rows containing multiple `sense_id` entries
- rejection of invented or missing `sense_id` values

**Step 2: Run targeted tests to verify failure**

Run:
`./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_models.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_validate.py -q`

Expected: failures for missing record types / unsupported validation path.

**Step 3: Implement minimal models and validators**

Add:
- a word-level enrichment record dataclass
- sense-entry validation helpers for per-word responses
- snapshot validation support for the new word-level artifact

**Step 4: Run targeted tests to verify pass**

Run the same pytest command and confirm the new tests pass.

**Step 5: Commit**

`git add tools/lexicon/models.py tools/lexicon/enrich.py tools/lexicon/validate.py tools/lexicon/tests/test_models.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_validate.py`

`git commit -m "feat: add lexicon per-word enrichment models"`

### Task 2: Add per-word prompt/response handling

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write failing tests**

Add tests for:
- prompt construction that includes all selected senses for one word
- response validation that maps each returned entry to a provided `sense_id`
- rejection when the model returns duplicate, missing, or unknown `sense_id` values

**Step 2: Run targeted tests to verify failure**

Run:
`./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`

**Step 3: Implement prompt and parser**

Add:
- `build_word_enrichment_prompt(...)`
- per-word OpenAI-compatible payload validation
- conversion from one word response into normalized word-level artifact rows

**Step 4: Run targeted tests to verify pass**

Run the same pytest command.

**Step 5: Commit**

`git add tools/lexicon/enrich.py tools/lexicon/tests/test_enrich.py`

`git commit -m "feat: add lexicon per-word prompt and parsing"`

### Task 3: Add bounded parallel per-word enrichment mode

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/cli.py`
- Test: `tools/lexicon/tests/test_enrich.py`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing tests**

Add tests for:
- `enrich --mode per_word`
- `--max-concurrency` handling
- deterministic output ordering after parallel execution
- failure summary when one or more word jobs fail
- compatibility of `per_sense` mode

**Step 2: Run targeted tests to verify failure**

Run:
`./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q`

**Step 3: Implement minimal parallel execution**

Add:
- CLI mode switch for `per_sense` vs `per_word`
- bounded per-word worker execution
- stable collection/sorting before JSONL write
- fail-loud behavior for incomplete runs

**Step 4: Run targeted tests to verify pass**

Run the same pytest command.

**Step 5: Commit**

`git add tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py`

`git commit -m "feat: add parallel per-word lexicon enrichment mode"`

### Task 4: Teach compile-export to consume word-level enrichment artifacts

**Files:**
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/validate.py`
- Test: `tools/lexicon/tests/test_compile_export.py`
- Test: `tools/lexicon/tests/test_validate.py`

**Step 1: Write failing tests**

Add tests for:
- compiling from `word_enrichments.jsonl`
- preserving compiled output parity with current schema
- handling missing/partial word-level sense entries cleanly

**Step 2: Run targeted tests to verify failure**

Run:
`./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_validate.py -q`

**Step 3: Implement artifact loading and compile integration**

Add logic that:
- loads per-word artifact rows
- expands them into the same compiled word structure expected by `import-db`
- preserves current `enrichments.jsonl` support for `per_sense`

**Step 4: Run targeted tests to verify pass**

Run the same pytest command.

**Step 5: Commit**

`git add tools/lexicon/compile_export.py tools/lexicon/validate.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_validate.py`

`git commit -m "feat: compile lexicon exports from per-word enrichments"`

### Task 5: Add first-class Mode C compile filtering

**Files:**
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/cli.py`
- Test: `tools/lexicon/tests/test_compile_export.py`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing tests**

Add tests for:
- decisions-aware compile filtering
- `mode_c_safe` preset semantics
- exclusion of `review_required=true`
- inclusion of `deterministic_only` and `auto_accepted=true`
- hard failures on missing decisions file or invalid references

**Step 2: Run targeted tests to verify failure**

Run:
`./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_cli.py -q`

**Step 3: Implement decisions-aware filtering**

Add:
- compile CLI options for decisions input and filter preset
- compile-time filtering by lexeme/review state
- clear zero-row / error summaries

**Step 4: Run targeted tests to verify pass**

Run the same pytest command.

**Step 5: Commit**

`git add tools/lexicon/compile_export.py tools/lexicon/cli.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_cli.py`

`git commit -m "feat: add mode c lexicon compile filtering"`

### Task 6: Improve review API response shape for reviewers

**Files:**
- Modify: `backend/app/api/lexicon_reviews.py`
- Modify: `backend/tests/test_lexicon_reviews_api.py`
- Test: `backend/tests/test_lexicon_reviews_api.py`

**Step 1: Write failing tests**

Add tests for item responses or detail shaping that expose reviewer-usable candidate sense information, including selected sense IDs and readable candidate entries.

**Step 2: Run targeted tests to verify failure**

Run:
`docker compose -f docker-compose.yml exec -T backend pytest tests/test_lexicon_reviews_api.py -q`

**Step 3: Implement response shaping**

Normalize candidate metadata as needed so the frontend can render:
- selected senses
- candidate glosses/labels/POS
- decision hints
- rerank information

**Step 4: Run targeted tests to verify pass**

Run the same pytest command.

**Step 5: Commit**

`git add backend/app/api/lexicon_reviews.py backend/tests/test_lexicon_reviews_api.py`

`git commit -m "feat: expose clearer lexicon review item details"`

### Task 7: Redesign admin review UI for candidate inspection

**Files:**
- Modify: `admin-frontend/src/app/lexicon/page.tsx`
- Modify: `admin-frontend/src/lib/lexicon-reviews-client.ts`
- Test: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Test: `admin-frontend/src/lib/__tests__/lexicon-reviews-client.test.ts`

**Step 1: Write failing tests**

Add tests for:
- readable candidate sense display
- deterministic/reranked selection visibility
- override selection flow
- long candidate metadata rendering without unusable squashing

**Step 2: Run targeted tests to verify failure**

Run:
`npm --prefix admin-frontend test -- --runInBand admin-frontend/src/app/lexicon/__tests__/page.test.tsx admin-frontend/src/lib/__tests__/lexicon-reviews-client.test.ts`

**Step 3: Implement UI improvements**

Refactor the item detail pane into clear sections for:
- summary
- current selection
- candidate comparison
- reviewer override
- save/publish interactions

**Step 4: Run targeted tests to verify pass**

Run the same npm test command.

**Step 5: Commit**

`git add admin-frontend/src/app/lexicon/page.tsx admin-frontend/src/lib/lexicon-reviews-client.ts admin-frontend/src/app/lexicon/__tests__/page.test.tsx admin-frontend/src/lib/__tests__/lexicon-reviews-client.test.ts`

`git commit -m "feat: improve admin lexicon review candidate display"`

### Task 8: Extend E2E and workflow coverage

**Files:**
- Modify: `e2e/tests/smoke/admin-review-flow.smoke.spec.ts` or existing matching file
- Modify: `.github/workflows/ci.yml`
- Modify: relevant local smoke script if required
- Test: local Playwright smoke and affected frontend/backend suites

**Step 1: Write or extend failing smoke expectations**

Add smoke assertions that candidate detail is visible and reviewer actions still work after the UI/API changes.

**Step 2: Run targeted E2E to verify failure**

Run the existing targeted admin smoke command used by the repo for lexicon review.

**Step 3: Implement required E2E/workflow updates**

Adjust selectors, setup, or workflow commands only as needed to cover the new behavior.

**Step 4: Run targeted E2E to verify pass**

Run the same targeted smoke command and confirm pass.

**Step 5: Commit**

`git add e2e .github/workflows/ci.yml`

`git commit -m "test: extend admin lexicon review smoke coverage"`

### Task 9: Update operator docs and project status

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`
- Modify: any additional decision/runbook docs that the implementation requires

**Step 1: Update docs**

Document:
- per-word mode
- concurrency usage
- Mode C compile filtering
- admin review improvements
- verification evidence and rollout guidance

**Step 2: Run doc-adjacent verification**

Run the exact commands referenced by the docs where practical and verify wording matches the implementation.

**Step 3: Commit**

`git add tools/lexicon/README.md tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md`

`git commit -m "docs: document per-word lexicon mode and mode c workflow"`

### Task 10: Full verification and branch completion

**Files:**
- Verify all changed files from prior tasks

**Step 1: Run lexicon tool tests**

Run:
`./.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`

**Step 2: Run backend tests**

Run:
`docker compose -f docker-compose.yml exec -T backend pytest tests/test_lexicon_reviews_api.py -q`

**Step 3: Run admin frontend checks**

Run:
`npm --prefix admin-frontend run lint`

Run:
`npm --prefix admin-frontend test -- --runInBand`

Run:
`NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build`

**Step 4: Run targeted E2E/smoke**

Run the targeted admin lexicon review smoke and, if stable, the full local smoke script.

**Step 5: Run workflow/config verification**

Run:
`ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "ci.yml OK"'`

**Step 6: Prepare branch for PR**

Use the repo PR workflow to:
- review `git diff --stat`
- commit any final fixes
- create PR
- wait for checks
- merge
- clean the worktree and remote/local branch

