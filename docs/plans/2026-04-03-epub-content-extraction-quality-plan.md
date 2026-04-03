# EPUB Content Extraction Quality Plan

Goal: improve EPUB text-to-entry extraction quality by normalizing real EPUB text artifacts before matching, broadening deterministic inflection handling, and verifying behavior against representative EPUB files under `/Users/johnson/Downloads/Organized/Ebooks`.

Scope:
- backend extraction and matching only
- no UI changes in this slice
- keep metadata-ranking work intact; focus on chunk text normalization and word/phrase resolution quality

Key findings from live EPUB samples:
- text chunks can contain fragmented OCR-like tokens such as `p enguin r and om h ouse`
- dash and punctuation normalization is present, but there is no first-class cleanup stage before tokenization
- suffix-only lemmatization is too weak for broader tense/plural coverage
- phrase matching is structurally fine, but it depends on token quality upstream

Implementation steps:
1. Add a dedicated normalization layer in `backend/app/services/source_imports.py` for chunk text before tokenization.
   - remove soft hyphens
   - normalize ligatures and dash variants
   - collapse intra-word line-break / space-hyphen-space artifacts where safe
   - repair obvious OCR-style single-letter uppercase fragments when they create broken words in all-caps/imprint-style spans
   - keep transformations conservative to avoid corrupting ordinary prose
2. Strengthen deterministic inflection handling in `deterministic_lemmatize()`.
   - add common irregulars beyond the current tiny set
   - handle selected `-ied` / doubled-consonant / `-ves` / `-es` / `-ing` / `-ed` cases more carefully
   - prefer deterministic rules only; no heavy NLP dependency in this slice
3. Route matcher tokenization through the new normalization layer.
   - ensure phrase matching and word resolution both benefit from the same cleaned token stream
   - keep ordering and frequency logic unchanged
4. Add red-first tests in `backend/tests/test_source_imports_service.py`.
   - split-word repair
   - ligature/dash cleanup
   - plural/tense/irregular fallback resolution
   - phrase matching after cleanup
   - real-sample-inspired OCR fragment cleanup
5. Add a lightweight probe script under `scripts/`.
   - inspect EPUB extraction and matching quality against `/Users/johnson/Downloads/Organized/Ebooks`
   - print suspicious tokens and a compact metadata/matching summary for manual review
6. Update `docs/status/project-status.md` with verification evidence and remaining known limits.

Verification:
- targeted pytest on `backend/tests/test_source_imports_service.py`
- targeted pytest on import processing tests if matcher contract changes affect them
- optional real-file probe command against the user EPUB directory
- `ruff check` on touched backend files
- `git diff --check`

Known non-goals:
- introducing external stemming/lemmatization libraries
- changing import UI
- modifying learner catalog semantics
