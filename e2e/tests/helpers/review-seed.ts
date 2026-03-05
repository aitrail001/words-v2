import { expect, APIRequestContext } from "@playwright/test";
import { apiUrl, authHeaders } from "./auth";
import { ensureResilienceVocabularyFixture } from "./vocabulary-fixture";

export const seedDueReviewItem = async (
  request: APIRequestContext,
  token: string,
): Promise<void> => {
  const fixture = await ensureResilienceVocabularyFixture();

  const queueResponse = await request.post(`${apiUrl}/reviews/queue`, {
    data: { meaning_id: fixture.meaningId },
    headers: authHeaders(token),
  });

  expect(queueResponse.ok()).toBeTruthy();
};
