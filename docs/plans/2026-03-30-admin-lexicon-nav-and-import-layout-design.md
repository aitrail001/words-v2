# Admin Lexicon Nav And Import Layout Design

## Goal

Refresh the admin lexicon navigation and import-page layout so operators can move between Voice and DB tasks faster, while keeping the existing page separation and runtime contracts intact.

## Approved Scope

- Top navigation should read: `Home / Lexicon Ops / Voice / Enrichment Review / DB / Logout`.
- Voice pages should expose a section submenu with:
  - `Storage`
  - `Voice Runs`
  - `Voice DB Import`
- DB pages should expose a section submenu with:
  - `Enrichment Import`
  - `DB Inspector`
- Enrichment review pages should expose a section submenu with:
  - `Compiled Review`
  - `JSONL Review`
- `Lexicon Voice Import` and `Lexicon Import to Final DB` remain separate pages.
- Voice storage and voice runs must become separate pages.
- Both import pages should use a more compact operator layout, with overlapping fields arranged into one or two tight rows.
- After a storage-policy edit is applied, the `Current DB storage policies` display must refresh so the live DB-backed policy state shown on the page matches the latest saved config.

## Non-Goals

- No route restructuring or page merge.
- No backend storage-policy rewrite contract changes.
- No import runtime logic changes.
- No DB inspector schema or playback contract changes in this slice.

## Design

### Navigation

Keep the global authenticated nav compact and high-level. Replace the current lexicon-specific link sprawl with two category links:

- `Voice` routes to `/lexicon/voice`
- `DB` routes to `/lexicon/import-db`

Retain `Lexicon Ops` and a single `Enrichment Review` entry that points to the current compiled review path.

### Section Submenus

Introduce a small lexicon section subnav component that can be reused by lexicon pages. It will render a short tab-like link row under the page hero:

- Voice section pages:
  - `/lexicon/voice-storage` highlights `Storage`
  - `/lexicon/voice-runs` highlights `Voice Runs`
  - `/lexicon/voice-import` highlights `Voice DB Import`
- DB section pages:
  - `/lexicon/import-db` highlights `Enrichment Import`
  - `/lexicon/db-inspector` highlights `DB Inspector`
- Enrichment review pages:
  - `/lexicon/compiled-review` highlights `Compiled Review`
  - `/lexicon/jsonl-review` highlights `JSONL Review`

This keeps separate pages but makes the navigation hierarchy explicit.

### Voice Routing

- Top-level `Voice` nav should target `/lexicon/voice-runs`.
- `/lexicon/voice` should redirect to `/lexicon/voice-runs` for compatibility.
- `Open Voice Admin` from Lexicon Ops should target `/lexicon/voice-import`.

### Compact Import Layouts

For both import pages, keep the existing fields and actions, but move them into denser grids:

- Voice import:
  - row 1: manifest path, language
  - row 2: conflict handling, error handling, dry run/import actions
- Final DB import:
  - row 1: input path, source reference, language
  - row 2: conflict handling, error handling, dry run/import actions

No workflow semantics change. The layout only reduces wasted horizontal/vertical space.

### Policy Refresh

The voice page already loads current DB storage policies independently. After a successful non-dry-run apply action, it should trigger a fresh policy fetch and replace the displayed list. The page should not rely on stale local form state as evidence of the new policy.

## Testing

- Update nav tests to assert the new top-level labels.
- Add/adjust voice page tests to assert the submenu and post-apply storage-policy refresh.
- Add/adjust import-page tests to assert the compact form structure and unchanged actions.

## Risks

- In-page `Voice Runs` as a submenu item is slightly different from route-based submenu items. Keep it explicit in the UI and tests.
- The policy refresh must happen only after a successful apply, not after dry run.
