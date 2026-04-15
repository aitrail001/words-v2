import { readFile } from "node:fs/promises";
import { expect, type APIRequestContext } from "@playwright/test";
import { authHeaders, apiUrl } from "./auth";
import { ensureMinimalEpubFixture } from "./epub-fixture";
import { prepareImportFixture } from "./import-fixture";
import {
  type ImportJobSnapshot,
  waitForImportJobTerminal,
} from "./import-jobs";
import { seedCustomReviewQueue } from "./review-scenario-fixture";

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

export type RouteRuntimeCanonicalScheduleFixture = {
  wordEntryId: string;
  wordText: string;
  phraseEntryId: string;
  phraseText: string;
};

function buildTomorrowReleaseInstant(): Date {
  const now = new Date();
  return new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + 1,
      18,
      0,
      0,
      0,
    ),
  );
}

export const seedRouteRuntimeCanonicalScheduleFixture = async (
  userId: string,
): Promise<RouteRuntimeCanonicalScheduleFixture> => {
  const releaseAt = buildTomorrowReleaseInstant();
  const phraseReleaseAt = new Date(releaseAt.getTime() + 5 * 60 * 1000);
  const reviewedAt = new Date(releaseAt.getTime() - 24 * 60 * 60 * 1000);

  const scenarios = await seedCustomReviewQueue(userId, {
    timezone: "UTC",
    items: [
      {
        scenarioKey: "entry-to-definition",
        status: "learning",
        dueAt: releaseAt,
        dueReviewDate: releaseAt.toISOString().slice(0, 10),
        minDueAtUtc: releaseAt,
        lastReviewedAt: reviewedAt,
        srsBucket: "1d",
      },
      {
        scenarioKey: "definition-to-entry",
        status: "learning",
        dueAt: phraseReleaseAt,
        dueReviewDate: phraseReleaseAt.toISOString().slice(0, 10),
        minDueAtUtc: phraseReleaseAt,
        lastReviewedAt: reviewedAt,
        srsBucket: "1d",
      },
    ],
  });

  return {
    wordEntryId: scenarios["entry-to-definition"].resolvedEntryId,
    wordText: scenarios["entry-to-definition"].displayText,
    phraseEntryId: scenarios["definition-to-entry"].resolvedEntryId,
    phraseText: scenarios["definition-to-entry"].displayText,
  };
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
