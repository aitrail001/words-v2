import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { ensureMinimalEpubFixture } from "../helpers/epub-fixture";
import { prepareImportFixture } from "../helpers/import-fixture";
import { ImportJobSnapshot, waitForImportJobTerminal } from "../helpers/import-jobs";

test("word-list import reaches completed terminal status with valid epub", async ({
  page,
  request,
}) => {
  test.slow();
  const epubFixture = await ensureMinimalEpubFixture();

  await prepareImportFixture(epubFixture);

  const user = await registerViaApi(request, "import-terminal");
  await injectToken(page, user.token);
  await page.goto("/imports");
  await expect(page.getByTestId("imports-page-title")).toBeVisible();
  await page.getByTestId("imports-upload-input").setInputFiles(epubFixture);

  const createResponsePromise = page.waitForResponse((response) => {
    const req = response.request();
    return req.method() === "POST" && response.url().includes("/api/word-lists/import");
  });

  await page.getByTestId("imports-submit-button").click();

  const createResponse = await createResponsePromise;
  expect([200, 201, 202]).toContain(createResponse.status());
  const created = (await createResponse.json()) as ImportJobSnapshot;
  expect(created.id).toBeTruthy();

  const terminal = await waitForImportJobTerminal(request, user.token, created.id, {
    timeoutMs: 120_000,
    pollIntervalMs: 1_500,
  });

  expect(
    terminal.status,
    `import job failed: ${terminal.error_message ?? "missing error_message"}`,
  ).toBe("completed");
  expect(terminal.import_source_id).toBeTruthy();
  expect(terminal.completed_at).toBeTruthy();
  expect(terminal.source_filename).toBe("valid-minimal.epub");
  expect(terminal.list_name).toBe("valid-minimal");
  expect(terminal.word_list_id).toBeNull();
  expect(terminal.matched_entry_count).toBeGreaterThan(0);
  expect(terminal.total_items).toBeGreaterThan(0);
  expect(terminal.processed_items).toBe(terminal.total_items);
  expect(terminal.error_count).toBe(0);

  await expect(page).toHaveURL(new RegExp(`/imports/${created.id}$`), { timeout: 15_000 });
  await page.goto("/imports");
  await page.getByTestId("imports-history-toggle").click();
  await expect(page.getByTestId(`imports-row-${created.id}`)).toContainText("Valid Minimal EPUB");
  await expect(page.getByTestId(`imports-row-${created.id}`)).toContainText("completed");
});
