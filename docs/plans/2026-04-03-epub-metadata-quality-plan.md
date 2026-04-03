# EPUB Metadata Quality Improvement Plan

**Goal:** Improve EPUB import metadata quality so imports reliably show book title, author, publisher, published year, and ISBN from the EPUB package when available, with better fallbacks when package metadata is noisy, while also surfacing live import-job stage progress instead of a generic "In progress" state.

**Architecture:** Replace the current first-field EPUB metadata extraction with a package-level candidate parser and ranking layer in `source_imports.py`. Parse OPF metadata candidates for titles, creators, contributors, dates, identifiers, and publisher, score them for learner-facing quality, persist publisher alongside the existing import-source metadata, and expose the richer metadata through the existing import job responses/UI. In parallel, extend `ImportJob` with explicit stage/counter fields so the worker can persist extraction/matching progress and the imports UI can show live stage labels, counts, and elapsed time during processing.

**Scope slices:**

1. **OPF/package metadata parsing**
   - Parse `META-INF/container.xml` to locate the OPF package.
   - Read `dc:title`, `dc:creator`, `dc:contributor`, `dc:date`, `dc:identifier`, `dc:publisher`, and OPF role/refinement attributes where present.
   - Preserve multiple metadata candidates instead of immediately taking the first field.

2. **Metadata quality ranking**
   - Rank title candidates and combine main-title/subtitle pairs when indicated by metadata.
   - Prefer author-like creator roles over editor/uploader/publisher-like values.
   - Prefer publication dates over modification dates.
   - Prefer ISBN-like identifiers over UUID/ASIN/calibre/package IDs.
   - Add a content-based title fallback for bad package titles using the first useful spine documents before falling back to filename cleanup.

3. **Persistence and API**
   - Add `publisher` to `ImportSource` via a new migration.
   - Store the ranked `title`, `author`, `publisher`, `published_year`, `isbn`, and best raw identifier on `ImportSource`.
   - Expose `source_publisher` in import job API responses and frontend client types.

4. **UI surface alignment**
   - Show publisher in the import landing cards and import detail page alongside the existing metadata.
   - Keep the title display helper as a last-mile guard for already-cached dirty rows, but rely primarily on extractor quality instead of display normalization.

5. **Verification**
   - Add focused unit tests for metadata ranking:
     - clean main-title/subtitle EPUB
     - UUID-only EPUB with no ISBN
     - polluted-title EPUB where content fallback or ranked cleanup must win
     - mixed creator/editor cases
   - Run targeted backend tests for `source_imports`, `imports_api`, and import job API responses.
   - Run frontend import page/detail tests plus a production build.
   - Update `docs/status/project-status.md` with fresh evidence after the slice lands.

6. **Live import progress**
   - Add explicit `ImportJob` progress fields for stage, current label, and live counters.
   - Persist stage updates from the EPUB worker during metadata read, text extraction, entry matching, and final writeback.
   - Update `/imports` and `/imports/[jobId]` to render the live progress label/counts/elapsed time from those persisted fields rather than a generic processing state.
