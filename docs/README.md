# Documentation

## Structure

```
docs/
├── plans/        # Implementation plans (YYYY-MM-DD-<topic>.md)
├── decisions/    # Architecture Decision Records (ADR-NNN-<topic>.md)
├── lessons/      # Lessons learned during rebuild (YYYY-MM-DD-<topic>.md)
├── runbooks/     # Operator runbooks (pre-prod readiness, rollback, verification)
└── api/          # API documentation (auto-generated + manual)
```

## Conventions

### Plans (`docs/plans/`)
- One file per planning session or major feature
- Naming: `YYYY-MM-DD-<topic>.md`
- Include: requirements, phases, risks, dependencies, acceptance criteria
- Status header: `DRAFT`, `APPROVED`, `IN_PROGRESS`, `COMPLETED`, `SUPERSEDED`
- Link to related ADRs and lessons learned

### Architecture Decision Records (`docs/decisions/`)
- One file per significant technical decision
- Naming: `ADR-NNN-<topic>.md` (sequential numbering)
- Template: Context → Decision → Consequences → Status
- Status: `PROPOSED`, `ACCEPTED`, `DEPRECATED`, `SUPERSEDED`
- Never delete — mark as superseded with link to replacement
- Current governance policy: `docs/decisions/ADR-002-branch-governance.md`

### Lessons Learned (`docs/lessons/`)
- Capture what went wrong, why, and what to do differently
- Naming: `YYYY-MM-DD-<topic>.md`
- Template: What happened → Why it failed → What to do → Files affected
- Reference the originals in `LESSONS_LEARNED.md` (prototype lessons)

### API Documentation (`docs/api/`)
- OpenAPI spec auto-generated from FastAPI
- Manual docs for complex flows (import pipeline, review algorithm, etc.)

### Runbooks (`docs/runbooks/`)
- Pre-prod readiness: `docs/runbooks/preprod-readiness-checklist.md`
- Rollback procedure: `docs/runbooks/rollback.md`
