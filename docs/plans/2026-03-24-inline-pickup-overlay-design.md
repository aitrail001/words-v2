# Inline Pickup Overlay Design

## Goal

Replace full-page navigation for inline linked learner terms with a compact quick-look overlay that keeps the learner on the current detail card until they explicitly choose `Look up`.

## Scope

- Applies to inline learner links in:
  - example sentences
  - sense links (`synonyms`, `antonyms`, `collocations`)
  - confusable words
  - derivations
- Non-matching terms remain non-interactive.
- The overlay uses the existing learner detail API and renders a compact subset of the full detail page.

## Interaction Model

- Clicking an inline linked term opens a centered modal overlay.
- The base detail page remains visible behind the overlay.
- Overlay content:
  - entry title
  - pronunciation
  - part of speech
  - translation
  - short definition
  - optional usage note / example
  - `Look up` button to go to the full standalone word/phrase page
  - `Got it!` button to dismiss and return to the current entry

## Rendering Changes

- Example-linked words should render inline within the sentence rather than as a separate chip row.
- `relation_groups` should no longer render as a duplicated second relation section when `Sense Links` already show the per-sense relations.
- `Sense Links` remains the canonical learner-facing relation section.

## Technical Notes

- Reuse `getKnowledgeMapEntryDetail` for the overlay payload.
- Keep exact-match-only linking.
- Add lightweight inline sentence rendering that turns matched words into buttons/links without requiring backend span offsets.

## Verification

- Detail-page Jest coverage for:
  - opening the pickup overlay from an example link
  - dismissing the overlay
  - showing `Look up`
  - absence of duplicated relation-group content
- Frontend lint
- Targeted learner smoke on the live Docker stack
