import { readFile } from "node:fs/promises";
import { expect, type APIRequestContext } from "@playwright/test";
import { authHeaders, apiUrl } from "./auth";
import { ensureMinimalEpubFixture } from "./epub-fixture";
import { prepareImportFixture } from "./import-fixture";
import {
  type ImportJobSnapshot,
  waitForImportJobTerminal,
} from "./import-jobs";

type ImportReviewEntry = {
  entry_type: string;
  entry_id: string;
};

type ImportEntriesResponse = {
  items: ImportReviewEntry[];
};

type WordListResponse = {
  id: string;
  name: string;
};

export const createCompletedImportJob = async (
  request: APIRequestContext,
  token: string,
): Promise<ImportJobSnapshot> => {
  const epubFixture = await ensureMinimalEpubFixture();
  await prepareImportFixture(epubFixture);

  const createResponse = await request.post(`${apiUrl}/word-lists/import`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    multipart: {
      file: {
        name: "valid-minimal.epub",
        mimeType: "application/epub+zip",
        buffer: await readFile(epubFixture),
      },
    },
  });

  expect([200, 201, 202]).toContain(createResponse.status());
  const created = (await createResponse.json()) as { id: string };
  expect(created.id).toBeTruthy();

  const terminal = await waitForImportJobTerminal(request, token, created.id, {
    timeoutMs: 120_000,
    pollIntervalMs: 1_500,
  });

  expect(
    terminal.status,
    `import job failed: ${terminal.error_message ?? "missing error_message"}`,
  ).toBe("completed");
  expect(terminal.import_source_id).toBeTruthy();

  return terminal;
};

export const createWordListFromImportJob = async (
  request: APIRequestContext,
  token: string,
  jobId: string,
  name: string,
): Promise<WordListResponse> => {
  const entriesResponse = await request.get(`${apiUrl}/import-jobs/${jobId}/entries`, {
    headers: authHeaders(token),
  });
  expect(entriesResponse.status()).toBe(200);
  const entries = (await entriesResponse.json()) as ImportEntriesResponse;
  expect(entries.items.length).toBeGreaterThan(0);

  const createResponse = await request.post(`${apiUrl}/import-jobs/${jobId}/word-lists`, {
    headers: authHeaders(token),
    data: {
      name,
      selected_entries: entries.items.slice(0, 1).map((entry) => ({
        entry_type: entry.entry_type,
        entry_id: entry.entry_id,
      })),
    },
  });
  expect(createResponse.status()).toBe(201);

  const createdWordList = (await createResponse.json()) as WordListResponse;
  expect(createdWordList.id).toBeTruthy();
  expect(createdWordList.name).toBe(name);

  return createdWordList;
};
