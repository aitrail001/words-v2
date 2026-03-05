import { expect, APIRequestContext } from "@playwright/test";
import { apiUrl, authHeaders } from "./auth";

type SearchWord = {
  id: string;
  word: string;
};

type WordDetail = {
  meanings: Array<{ id: string }>;
};

export const seedDueReviewItem = async (
  request: APIRequestContext,
  token: string,
): Promise<void> => {
  const searchResponse = await request.get(`${apiUrl}/words/search?q=resilience`, {
    headers: authHeaders(token),
  });

  expect(searchResponse.ok()).toBeTruthy();
  const words = (await searchResponse.json()) as SearchWord[];
  const resilience = words.find((entry) => entry.word === "resilience") ?? words[0];
  expect(resilience?.id).toBeTruthy();

  const detailsResponse = await request.get(`${apiUrl}/words/${resilience.id}`, {
    headers: authHeaders(token),
  });
  expect(detailsResponse.ok()).toBeTruthy();

  const details = (await detailsResponse.json()) as WordDetail;
  const meaningId = details.meanings[0]?.id;
  expect(meaningId).toBeTruthy();

  const queueResponse = await request.post(`${apiUrl}/reviews/queue`, {
    data: { meaning_id: meaningId },
    headers: authHeaders(token),
  });

  expect(queueResponse.ok()).toBeTruthy();
};
