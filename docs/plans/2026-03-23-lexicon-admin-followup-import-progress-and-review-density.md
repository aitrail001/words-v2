# 2026-03-23 Lexicon Admin Follow-up: Import Progress And Review Density

## Scope

- Add visible `Import DB` progress without moving execution to the worker container yet.
- Reduce `DB Inspector` browse density to `10` rows per page.
- Make `Compiled Review` and `JSONL Review` more visually consistent and reduce entry-rail height pressure.

## Decisions

1. Keep import execution in `backend` for this slice.
   - Use a backend-managed background job registry rather than a worker migration.
   - This makes "browse away and come back" work in the same backend process.
   - It does not survive backend restarts; worker migration remains the long-term answer.

2. Reuse the compiled payload to derive a shared reviewer summary.
   - Avoid widening backend review contracts again just to support the summary panel.
   - Keep JSONL Review using persisted `review_summary` where present, with payload-derived fallback.

3. Tighten list rails aggressively.
   - `DB Inspector`: `10` rows per page.
   - `Compiled Review` / `JSONL Review`: `5` rows per page.

## Implementation Steps

1. Add backend lexicon import job/status contract plus progress callback support in `tools/lexicon/import_db.py`.
2. Update `Import DB` page/client to start a job, poll, and reconnect from browser storage.
3. Add shared reviewer-summary derivation/component and apply it to both review pages.
4. Tighten pagination and verify with targeted backend/frontend tests plus frontend lint/build.
