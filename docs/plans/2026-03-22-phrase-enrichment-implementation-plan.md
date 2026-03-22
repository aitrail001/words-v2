# Phrase Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add curated phrase inventory build, strict phrase enrichment, and shared review/import support so phrasal verbs and idioms flow through the same lexicon admin pipeline as words.

**Architecture:** Build a phrase inventory stage that converts reviewed CSVs into `phrases.jsonl`, then extend the existing enrichment runtime to support phrase rows with a strict phrase-specific `senses[]` contract. Keep compiled artifacts and admin review/import aligned to the existing lexicon path by persisting rich phrase payload on `phrase_entries` rather than inventing a separate phrase review subsystem.

**Tech Stack:** Python CLI tooling, strict JSON schema structured outputs, JSONL compiled artifacts, FastAPI backend/admin APIs, SQLAlchemy/Alembic, pytest, existing lexicon admin frontend.

---

### Task 1: Add phrase source inventory fixtures and mapping tests

**Files:**
- Modify: `tools/lexicon/tests/test_phrase_pipeline.py`
- Create: `tools/lexicon/tests/test_phrase_inventory.py`
- Check: `data/lexicon/phrasals/reviewed_phrasal_verbs.csv`
- Check: `data/lexicon/idioms/reviewed_idioms.csv`

**Step 1: Write the failing tests**

Add tests that cover:

- mapping reviewed phrasal labels to `phrasal_verb`
- mapping `idiom` to `idiom`
- mapping other idiom-list labels to `multiword_expression`
- preserving raw label and source metadata in `source_provenance` / `seed_metadata`
- deduping repeated normalized phrases across multiple sources

**Step 2: Run the tests to verify failure**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_phrase_inventory.py tools/lexicon/tests/test_phrase_pipeline.py -q
```

Expected: failures for missing inventory builder/mapping behavior.

**Step 3: Implement the minimal inventory normalization helpers**

Likely files:

- `tools/lexicon/phrase_pipeline.py`
- optional new helper module such as `tools/lexicon/phrase_inventory.py`

Implement:

- CSV row loading
- reviewed-label mapping
- provenance normalization
- deterministic dedupe by normalized form

**Step 4: Run the tests to verify pass**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add tools/lexicon/phrase_pipeline.py tools/lexicon/phrase_inventory.py tools/lexicon/tests/test_phrase_inventory.py tools/lexicon/tests/test_phrase_pipeline.py
git commit -m "feat(lexicon): add phrase inventory normalization"
```

### Task 2: Add a CLI phrase-build command for one or more CSV sources

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Check: `tools/lexicon/README.md`
- Check: `tools/lexicon/OPERATOR_GUIDE.md`

**Step 1: Write the failing CLI tests**

Add tests that cover:

- `build-phrases` or similarly named command accepting multiple CSV paths
- writing `phrases.jsonl`
- preserving merged provenance on duplicate phrases
- emitting summary counts

**Step 2: Run the tests to verify failure**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q
```

Expected: missing command or output mismatch failures.

**Step 3: Implement the CLI command**

Modify `tools/lexicon/cli.py` to:

- accept one or more phrase CSV source paths
- create a snapshot id
- write `phrases.jsonl`
- print structured summary output

**Step 4: Run tests to verify pass**

Run the CLI test command again and confirm pass.

**Step 5: Commit**

```bash
git add tools/lexicon/cli.py tools/lexicon/tests/test_cli.py
git commit -m "feat(lexicon): add phrase inventory build command"
```

### Task 3: Expand the strict phrase enrichment schema to use `senses[]`

**Files:**
- Modify: `tools/lexicon/schemas/phrase_enrichment_schema.py`
- Modify: `tools/lexicon/tests/test_contract_schemas.py`
- Create: `tools/lexicon/tests/test_phrase_enrichment_schema.py`

**Step 1: Write the failing schema tests**

Add tests that require:

- top-level `senses`
- per-sense `definition`, `part_of_speech`, `examples`, `grammar_patterns`, `usage_note`, `translations`
- bounded sense count
- at least one example per sense
- normalized phrase-kind validation

**Step 2: Run tests to verify failure**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_contract_schemas.py tools/lexicon/tests/test_phrase_enrichment_schema.py -q
```

