# Review SRS Invariant Audit Findings

**Date:** 2026-04-15
**Branch:** feat/review-srs-invariant-audit
**Source spec:** `docs/superpowers/specs/2026-04-15-review-srs-invariant-audit-design.md`

## Invariant Checklist

- [ ] learner `learning` entries always have coherent next-step UI
- [ ] queue, detail, and admin schedule meaning agree
- [ ] admin diagnostics contain no dead legacy fields
- [ ] detail endpoints and queue endpoints serialize consistent review state
- [ ] gates cover every confirmed inconsistency class

## Findings

### Live audit scope
- **Audit command:** `bash -lc 'source .venv-backend/bin/activate && set -a && source .env.localdev && set +a && python scripts/debug/review_srs_invariant_audit.py'`
- **User:** `admin@admin.com`
- **Observed summary:** `review_states=10`, `review_events=0`, `bucket_counts={'1d': 10}`, `target_type_counts={'entry': 5, 'meaning': 5}`
- **Timezone:** `Australia/Melbourne`

### Learning items with no canonical next-step schedule
- **Type:** bug
- **Surface:** backend + learner
- **Evidence:** `scripts/debug/review_srs_invariant_audit.py` reported `missing_canonical_schedule` and `learning_state_without_next_step` for `judicial`, `the`, and `lgbt`.
- **Reproduction:** run `bash -lc 'source .venv-backend/bin/activate && set -a && source .env.localdev && set +a && python scripts/debug/review_srs_invariant_audit.py'`
- **Expected invariant:** learner `learning` entries always have coherent next-step UI
- **Notes:** six active states have `srs_bucket='1d'` while all of `due_review_date`, `min_due_at_utc`, and `recheck_due_at` are `NULL`. The `judicial` rows are concrete examples:
  - target state `6ace1e5c-008a-48f1-9890-1413c83a30ad` for `judicial` has `target_type='meaning'`, `target_id='4ac30516-8c20-4a47-9809-af17001d4afa'`, and no schedule fields.
  - entry state `e506d911-1829-4aed-93d6-1ef7023b8755` for `judicial` has `target_type=NULL`, `target_id=NULL`, and no schedule fields.
  - both rows still map to learner status `learning`.

### Sibling schedule population is inconsistent across entry review-state pairs
- **Type:** bug
- **Surface:** backend
- **Evidence:** `scripts/debug/review_srs_invariant_audit.py` reported `sibling_schedule_population_inconsistent` with two live classes:
  - `no_sibling_has_schedule`: `judicial`, `the`, `lgbt`
  - `all_siblings_have_schedule`: `persistence`, `versus`
- **Reproduction:** run the audit command above and inspect the `classes` / `examples` payload under `sibling_schedule_population_inconsistent`.
- **Expected invariant:** detail endpoints and queue endpoints serialize consistent review state
- **Notes:** the audit no longer treats entry-level plus meaning-level siblings as inherently invalid. The evidence-based issue is narrower: otherwise similar sibling row shapes are not populated consistently. Three sibling pairs have no canonical schedule on either row, while two sibling pairs have the expected canonical `Australia/Melbourne` `1d` schedule on both rows.

### Canonical schedule fields are correct only on the later-created duplicates
- **Type:** bug
- **Surface:** backend + admin
- **Evidence:** the audit reported no `canonical_schedule_mismatch` findings, but the only rows with valid schedule fields are the later-created duplicates for `persistence` and `versus`.
- **Reproduction:** run the audit command above and compare:
  - `persistence` entry state `4a73004a-2bbe-47ef-a076-4f34d693a379` and meaning state `661845ba-945d-482d-a5c9-8b0b10883833`
  - `versus` entry state `a640393b-5fba-4e17-ba41-fa988893248a` and meaning state `a8abf0b5-4da5-4c03-9c59-9854e2bfeda5`
- **Expected invariant:** queue, detail, and admin schedule meaning agree
- **Notes:** those four rows have the expected `Australia/Melbourne` canonical schedule (`due_review_date='2026-04-16'`, `min_due_at_utc='2026-04-15T18:00:00+00:00'` for a `1d` bucket), while the earlier `judicial`, `the`, and `lgbt` duplicates are missing the same fields entirely. The split suggests schedule population is inconsistent across creation paths or over time.
