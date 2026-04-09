# Lexicon 30K Rollout + Schema Separation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the lexicon tool operationally reliable enough for top-30K word generation/import and separate lexicon/reference data into a dedicated Postgres `lexicon` schema.

**Architecture:** Use a phased delivery model. First isolate lexicon-owned persistence into a dedicated schema without introducing a second DB service. Then harden the large-run enrichment pipeline with checkpoint/resume behavior so 1K -> 5K -> 30K runs are operationally safe. Finally, validate ambiguous-tail adjudication at rollout scale and document/operatorize the recommended adoption path.

**Tech Stack:** Python 3.13, SQLAlchemy, Alembic, PostgreSQL schemas, pytest, existing lexicon CLI/admin/backend stack, GitHub PR workflow.

---

## PR Sequence

1. **PR A — Lexicon schema separation**
   - Move lexicon-owned tables into Postgres schema `lexicon`
   - Update models, migrations, import path, and backend query paths
   - Preserve current application DB URL / server; only logical separation changes

2. **PR B — Large-run enrichment hardening**
   - Add checkpointed per-word output, resumable enrichment runs, and safer operator ergonomics
   - Ensure 1K -> 5K -> 30K runs do not lose completed work on mid-run failure

3. **PR C — Ambiguous-tail rollout + operator adoption**
   - Add larger-scale ambiguous-tail evaluation/reporting
   - Run broader bounded adjudication experiments and document recommended adoption policy

---

### Task 1: Create PR A worktree and implementation plan

**Files:**
- Create: `docs/plans/2026-03-12-lexicon-schema-separation-pr-a.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Create fresh worktree branch for PR A.
2. Inspect current lexicon-owned models/migrations/import paths.
3. Write PR A plan with exact files, tests, and migration notes.
4. Implement with TDD where practical.
5. Verify, commit, PR, merge, clean up.

### Task 2: Deliver PR A — dedicated `lexicon` schema

**Expected file areas:**
- `backend/app/models/*.py` for lexicon-owned tables
- `backend/alembic/versions/*.py`
- `tools/lexicon/import_db.py`
- backend tests and lexicon import tests
- docs/operator docs/status

**Acceptance criteria:**
- Lexicon-owned tables use `lexicon` schema consistently
- Alembic creates/migrates schema safely
- Foreign keys within lexicon schema resolve correctly
- Cross-schema references to runtime tables still work where needed
- `import-db` continues to function

### Task 3: Create PR B worktree and implementation plan

**Files:**
- Create: `docs/plans/2026-03-12-lexicon-large-run-hardening-pr-b.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Create fresh worktree branch after PR A merges.
2. Inspect current enrichment write behavior and failure modes.
3. Write PR B plan with checkpoint/resume design.
4. Implement incrementally with focused tests.
5. Verify, commit, PR, merge, clean up.

### Task 4: Deliver PR B — checkpoint/resume hardening

**Expected file areas:**
- `tools/lexicon/enrich.py`
- `tools/lexicon/cli.py`
- lexicon tests for resume/checkpoint behavior
- operator docs/status

**Acceptance criteria:**
- Per-word runs persist completed work incrementally
- Failed runs can resume without regenerating completed lexemes
- Operator-visible metadata records run identity/progress clearly
- Docs explain 1K -> 5K -> 30K run strategy

### Task 5: Create PR C worktree and implementation plan

**Files:**
- Create: `docs/plans/2026-03-12-lexicon-ambiguous-tail-rollout-pr-c.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Create fresh worktree branch after PR B merges.
2. Inspect current adjudication/evaluation/reporting path.
3. Write PR C plan for rollout-scale operator use.
4. Implement missing reporting/commands/docs.
5. Run bounded broader experiments, verify, commit, PR, merge, clean up.

### Task 6: Deliver PR C — operator adoption for ambiguous tail

**Expected file areas:**
- `tools/lexicon/form_adjudication.py`
- `tools/lexicon/cli.py`
- possibly new reporting helpers/tests/docs
- operator docs/status

**Acceptance criteria:**
- Operators can quantify ambiguous-tail size on larger runs
- Adjudication outputs are auditable and easy to review
- Docs recommend when to use deterministic-only vs adjudication
- Evidence for broader rollout is recorded in `docs/status/project-status.md`

### Task 7: Final 30K-readiness closure

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`

**Acceptance criteria:**
- Lexicon tool has a documented and reproducible operator path toward 30K
- Schema separation is complete
- Large-run resilience is implemented
- Ambiguous-tail operator guidance is documented
- Remaining non-blocking gaps are explicitly captured as TODO/follow-up items