Expected: failures because the schema still uses the older flat structure.

**Step 3: Implement the schema and normalization**

Update `tools/lexicon/schemas/phrase_enrichment_schema.py` to:

- define a strict phrase `senses[]` contract
- normalize sense-level translations/examples
- retain top-level `confidence`
- keep `phrase_kind` enum aligned to the minimal v1 taxonomy

**Step 4: Run tests to verify pass**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add tools/lexicon/schemas/phrase_enrichment_schema.py tools/lexicon/tests/test_contract_schemas.py tools/lexicon/tests/test_phrase_enrichment_schema.py
git commit -m "feat(lexicon): align phrase schema with word-style senses"
```

### Task 4: Wire phrase rows into realtime enrichment on the shared runtime

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/validate.py`
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_validate.py`
- Check: `tools/lexicon/tests/test_unified_enrichment_flow.py`

**Step 1: Write the failing realtime enrichment tests**

Add tests that cover:

- phrase row detection from `phrases.jsonl`
- phrase-specific prompt/schema selection
- accepted phrase output materialization
- failure/regenerate behavior on invalid phrase payloads
- validation of compiled phrase rows with senses

**Step 2: Run tests to verify failure**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_unified_enrichment_flow.py -q
```

Expected: failures for missing phrase runtime handling.

**Step 3: Implement minimal realtime phrase runtime**

Modify the enrichment runtime to:

- load phrase seed rows
- send phrase prompt/input payloads
- apply the phrase strict schema
- normalize accepted phrase outputs into snapshot/compiled shape
- write phrase failure sidecars compatible with regenerate flow

**Step 4: Run tests to verify pass**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add tools/lexicon/enrich.py tools/lexicon/models.py tools/lexicon/validate.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_unified_enrichment_flow.py
git commit -m "feat(lexicon): add realtime phrase enrichment"
```

### Task 5: Keep compile/export and review outputs aligned for phrase rows

**Files:**
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/review_materialize.py`
- Modify: `tools/lexicon/review_prep.py`
- Modify: `tools/lexicon/tests/test_compile_export.py`
- Modify: `tools/lexicon/tests/test_review_materialize.py`
- Modify: `tools/lexicon/tests/test_review_prep.py`

**Step 1: Write the failing artifact/review tests**

Add tests that require:

- `phrases.enriched.jsonl` rows to include rich phrase payload
- review prep to expose phrase fields needed in admin review
- reviewed output materialization to preserve phrase payload cleanly

**Step 2: Run tests to verify failure**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_review_materialize.py tools/lexicon/tests/test_review_prep.py -q
```

Expected: failures because phrase payload is too thin or dropped.

**Step 3: Implement the minimal export/review compatibility changes**

Update compile/review helpers so phrase rows:

- retain sense-level payload
- retain `seed_metadata`
- render enough structure for shared admin review
- remain compatible with existing reviewed output paths

**Step 4: Run tests to verify pass**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add tools/lexicon/compile_export.py tools/lexicon/review_materialize.py tools/lexicon/review_prep.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_review_materialize.py tools/lexicon/tests/test_review_prep.py
git commit -m "feat(lexicon): keep phrase artifacts aligned with review flow"
```

### Task 6: Extend phrase DB persistence for rich compiled payload

**Files:**
- Modify: `backend/app/models/phrase_entry.py`
- Create: `backend/alembic/versions/<new_revision>_expand_phrase_entries_for_enrichment.py`
- Modify: `tools/lexicon/import_db.py`
- Modify: `backend/tests/test_lexicon_phrase_reference_models.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write the failing DB/import tests**

Add tests that require:

- `PhraseEntry` to persist `compiled_payload`
- `seed_metadata`
- `confidence_score`
- `generated_at`
- import-db phrase upserts to preserve rich phrase payload

**Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_phrase_reference_models.py -q
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q
```

Expected: failures for missing columns or import persistence.

**Step 3: Implement the DB model and import changes**

