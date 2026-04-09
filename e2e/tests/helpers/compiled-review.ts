import { expect, Page } from "@playwright/test";

export async function selectCompiledReviewBatch(page: Page, sourceReference: string): Promise<void> {
  const rail = page.getByTestId("compiled-review-batch-rail");
  const nextButton = page.getByTestId("compiled-review-batch-rail-next");
  const batchCard = rail.getByRole("button").filter({ hasText: sourceReference }).first();

  for (let index = 0; index < 100; index += 1) {
    if (await batchCard.count()) {
      await batchCard.click();
      return;
    }
    if (await nextButton.isDisabled()) {
      break;
    }
    await nextButton.click();
  }

  await expect(rail).toContainText(sourceReference);
}
