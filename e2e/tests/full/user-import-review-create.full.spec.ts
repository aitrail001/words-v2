import path from "node:path";
import { expect, test } from "@playwright/test";
import { registerViaApi } from "../helpers/auth";
import { prepareImportFixture } from "../helpers/import-fixture";
import { waitForImportJobTerminal } from "../helpers/import-jobs";

const EPUB_FIXTURE = path.resolve(process.cwd(), "tests/fixtures/epub/valid-minimal.epub");

type WordListDetail = {
  id: string;
  name: string;
  items: Array<{
    id: string;
    entry_type: string;
    display_text: string | null;
    frequency_count: number;
  }>;
};

test("import review flow creates a generic word list from selected entries", async ({
  page,
  request,
}) => {
  test.slow();

  await prepareImportFixture(EPUB_FIXTURE);

  const user = await registerViaApi(request, "import-review-create");
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/login");
  await page.evaluate((accessToken) => {
    window.localStorage.setItem("words_access_token", accessToken);
    document.cookie = `words_access_token=${encodeURIComponent(accessToken)}; Path=/; SameSite=Lax`;
  }, user.token);
  await page.goto("/imports");
  await expect(page.getByTestId("imports-page-title")).toBeVisible();
  await page.waitForTimeout(1500);

  const listName = `Review Import ${Date.now()}`;
  await page.getByTestId("imports-upload-input").setInputFiles(EPUB_FIXTURE);

  const createImportResponsePromise = page.waitForResponse((response) => {
    const req = response.request();
    return req.method() === "POST" && response.url().includes("/api/word-lists/import");
  });

  await page.getByTestId("imports-submit-button").click();

  const createImportResponse = await createImportResponsePromise;
  expect([200, 201, 202]).toContain(createImportResponse.status());
  const createdJob = (await createImportResponse.json()) as { id: string };
  expect(createdJob.id).toBeTruthy();

  const terminal = await waitForImportJobTerminal(request, user.token, createdJob.id, {
    timeoutMs: 120_000,
    pollIntervalMs: 1_500,
  });
  expect(terminal.status, terminal.error_message ?? "import failed").toBe("completed");
  expect(terminal.matched_entry_count).toBeGreaterThan(0);

  await expect(page).toHaveURL(new RegExp(`/imports/${createdJob.id}$`), { timeout: 15_000 });
  await expect(page.getByTestId("imports-review-panel")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("imports-review-list")).toContainText("learning words");
  await expect(page.getByTestId("imports-selected-count")).not.toHaveText("0 selected");
  await expect(page.getByTestId("import-job-summary")).toContainText("Title:");
  await expect(page.getByTestId("import-job-summary")).toContainText("Author:");
  await page.getByTestId("imports-create-list-name-input").fill(listName);

  const createListResponsePromise = page.waitForResponse((response) => {
    const req = response.request();
    return (
      req.method() === "POST" &&
      response.url().includes(`/api/import-jobs/${createdJob.id}/word-lists`)
    );
  });

  await page.getByTestId("imports-create-list-button").click();

  const createListResponse = await createListResponsePromise;
  expect(createListResponse.status()).toBe(201);
  const createdList = (await createListResponse.json()) as { id: string; name: string };
  expect(createdList.id).toBeTruthy();
  expect(createdList.name).toBe(listName);

  await expect(page.getByTestId("imports-created-list-panel")).toContainText(listName);
  await page.getByTestId("imports-open-created-list-link").click();
  await expect(page.getByTestId("word-list-detail-title")).toHaveText(listName);
  await expect(page.getByTestId("word-list-detail-items")).toContainText("learning words");

  const renamedListName = `${listName} Renamed`;
  await page.getByTestId("word-list-manage-button").click();
  await page.getByTestId("word-list-rename-input").fill(renamedListName);
  await page.getByTestId("word-list-description-input").fill("Imported and reviewed");
  await page.getByTestId("word-list-rename-button").click();
  await expect(page.getByTestId("word-list-message")).toContainText("List updated");
  await expect(page.getByTestId("word-list-detail-title")).toHaveText(renamedListName);

  await page.getByTestId("word-list-manual-search-input").fill("learning");
  await page.getByTestId("word-list-manual-search-button").click();
  await expect(page.getByTestId("word-list-manual-results")).toContainText("learning words");
  await page
    .getByTestId("word-list-manual-results")
    .getByRole("button", { name: "Add" })
    .first()
    .click();
  await expect(page.getByTestId("word-list-message")).toContainText(
    "Added learning words",
  );

  const detailBeforeRemove = await request.get(
    `${process.env.E2E_API_URL ?? "http://localhost:8000/api"}/word-lists/${createdList.id}`,
    {
      headers: {
        Authorization: `Bearer ${user.token}`,
      },
    },
  );
  expect(detailBeforeRemove.status()).toBe(200);
  const detailBeforeRemoveJson = (await detailBeforeRemove.json()) as WordListDetail;
  expect(detailBeforeRemoveJson.name).toBe(renamedListName);
  expect(detailBeforeRemoveJson.items[0].frequency_count).toBeGreaterThan(0);
  const itemId = detailBeforeRemoveJson.items[0].id;

  await page.getByTestId(`word-list-select-item-${itemId}`).click();
  await page.getByTestId("word-list-bulk-remove-button").click();

  await expect(page.getByTestId("word-list-editor-help")).toContainText("quote multi-word phrases");
  await page.getByTestId("word-list-editor-text").fill('"learning words"');
  await page.getByTestId("word-list-add-button").click();
  await expect(page.getByTestId("word-list-message")).toContainText("Added 1 entry");
  await expect(page.getByTestId("word-list-detail-items")).toContainText("learning words");

  const listDetailResponse = await request.get(
    `${process.env.E2E_API_URL ?? "http://localhost:8000/api"}/word-lists/${createdList.id}`,
    {
      headers: {
        Authorization: `Bearer ${user.token}`,
      },
    },
  );
  expect(listDetailResponse.status()).toBe(200);
  const listDetail = (await listDetailResponse.json()) as WordListDetail;
  expect(listDetail.name).toBe(renamedListName);
  expect(listDetail.items.length).toBeGreaterThan(0);
  expect(
    listDetail.items.some(
      (item) =>
        item.entry_type === "phrase" &&
        item.display_text === "learning words" &&
        item.frequency_count > 0,
    ),
  ).toBe(true);

  await page.getByTestId("word-list-back-link").click();
  await expect(page).toHaveURL(/\/word-lists$/);
  await page.getByTestId("word-lists-home-link").click();
  await expect(page).toHaveURL(/\/$/);
});
