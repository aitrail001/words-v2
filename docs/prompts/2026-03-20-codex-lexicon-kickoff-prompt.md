# Codex Kickoff Prompt — Lexicon Batch Enrichment Tool

Paste everything below into Codex from the repository root.

---

You are the technical lead and implementation agent for the `words-v2` lexicon batch enrichment project.

Your job is to design, implement, test, review, and document a production-grade batch-first enrichment backend for `tools/lexicon`, using the checked-in design docs and configured custom subagents.

## Hard requirements

1. Preserve the current deterministic-first pipeline and existing commands:
   - `build-base`
   - `enrich`
   - `validate`
   - `compile-export`
   - `import-db`

2. Add a production-grade Batch API execution backend with new commands:
   - `batch-prepare`
   - `batch-submit`
   - `batch-status`
   - `batch-ingest`
   - `batch-retry`
   - `batch-qc`
   - `phrase-build-base`
   - `reference-build-base`
   - `review-export`
   - `review-apply`

3. Support:
   - ~30k words
   - ~5k phrases / phrasal verbs / idioms
   - lightweight learner reference entries such as names, place names, demonyms, titles, and common abbreviations
   - out-of-order batch outputs
   - resumable runs
   - deterministic retries
   - automatic validation
   - QC and human review
   - future re-enrichment and schema evolution

4. Keep JSONL as the canonical offline artifact format.

5. Use strict structured outputs for enrichment and QC contracts.

6. Add unit tests, scenario tests, and e2e tests. Do not use live API calls in tests.

7. Document the final operator workflow in `tools/lexicon/docs/batch.md`.

8. Keep lightweight reference entries intentionally simple:
   - focus on pronunciation
   - localized display form / translation handling
   - brief description
   - optional learner tip
   - do not force full word-style or phrase-style enrichment on them

9. Keep learner-priority public-life vocabulary such as housing, work, healthcare, transport, and immigration terms inside the main word corpus, but support curated seed packs so operators can prioritize them.

## Model and runtime expectations

- For Codex subagents, use the configured agent model assignments already defined in `.codex/agents/`.
- For the runtime enrichment tool itself, default the low-cost batch generator model to `gpt-5-mini`.
- Accept a configured override such as `gpt-5.4-mini` if the operator environment exposes it.
- Reserve `gpt-5.4` for escalation, repair, or high-risk QC tails.

## First actions you must take

1. Read these checked-in files first:
   - `docs/plans/2026-03-20-lexicon-batch-tool-design.md`
   - `docs/plans/2026-03-20-lexicon-batch-implementation-plan.md`
   - `tools/lexicon/README.md`
   - `tools/lexicon/cli.py`
   - `tools/lexicon/enrich.py`
   - `SCHEMA_REFERENCE.md`

2. Explicitly spawn and use these subagents:
   - `repo_analyst`
   - `design_planner`
   - `batch_api_engineer`
   - `schema_validation_engineer`
   - `test_engineer`
   - `qc_review_engineer`

3. Use `reviewer` near the end for a final read-only review before you conclude.

4. In Milestone 0, create these repo skills so future Codex runs can reuse the workflow:
   - `.agents/skills/lexicon-batch-contracts/SKILL.md`
   - `.agents/skills/lexicon-schema-guardrails/SKILL.md`
   - `.agents/skills/lexicon-test-harness/SKILL.md`

## Working style

- Work stage by stage according to `docs/plans/2026-03-20-lexicon-batch-implementation-plan.md`.
- Make the smallest defensible change per stage.
- Add or update tests in the same stage as the implementation.
- Reconcile your plan continuously; do not leave “pending” or “in progress” items at the end.
- Prefer extracting reusable helpers from existing code over rewriting from scratch.
- Keep the batch client thin and mockable.
- Keep operational state in snapshot artifacts, not the app DB.
- Keep DB writes behind `import-db`.
- Never rely on batch output order; always use `custom_id`.
- Never overwrite accepted outputs destructively; append attempts and select latest accepted record at compile time.
- Treat `reference` as a third entry family, not as a special case hidden inside the word or phrase family.

## Required deliverables

By the end of the run, the repository must contain:

1. A working batch execution backend for lexicon enrichment.
2. Phrase / idiom / phrasal verb support.
3. Lightweight reference-entry support for names, places, titles, demonyms, and common abbreviations.
4. Strict schema validation and QC verdict support.
5. Retry / repair / escalation flows.
6. Review queue + manual override flow.
7. Updated compile/export and import-db support for the richer schema.
8. Full offline tests and fixtures.
9. Operator docs in `tools/lexicon/docs/batch.md`.
10. Repo skills under `.agents/skills/...`.

## Definition of done

Do not conclude until all of these are true:

- all touched Python code formats cleanly according to repo conventions
- relevant tests pass locally without live API calls
- new CLI commands are wired and documented
- current CLI behavior is preserved or any intentional break is explicitly documented
- out-of-order batch result ingestion is proven in tests
- retries are proven in tests
- QC and override layering are proven in tests
- phrase support is proven in tests
- reference-entry support is proven in tests
- reviewer has been run and any critical findings are fixed

## Final response format

When you finish, return:

1. what changed
2. which stages completed
3. which tests ran and passed
4. any remaining non-critical follow-ups
5. the exact operator entrypoint for running the new pipeline

Begin now.
