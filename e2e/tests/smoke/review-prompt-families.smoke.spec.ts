import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("@smoke review prompt families render and submit non-voice flows", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-families");
  const submitPayloads: Record<string, unknown>[] = [];

  await injectToken(page, user.token);

  await page.route("**/api/reviews/queue/due**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "state-collocation",
          queue_item_id: "state-collocation",
          word: "jump the gun",
          definition: "To do something too soon.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "collocation_check",
            stem: "Choose the common expression that best fits the sentence.",
            question: "They ___ and announced it early.",
            sentence_masked: "They ___ and announced it early.",
            options: [
              { option_id: "A", label: "jump the gun", is_correct: true },
              { option_id: "B", label: "miss the boat", is_correct: false },
              { option_id: "C", label: "cut corners", is_correct: false },
              { option_id: "D", label: "take over", is_correct: false },
            ],
            audio_state: "not_available",
          },
          detail: {
            entry_type: "phrase",
            entry_id: "phrase-collocation",
            display_text: "jump the gun",
            primary_definition: "To do something too soon.",
            primary_example: "They jumped the gun and announced it early.",
            meaning_count: 1,
            remembered_count: 2,
            compare_with: ["move too fast"],
            meanings: [],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "3d", label: "In 3 days", is_default: true }],
        },
        {
          id: "state-situation",
          queue_item_id: "state-situation",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "situation_matching",
            stem: "Which word or phrase best fits this situation?",
            question: "A team keeps adapting after repeated setbacks.",
            options: [
              { option_id: "A", label: "overreaction", is_correct: false },
              { option_id: "B", label: "resilience", is_correct: true },
              { option_id: "C", label: "avoidance", is_correct: false },
              { option_id: "D", label: "confusion", is_correct: false },
            ],
            audio_state: "not_available",
          },
          detail: {
            entry_type: "word",
            entry_id: "word-situation",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt after major setbacks.",
            meaning_count: 1,
            remembered_count: 3,
            compare_with: [],
            meanings: [
              {
                id: "meaning-situation",
                definition: "The capacity to recover quickly from difficulties.",
                example: "Resilience helps teams adapt after major setbacks.",
              },
            ],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        },
        {
          id: "state-speak",
          queue_item_id: "state-speak",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "speak_recall",
            stem: "Say or type the word or phrase that matches this definition.",
            question: "The capacity to recover quickly from difficulties.",
            options: null,
            expected_input: "resilience",
            input_mode: "speech_placeholder",
            voice_placeholder_text: "Voice capture is not live yet. Type the answer for now.",
            audio_state: "placeholder",
          },
          detail: {
            entry_type: "word",
            entry_id: "word-speak",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt to change.",
            meaning_count: 1,
            remembered_count: 4,
            compare_with: [],
            meanings: [],
            audio_state: "placeholder",
          },
          schedule_options: [{ value: "7d", label: "In a week", is_default: true }],
        },
      ]),
    });
  });

  await page.route("**/api/reviews/queue/*/submit", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    submitPayloads.push(payload);

    const itemId = route.request().url().split("/").pop() ?? "";
    if (payload.outcome === "wrong" && itemId === "state-situation") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            entry_type: "word",
            entry_id: "word-situation",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt after major setbacks.",
            meaning_count: 1,
            remembered_count: 3,
            compare_with: [],
            meanings: [
              {
                id: "meaning-situation",
                definition: "The capacity to recover quickly from difficulties.",
                example: "Resilience helps teams adapt after major setbacks.",
              },
            ],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });

  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();

  await expect(page.getByTestId("review-collocation-prompt")).toBeVisible();
  await expect(page.getByTestId("review-collocation-prompt").getByText(/common expression/i)).toBeVisible();
  await page.getByRole("button", { name: /jump the gun/i }).click();
  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-situation-prompt")).toBeVisible();
  await expect(
    page.getByTestId("review-situation-prompt").getByText(
      /a team keeps adapting after repeated setbacks/i,
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: /overreaction/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-speech-placeholder")).toBeVisible();
  await expect(page.getByText(/voice capture is not live yet/i)).toBeVisible();
  await page.getByPlaceholder(/type the word or phrase/i).fill("resilience");
  await page.getByRole("button", { name: /check answer/i }).click();
  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-complete-state")).toBeVisible();
  await expect(page.getByText(/you reviewed 3 entries/i)).toBeVisible();

  expect(submitPayloads).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        outcome: "correct_tested",
        selected_option_id: "A",
        schedule_override: "3d",
      }),
      expect.objectContaining({
        outcome: "wrong",
      }),
      expect.objectContaining({
        outcome: "correct_tested",
        typed_answer: "resilience",
        schedule_override: "7d",
      }),
    ]),
  );
});
