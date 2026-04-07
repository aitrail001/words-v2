import { seedDueReviewScenarioItem, type DueReviewSeedFixture } from "./review-scenario-fixture";

export const seedDueReviewItem = async (
  userId: string,
): Promise<DueReviewSeedFixture> => seedDueReviewScenarioItem(userId);
