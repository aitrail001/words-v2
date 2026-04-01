import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("@smoke typed review normalization submits once and accepts punctuation/case variants", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-typed-normalization");
  const submitPayloads: Record<string, unknown>[] = [];

  await injectToken(page, user.token);

  await page.route("**/api/reviews/queue/due**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "state-typed",
          queue_item_id: "state-typed",
          word: "look up",
          definition: "To search for information.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "typed_recall",
            prompt_token: "prompt-state-typed",
            stem: "Type the word or phrase that matches this definition.",
            question: "To search for information.",
            input_mode: "typed",
            source_entry_type: "phrase",
            audio_state: "not_available",
          },
          detail: {
            entry_type: "phrase",
            entry_id: "phrase-look-up",
            display_text: "look up",
            primary_definition: "To search for information.",
            primary_example: "Look up the address before you leave.",
            meaning_count: 1,
            remembered_count: 1,
            compare_with: [],
            meanings: [],
            audio_state: "not_available",
            coverage_summary: "familiar_with_1_meaning",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        },
      ]),
    });
  });

  await page.route("**/api/reviews/queue/state-typed/submit", async (route) => {
    submitPayloads.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "state-typed",
        meaning_id: "phrase-sense-look-up",
        target_type: "phrase_sense",
        target_id: "phrase-sense-look-up",
        outcome: "correct_tested",
        needs_relearn: false,
        recheck_planned: false,
        detail: {
          entry_type: "phrase",
          entry_id: "phrase-look-up",
          display_text: "look up",
          primary_definition: "To search for information.",
          primary_example: "Look up the address before you leave.",
          meaning_count: 1,
          remembered_count: 1,
          compare_with: [],
          meanings: [],
          audio_state: "not_available",
          coverage_summary: "familiar_with_1_meaning",
        },
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      }),
    });
  });

  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();
  await page.getByPlaceholder(/type the word or phrase/i).fill("  Look, up!! ");
  await page.getByRole("button", { name: /check answer/i }).click();

  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await expect(page.getByRole("heading", { name: "look up" })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page.getByTestId("review-complete-state")).toBeVisible();

  expect(submitPayloads).toHaveLength(1);
  expect(submitPayloads[0]).toMatchObject({
    typed_answer: "  Look, up!! ",
    prompt_token: "prompt-state-typed",
  });
});
