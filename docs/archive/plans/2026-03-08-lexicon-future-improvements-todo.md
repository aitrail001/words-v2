# Lexicon Future Improvements TODO

These items are intentionally deferred after the lexicon tool is closed as a **working local-DB admin tool**.

## Working tool is already expected to cover

- offline snapshot generation
- optional review-prep flow
- learner-facing enrichment
- compiled export
- import into the local DB
- backend API inspection of imported learner-facing data

## Deferred improvements

### Validation and import hardening
- add stricter compiled-schema validation beyond current top-level/example checks
- add explicit review-status gating before compile/import for review-controlled runs
- add built-in `import-db` pre-validation enforcement or explicit `--skip-validate` semantics
- add stronger live DB idempotency/integration coverage in automated CI

### Review and publishing unification
- make staged review publish delegate to the same learner-enrichment importer/writeback path
- retire or feature-flag the narrower minimal publish projection once the importer-backed path is unified
- add richer diff summaries between staged review decisions and compiled/imported DB state

### Admin experience
- add admin frontend review UI
- add dedicated operator/admin read screens for staged review and imported enrichment inspection
- add stronger RBAC/admin-only authorization for review and enrichment inspection surfaces

### Content/model expansion
- phrase and idiom support
- phrase linking / `meaning_phrases`
- fuller learner-facing meaning fields not yet modeled or projected publicly
- broader curation path for non-WordNet items and missing lexemes

### Operational hardening
- automated live Postgres import smoke in CI
- checkpoint/resume for large enrichment runs
- retry/backoff, rate limits, budget caps, and batch controls
- richer run manifests, failure taxonomy, and artifact retention
- automated quality gates over holdout benchmark sets
