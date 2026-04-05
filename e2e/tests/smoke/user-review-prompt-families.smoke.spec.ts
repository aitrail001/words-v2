import { expect, test, type Page } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import {
  REVIEW_SCENARIO_DEFINITIONS,
  seedReviewScenarioQueue,
} from "../helpers/review-scenario-fixture";

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const clickOptionByLabel = async (page: Page, label: string) => {
  const exactEndMatch = page
    .getByRole("button")
    .filter({ hasText: new RegExp(`${escapeRegExp(label)}$`, "i") });
  const exactEndCount = await exactEndMatch.count();
  if (exactEndCount === 1) {
    await exactEndMatch.first().click();
    return;
  }
  if (exactEndCount > 1) {
    for (let index = 0; index < exactEndCount; index += 1) {
      const candidate = exactEndMatch.nth(index);
      const text = (await candidate.textContent())?.trim().toLowerCase() ?? "";
      if (text === label.toLowerCase() || /^[a-d]\s*/i.test(text) && text.replace(/^[a-d]\s*/i, "") === label.toLowerCase()) {
        await candidate.click();
        return;
      }
    }
    await exactEndMatch.first().click();
    return;
  }
  await page.getByRole("button", { name: new RegExp(`^${escapeRegExp(label)}$`, "i") }).click();
};

const answerVisiblePrompt = async (page: Page, scenario: (typeof REVIEW_SCENARIO_DEFINITIONS)[number]) => {
  const definitionButtons = page.getByRole("button", {
    name: new RegExp(escapeRegExp(scenario.definition), "i"),
  });

  if (await page.getByTestId("review-collocation-prompt").count()) {
    await clickOptionByLabel(page, scenario.displayText);
    return;
  }
  if (await page.getByTestId("review-situation-prompt").count()) {
    await clickOptionByLabel(page, scenario.displayText);
    return;
  }
  if (await page.getByTestId("review-confidence-prompt").count()) {
    await page.getByRole("button", { name: /i remember it/i }).click();
    return;
  }
  if (await page.getByTestId("review-speech-placeholder").count()) {
    await page.getByPlaceholder(/type the word or phrase/i).fill(scenario.displayText);
    await page.getByRole("button", { name: /check answer/i }).click();
    return;
  }
  if (await page.getByPlaceholder(/type the word or phrase/i).count()) {
    await page.getByPlaceholder(/type the word or phrase/i).fill(scenario.displayText);
    await page.getByRole("button", { name: /check answer/i }).click();
    return;
  }
  if (await page.getByRole("button", { name: /replay audio/i }).count()) {
    await expect(page.getByRole("button", { name: /replay audio/i })).toBeVisible();
    await page.getByRole("button", { name: /replay audio/i }).first().click();
    if (await definitionButtons.count()) {
      await definitionButtons.first().click();
      return;
    }
    if (await page.getByPlaceholder(/type the word or phrase/i).count()) {
      await page.getByPlaceholder(/type the word or phrase/i).fill(scenario.displayText);
      await page.getByRole("button", { name: /check answer/i }).click();
      return;
    }
    await clickOptionByLabel(page, scenario.displayText);
    return;
  }
  if (await page.getByText(new RegExp(`^${escapeRegExp(scenario.displayText)}$`, "i")).count()) {
    if (await definitionButtons.count()) {
      await definitionButtons.first().click();
      return;
    }
    await clickOptionByLabel(page, scenario.displayText);
    return;
  }
  await expect(page.getByText(new RegExp(escapeRegExp(scenario.definition), "i"))).toBeVisible();
  if (await definitionButtons.count()) {
    await definitionButtons.first().click();
    return;
  }
  await clickOptionByLabel(page, scenario.displayText);
};

const finishGuidedLearningPass = async (page: Page) => {
  for (let step = 0; step < 10; step += 1) {
    const nextMeaning = page.getByRole("button", { name: /next meaning/i });
    if (await nextMeaning.count()) {
      await nextMeaning.click();
      continue;
    }
    const finishLearning = page.getByRole("button", { name: /finish learning/i });
    if (await finishLearning.count()) {
      await finishLearning.click();
    }
    return;
  }
  throw new Error("Guided relearn did not finish within 10 steps.");
};

const resolveReviewHandoff = async (page: Page) => {
  const waitForReviewReturn = async () => {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      if (await page.getByTestId("review-active-state").count()) {
        return;
      }
      if (await page.getByTestId("review-complete-state").count()) {
        return;
      }
      await page.waitForTimeout(250);
    }
    throw new Error("Review handoff did not return to the active review flow.");
  };

  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await page.getByRole("button", { name: /continue review/i }).count()) {
      await page.getByRole("button", { name: /continue review/i }).click({ force: true });
      await waitForReviewReturn();
      return;
    }
    if (await page.getByRole("button", { name: /back to review/i }).count()) {
      await page.getByRole("button", { name: /back to review/i }).first().click({ force: true });
      await waitForReviewReturn();
      return;
    }
    if (await page.getByTestId("review-relearn-state").count()) {
      await finishGuidedLearningPass(page);
      await waitForReviewReturn();
      return;
    }
    if (await page.getByTestId("review-complete-state").count()) {
      return;
    }
    await page.waitForTimeout(250);
  }
  throw new Error("No review handoff control rendered after prompt submission.");
};

test("@smoke review prompt families run against the real DB-backed queue", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  page.on("dialog", (dialog) => dialog.accept());
  const user = await registerViaApi(request, "review-families");
  await seedReviewScenarioQueue(user.id);

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);

  await page.route("**/api/words/voice-assets/*/content", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "fixture-audio",
    });
  });

  await page.goto("/review");
  await expect(page.getByTestId("review-active-state")).toBeVisible();

  for (const [index, scenario] of REVIEW_SCENARIO_DEFINITIONS.entries()) {
    const reviewCount = `Review ${index + 1}/${REVIEW_SCENARIO_DEFINITIONS.length}`;
    await expect(page.getByText(reviewCount)).toBeVisible();

    if (scenario.expectedPromptType === "sentence_gap") {
      await expect(page.getByRole("button", { name: /show meaning/i })).toBeVisible();
      await page.getByRole("button", { name: /show meaning/i }).click();
      await expect(page.getByTestId("review-relearn-state")).toBeVisible();
      await finishGuidedLearningPass(page);
      if (index + 1 < REVIEW_SCENARIO_DEFINITIONS.length) {
        await expect(page.getByTestId("review-active-state")).toBeVisible();
      }
      continue;
    }

    await answerVisiblePrompt(page, scenario);

    await resolveReviewHandoff(page);

    if (index + 1 < REVIEW_SCENARIO_DEFINITIONS.length) {
      const nextReviewCount = `Review ${index + 2}/${REVIEW_SCENARIO_DEFINITIONS.length}`;
      await expect(page.getByText(nextReviewCount)).toBeVisible();
    }

    if (index + 1 < REVIEW_SCENARIO_DEFINITIONS.length) {
      await expect(page.getByTestId("review-active-state")).toBeVisible();
    }
  }

  await expect(page.getByTestId("review-complete-state")).toBeVisible();
});
