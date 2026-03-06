import path from "node:path";
import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { ImportJobSnapshot, waitForImportJobTerminal } from "../helpers/import-jobs";

const EPUB_FIXTURE = path.resolve(process.cwd(), "tests/fixtures/epub/valid-minimal.epub");

test("word-list import reaches completed terminal status with valid epub", async ({
  page,
  request,
}) => {
  test.slow();

  const user = await registerViaApi(request, "import-terminal");
  await injectToken(page, user.token);
  await page.goto("/imports");
  await expect(page.getByTestId("imports-page-title")).toBeVisible();

  const listName = `Terminal Import ${Date.now()}`;
  await page.locator("#imports-list-name").fill(listName);
  await page.getByTestId("imports-upload-input").setInputFiles(EPUB_FIXTURE);

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
  expect(terminal.started_at).toBeTruthy();
  expect(terminal.completed_at).toBeTruthy();
  expect(terminal.book_id).toBeTruthy();
  expect(terminal.word_list_id).toBeTruthy();
  expect(terminal.total_items).toBeGreaterThan(0);
  expect(terminal.processed_items).toBe(terminal.total_items);
  expect(terminal.error_count).toBe(0);

  await page.reload();
  await expect(page.getByTestId("word-lists-list")).toContainText(listName);
});
