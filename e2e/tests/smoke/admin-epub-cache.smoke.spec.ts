import { expect, test } from "@playwright/test";
import { injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";
import { ensureMinimalEpubFixture } from "../helpers/epub-fixture";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";
test("@smoke admin can open EPUB cache management page", async ({ page, request }) => {
  const epubFixture = await ensureMinimalEpubFixture();
  const user = await registerAdminViaApi(request, "admin-epub-cache-smoke");

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);

  await page.goto(`${adminUrl}/lexicon/epub-cache`);

  await expect(page).toHaveURL(`${adminUrl}/lexicon/epub-cache/sources`);
  await expect(page.getByTestId("lexicon-epub-cache-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "EPUB Cache Management" })).toBeVisible();
  await expect(page.getByTestId("lexicon-epub-cache-nav")).toBeVisible();
  await expect(page.getByTestId("epub-cache-sources-table")).toBeVisible();

  await page.getByRole("link", { name: "Batch Import" }).click();
  await expect(page).toHaveURL(`${adminUrl}/lexicon/epub-cache/batches`);
  await expect(page.getByTestId("lexicon-epub-cache-batches-page")).toBeVisible();
  await expect(page.getByTestId("epub-cache-recent-batches")).toBeVisible();

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles([epubFixture, epubFixture]);
  await page.getByRole("button", { name: "Start pre-import batch" }).click();
  await expect(page.getByText(/Batch created with \d+ jobs/)).toBeVisible();
  await page.getByRole("link", { name: "Open batch" }).first().click();
  await expect(page).toHaveURL(/\/lexicon\/epub-cache\/batches\/.+/);
  await expect(page.getByTestId("lexicon-epub-cache-batch-detail-page")).toBeVisible();
  await expect(page.getByTestId("epub-cache-batch-jobs")).toBeVisible();
  await expect(page.getByTestId("epub-cache-batch-job-detail")).toBeVisible();
});

test("@smoke admin source details ignore stale deleted-cache responses after a newer success", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-epub-cache-race");

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);

  const goodEnergyId = "00000000-0000-0000-0000-000000000001";
  const otherId = "00000000-0000-0000-0000-000000000002";
  let goodEnergyEntryRequestCount = 0;

  const sourcesPayload = {
    total: 2,
    items: [
      {
        id: goodEnergyId,
        source_type: "epub",
        source_hash_sha256: "good-energy-hash",
        title: "Good Energy: The Surprising Connection Between Metabolism and Limitless Health",
        author: "Casey Means, MD, Calley Means",
        publisher: "Penguin Publishing Group",
        language: "en-US",
        source_identifier: "9780593712665",
        published_year: 2024,
        isbn: "9780593712665",
        status: "completed",
        matched_entry_count: 5682,
        word_entry_count: 5372,
        phrase_entry_count: 310,
        created_at: "2026-04-03T14:07:10.134767Z",
        processed_at: "2026-04-04T00:57:34.325740Z",
        deleted_at: null,
        deleted_by_user_id: null,
        deletion_reason: null,
        first_imported_at: "2026-04-03T14:07:10.134767Z",
        first_imported_by_user_id: user.id,
        first_imported_by_email: user.email,
        first_imported_by_role: "admin",
        processing_duration_seconds: 14,
        source_filename: "Good Energy.epub",
        total_jobs: 10,
        cache_hit_count: 5,
        last_reused_at: "2026-04-04T00:59:17.293992Z",
        last_reused_by_user_id: user.id,
        last_reused_by_email: user.email,
        last_reused_by_role: "admin",
      },
      {
        id: otherId,
        source_type: "epub",
        source_hash_sha256: "other-book-hash",
        title: "Other Book",
        author: "Another Author",
        publisher: null,
        language: "en-US",
        source_identifier: null,
        published_year: null,
        isbn: null,
        status: "completed",
        matched_entry_count: 12,
        word_entry_count: 10,
        phrase_entry_count: 2,
        created_at: "2026-04-03T14:07:10.134767Z",
        processed_at: "2026-04-04T00:57:34.325740Z",
        deleted_at: null,
        deleted_by_user_id: null,
        deletion_reason: null,
        first_imported_at: "2026-04-03T14:07:10.134767Z",
        first_imported_by_user_id: user.id,
        first_imported_by_email: user.email,
        first_imported_by_role: "admin",
        processing_duration_seconds: 2,
        source_filename: "Other Book.epub",
        total_jobs: 1,
        cache_hit_count: 0,
        last_reused_at: null,
        last_reused_by_user_id: null,
        last_reused_by_email: null,
        last_reused_by_role: null,
      },
    ],
  };

  await page.route("**/api/admin/import-sources", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sourcesPayload) });
  });
  await page.route("**/api/admin/import-sources?*", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sourcesPayload) });
  });

  await page.route(`**/api/admin/import-sources/${goodEnergyId}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sourcesPayload.items[0]) });
  });
  await page.route(`**/api/admin/import-sources/${otherId}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sourcesPayload.items[1]) });
  });

  await page.route(`**/api/admin/import-sources/${goodEnergyId}/jobs?*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        items: [
          {
            id: "job-good-energy-1",
            user_id: user.id,
            user_email: user.email,
            user_role: "admin",
            import_batch_id: "batch-1",
            job_origin: "admin_preimport",
            status: "completed",
            source_filename: "Good Energy.epub",
            list_name: "Good Energy",
            matched_entry_count: 5682,
            created_at: "2026-04-04T00:59:17.293992Z",
            started_at: null,
            completed_at: "2026-04-04T00:59:17.312088Z",
            from_cache: true,
            processing_duration_seconds: null,
          },
        ],
      }),
    });
  });
  await page.route(`**/api/admin/import-sources/${goodEnergyId}/jobs`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        items: [
          {
            id: "job-good-energy-1",
            user_id: user.id,
            user_email: user.email,
            user_role: "admin",
            import_batch_id: "batch-1",
            job_origin: "admin_preimport",
            status: "completed",
            source_filename: "Good Energy.epub",
            list_name: "Good Energy",
            matched_entry_count: 5682,
            created_at: "2026-04-04T00:59:17.293992Z",
            started_at: null,
            completed_at: "2026-04-04T00:59:17.312088Z",
            from_cache: true,
            processing_duration_seconds: null,
          },
        ],
      }),
    });
  });

  await page.route(`**/api/admin/import-sources/${otherId}/jobs?*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 1,
        items: [
          {
            id: "job-other-1",
            user_id: user.id,
            user_email: user.email,
            user_role: "admin",
            import_batch_id: "batch-2",
            job_origin: "admin_preimport",
            status: "completed",
            source_filename: "Other Book.epub",
            list_name: "Other Book",
            matched_entry_count: 12,
            created_at: "2026-04-04T00:59:17.293992Z",
            started_at: null,
            completed_at: "2026-04-04T00:59:17.312088Z",
            from_cache: true,
            processing_duration_seconds: null,
          },
        ],
      }),
    });
  });
  await page.route(`**/api/admin/import-sources/${otherId}/jobs`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 1,
        items: [
          {
            id: "job-other-1",
            user_id: user.id,
            user_email: user.email,
            user_role: "admin",
            import_batch_id: "batch-2",
            job_origin: "admin_preimport",
            status: "completed",
            source_filename: "Other Book.epub",
            list_name: "Other Book",
            matched_entry_count: 12,
            created_at: "2026-04-04T00:59:17.293992Z",
            started_at: null,
            completed_at: "2026-04-04T00:59:17.312088Z",
            from_cache: true,
            processing_duration_seconds: null,
          },
        ],
      }),
    });
  });

  await page.route(`**/api/admin/import-sources/${goodEnergyId}/entries?*`, async (route) => {
    goodEnergyEntryRequestCount += 1;
    if (goodEnergyEntryRequestCount === 1) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({
        status: 410,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            code: "IMPORT_CACHE_DELETED",
            message: "This cached import is no longer available. Re-upload the EPUB to regenerate import cache.",
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        items: [
          {
            source_entry_row_id: "good-energy-entry-1",
            entry_type: "word",
            entry_id: "entry-1",
            frequency_count: 4464,
            display_text: "the",
            normalized_form: "the",
            browse_rank: 1,
            cefr_level: "A1",
            phrase_kind: null,
            primary_part_of_speech: "determiner",
          },
        ],
      }),
    });
  });
  await page.route(`**/api/admin/import-sources/${goodEnergyId}/entries`, async (route) => {
    goodEnergyEntryRequestCount += 1;
    if (goodEnergyEntryRequestCount === 1) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({
        status: 410,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            code: "IMPORT_CACHE_DELETED",
            message: "This cached import is no longer available. Re-upload the EPUB to regenerate import cache.",
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        items: [
          {
            source_entry_row_id: "good-energy-entry-1",
            entry_type: "word",
            entry_id: "entry-1",
            frequency_count: 4464,
            display_text: "the",
            normalized_form: "the",
            browse_rank: 1,
            cefr_level: "A1",
            phrase_kind: null,
            primary_part_of_speech: "determiner",
          },
        ],
      }),
    });
  });

  await page.route(`**/api/admin/import-sources/${otherId}/entries?*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 1,
        items: [
          {
            source_entry_row_id: "other-entry-1",
            entry_type: "word",
            entry_id: "entry-2",
            frequency_count: 20,
            display_text: "other",
            normalized_form: "other",
            browse_rank: 500,
            cefr_level: "B1",
            phrase_kind: null,
            primary_part_of_speech: "adjective",
          },
        ],
      }),
    });
  });
  await page.route(`**/api/admin/import-sources/${otherId}/entries`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 1,
        items: [
          {
            source_entry_row_id: "other-entry-1",
            entry_type: "word",
            entry_id: "entry-2",
            frequency_count: 20,
            display_text: "other",
            normalized_form: "other",
            browse_rank: 500,
            cefr_level: "B1",
            phrase_kind: null,
            primary_part_of_speech: "adjective",
          },
        ],
      }),
    });
  });

  await page.goto(`${adminUrl}/lexicon/epub-cache/sources`);
  await expect(page.getByTestId("epub-cache-sources-table")).toBeVisible();

  const goodEnergyRow = page.locator("tr", { hasText: "Good Energy: The Surprising Connection Between Metabolism and Limitless Health" });
  const otherRow = page.locator("tr", { hasText: "Other Book" });

  await goodEnergyRow.getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(100);
  await otherRow.getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(100);
  await goodEnergyRow.getByRole("button", { name: "Open" }).click();

  const details = page.getByTestId("epub-cache-source-details");
  await expect(details).toContainText("Title: Good Energy: The Surprising Connection Between Metabolism and Limitless Health");
  await expect(details).toContainText("the · word · freq 4464");
  await expect(details).not.toContainText("This cached import is no longer available");
  await expect(details).not.toContainText("No cached entries.");
});