Update the SQLAlchemy model, Alembic migration, and `import_db` phrase branch so approved phrase compiled rows persist the enriched payload on `phrase_entries`.

**Step 4: Run tests to verify pass**

Run the same pytest commands and confirm pass.

**Step 5: Commit**

```bash
git add backend/app/models/phrase_entry.py backend/alembic/versions/*.py tools/lexicon/import_db.py backend/tests/test_lexicon_phrase_reference_models.py tools/lexicon/tests/test_import_db.py
git commit -m "feat(lexicon): persist rich phrase payload in phrase entries"
```

### Task 7: Expose phrase rows cleanly in admin review/import surfaces

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Modify: `backend/app/api/lexicon_jsonl_reviews.py`
- Modify: `backend/app/api/lexicon_ops.py`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Modify: `backend/tests/test_lexicon_jsonl_reviews_api.py`
- Modify: `backend/tests/test_lexicon_ops_api.py`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/*`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/*`
- Modify: `admin-frontend/src/app/lexicon/import-db/*`

**Step 1: Write the failing backend/admin tests**

Add tests that require:

- shared review APIs to surface phrase sense payload
- shared UI to render phrase-specific fields without separate workflow
- Import DB UI to continue importing approved phrase rows through the same action path

**Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py backend/tests/test_lexicon_ops_api.py -q
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: failures or missing phrase rendering coverage.

**Step 3: Implement minimal shared UI/API support**

Extend existing entry-type branching so phrase rows:

- show phrase-kind and display form clearly
- render senses/examples/translations in review
- remain importable through the current path

**Step 4: Run tests to verify pass**

Run the same backend/admin test commands and confirm pass.

**Step 5: Commit**

```bash
git add backend/app/api/lexicon_compiled_reviews.py backend/app/api/lexicon_jsonl_reviews.py backend/app/api/lexicon_ops.py backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py backend/tests/test_lexicon_ops_api.py admin-frontend/src/app/lexicon/compiled-review admin-frontend/src/app/lexicon/jsonl-review admin-frontend/src/app/lexicon/import-db
git commit -m "feat(admin): review and import phrase entries in shared workflow"
```

### Task 8: Add batch phrase support on the same contract

**Files:**
- Modify: `tools/lexicon/batch_prepare.py`
- Modify: `tools/lexicon/batch_ingest.py`
- Modify: `tools/lexicon/tests/test_batch_prepare.py`
- Modify: `tools/lexicon/tests/test_batch_ingest.py`
- Check: `tools/lexicon/tests/test_config.py`

**Step 1: Write the failing batch tests**

Add tests that require:

- phrase batch request generation using the phrase schema
- phrase batch ingest into accepted/review/regenerate outputs
- parity with realtime phrase materialization

**Step 2: Run tests to verify failure**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_batch_prepare.py tools/lexicon/tests/test_batch_ingest.py -q
```

Expected: failures for unsupported phrase batch entries.

**Step 3: Implement the minimal batch path**

Extend batch prepare/ingest to support phrase rows with the same phrase prompt/schema/materialization used by realtime.

**Step 4: Run tests to verify pass**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add tools/lexicon/batch_prepare.py tools/lexicon/batch_ingest.py tools/lexicon/tests/test_batch_prepare.py tools/lexicon/tests/test_batch_ingest.py
git commit -m "feat(lexicon): add batch phrase enrichment support"
```

### Task 9: Update operator docs and project status with verification evidence

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Write the doc/status updates**

Document:

- phrase inventory source flow
- realtime and batch support
- shared admin review/import path
- exact verification commands and outcomes

**Step 2: Run final verification**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_phrase_reference_models.py backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py backend/tests/test_lexicon_ops_api.py -q
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: all targeted tests pass with fresh output.

**Step 3: Update `project-status.md`**

Add a dated entry with:

- phrase inventory build implementation
- phrase realtime/batch support status
- admin alignment status
- verification evidence

**Step 4: Commit**

```bash
git add tools/lexicon/README.md tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md
git commit -m "docs(lexicon): document phrase enrichment rollout"
```
