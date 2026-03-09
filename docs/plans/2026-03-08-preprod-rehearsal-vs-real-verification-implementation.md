# Preprod Rehearsal vs Real Verification

**Goal:** Clarify that the existing GitHub Actions preprod-readiness workflow is a disposable rehearsal against an ephemeral Docker stack, and document a separate real preprod verification path for persistent deployed environments and populated databases.

**Scope:**
- rename/reword the current workflow and checklist so they stop implying use of a real preprod DB
- add a dedicated runbook for real preprod verification against an existing environment
- document where a bounded lexicon smoke fits in real preprod verification
- update live project status with the clarification

**Out of scope:**
- adding a real preprod deployment workflow
- wiring GitHub Actions directly to a persistent preprod environment
- changing deploy infrastructure or secrets

**Implementation steps:**
1. Update `.github/workflows/preprod-readiness.yml` display text to say `rehearsal` and reflect disposable Docker-backed scope.
2. Update `docs/runbooks/preprod-readiness-checklist.md` to distinguish rehearsal from real preprod verification.
3. Add `docs/runbooks/real-preprod-verification.md` covering persistent DB/app expectations, migration/rollback evidence, and bounded lexicon smoke guidance.
4. Update `docs/runbooks/release-promotion.md` links/wording if needed so promotion points to the right runbook for real preprod checks.
5. Record the clarification in `docs/status/project-status.md`.
6. Run lightweight verification on changed YAML/Markdown files.

**Verification target:**
- YAML parses successfully
- changed Markdown/runbook files exist and reference each other coherently
- status entry reflects the clarified governance split
