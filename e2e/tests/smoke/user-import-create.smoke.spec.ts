import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { apiUrl, registerViaApi } from "../helpers/auth";

type ImportItem = {
  id: string;
  user_id: string;
  source_filename: string;
  status: string;
  source_hash: string;
};

test("@smoke import create API returns 201 and appears in list", async ({ request }) => {
  const user = await registerViaApi(request, "import-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const filename = `smoke-${uniqueSuffix}.epub`;
  const payload = `EPUB-SMOKE-${uniqueSuffix}`;
  const expectedHash = createHash("sha256").update(payload, "utf-8").digest("hex");

  const createResponse = await request.post(`${apiUrl}/imports`, {
    headers: {
      Authorization: `Bearer ${user.token}`,
    },
    multipart: {
      file: {
        name: filename,
        mimeType: "application/epub+zip",
        buffer: Buffer.from(payload, "utf-8"),
      },
    },
  });

  expect(createResponse.status()).toBe(201);
  const created = (await createResponse.json()) as ImportItem;
  expect(created.id).toBeTruthy();
  expect(created.user_id).toBeTruthy();
  expect(created.source_filename).toBe(filename);
  expect(created.status).toBe("queued");
  expect(created.source_hash).toBe(expectedHash);

  const listResponse = await request.get(`${apiUrl}/imports`, {
    headers: {
      Authorization: `Bearer ${user.token}`,
    },
  });

  expect(listResponse.status()).toBe(200);
  const imports = (await listResponse.json()) as ImportItem[];
  const matches = imports.filter((item) => item.id === created.id);
  expect(matches).toHaveLength(1);
  expect(matches[0].source_filename).toBe(filename);
  expect(matches[0].source_hash).toBe(expectedHash);
});
