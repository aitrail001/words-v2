import { expect, test } from "@playwright/test";
import { apiUrl, registerViaApi } from "../helpers/auth";

type ImportJob = {
  id: string;
  status: string;
  source_filename: string;
  list_name: string;
};

test("@smoke word-list import API creates import job and serves status snapshot", async ({ request }) => {
  const user = await registerViaApi(request, "import-domain-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const filename = `domain-${uniqueSuffix}.epub`;

  const createResponse = await request.post(`${apiUrl}/word-lists/import`, {
    headers: {
      Authorization: `Bearer ${user.token}`,
    },
    multipart: {
      file: {
        name: filename,
        mimeType: "application/epub+zip",
        buffer: Buffer.from(`EPUB-DOMAIN-${uniqueSuffix}`, "utf-8"),
      },
      list_name: `Smoke ${uniqueSuffix}`,
    },
  });

  expect([200, 201, 202]).toContain(createResponse.status());
  const created = (await createResponse.json()) as ImportJob;
  expect(created.id).toBeTruthy();
  expect(created.source_filename).toBe(filename);
  expect(created.list_name).toContain("Smoke");
  expect(["queued", "processing", "completed"]).toContain(created.status);

  const jobResponse = await request.get(`${apiUrl}/import-jobs/${created.id}`, {
    headers: {
      Authorization: `Bearer ${user.token}`,
    },
  });

  expect(jobResponse.status()).toBe(200);
  const snapshot = (await jobResponse.json()) as ImportJob;
  expect(snapshot.id).toBe(created.id);
  expect(snapshot.source_filename).toBe(filename);

  const listsResponse = await request.get(`${apiUrl}/word-lists`, {
    headers: {
      Authorization: `Bearer ${user.token}`,
    },
  });

  expect(listsResponse.status()).toBe(200);
});
