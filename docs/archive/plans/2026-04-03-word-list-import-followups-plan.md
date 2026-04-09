# Word List Import Follow-Ups Implementation Plan

**Goal:** Separate import and word-list management cleanly, unify user word-list detail with the learner knowledge-list experience, and close the remaining management workflow gaps.

**Architecture:** Keep `/imports` focused on upload, extraction review, and create-list flow. Move ongoing management to `/word-lists` and `/word-lists/[id]`, where the detail page reuses a shared learner-list surface derived from the current `knowledge-list/[status]` UI. Extend the backend with user-scoped unique-name validation, bulk list/item actions, paginated import review/history support, and word-list detail hydration that includes learner status metadata.

**Scope slices:**

1. **Backend contract hardening**
   - Add user-scoped unique-name enforcement for empty-list creation, rename, and import-based list creation.
   - Add list index bulk delete endpoint.
   - Add word-list item bulk delete endpoint.
   - Add import job listing filters for active vs history.
   - Add learner status hydration to word-list detail items so the user-list detail page can match learner knowledge lists.

2. **Shared learner list detail surface**
   - Extract the core list row/search/sort/status UI from `frontend/src/app/knowledge-list/[status]/page.tsx` into a reusable component.
   - Reuse it in knowledge lists with system-managed actions.
   - Reuse it in `/word-lists/[id]` with user-list actions layered on top.

3. **Word-list management flow**
   - Keep `/word-lists` as the index page.
   - Add create-new-list CTA and modal.
   - Add multi-select bulk delete on the list index.
   - Add `/word-lists/[id]` dedicated detail route with back-to-index navigation.
   - Add floating management modal on the detail page for rename, description, and destructive list actions.
   - Add select all / clear / bulk remove / single remove confirmation inside the detail page.

4. **Import flow follow-ups**
   - Remove upfront list name from upload start.
   - Add pagination to review results.
   - Move naming to `Create list from selection` step.
   - Keep `/imports` as the index/landing page and move review/create-list work into a dedicated `/imports/[jobId]` route.
   - Split current import workspace from import history.
   - Allow completed history jobs to reopen the extracted-entry review surface and create additional lists from the same import source.
   - Allow users to select, unselect, select all, and bulk delete only their import-history rows while keeping canonical cached `ImportSource` / `ImportSourceEntry` data intact.
   - Show import metadata and metrics in both the current workspace and history cards: title, author, year, ISBN, cache reuse, duration, total extracted, word count, and phrase count.
   - Prefer extracted book metadata in job/history cards instead of showing only the raw EPUB filename.

5. **Knowledge-list / word-list parity**
   - Hydrate user word-list rows with the same first-definition / translation summary fields shown in learner knowledge lists.
   - Align knowledge-list sort controls with word-list detail: shared sort basis plus explicit ascending/descending order toggle.

6. **Verification**
   - Backend API tests for unique names, bulk actions, import-job filters, and word-list detail status hydration.
   - Frontend tests for index/detail/modal flow, import pagination/history/naming, and shared learner-list rendering.
   - Focused Playwright rerun for import create handoff and word-list detail behavior.
   - Apply the follow-up Alembic migration on the branch-local Docker stack before browser proof, because the new import metadata fields are persisted in `import_sources`.
