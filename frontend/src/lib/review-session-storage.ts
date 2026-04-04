import type {
  ReviewDetailPayload,
  ReviewPromptPayload,
  ReviewScheduleOption,
} from "@/lib/knowledge-map-client";

export const REVIEW_RESUME_STORAGE_KEY = "learner-review-session-v1";

export type StoredReviewCard = {
  id?: string;
  queue_item_id?: string | null;
  meaning_id?: string | null;
  word?: string;
  definition?: string | null;
  card_type?: string;
  review_mode?: string | null;
  prompt?: ReviewPromptPayload | null;
  source_entry_type?: "word" | "phrase" | null;
  source_entry_id?: string | null;
  detail?: ReviewDetailPayload | null;
  schedule_options?: ReviewScheduleOption[];
};

export type StoredRevealState = {
  outcome: "correct_tested" | "remember" | "lookup" | "wrong";
  detail: ReviewDetailPayload | null;
  scheduleOptions: ReviewScheduleOption[];
  selectedSchedule: string;
  selectedOptionId?: string;
  typedResponseValue?: string;
  persisted?: boolean;
};

export type StoredReviewSession = {
  cards: StoredReviewCard[];
  currentIndex: number;
  phase: "learning" | "challenge" | "relearn" | "reveal";
  revealState: StoredRevealState | null;
  typedAnswer: string;
  completed?: boolean;
};

export const loadStoredReviewSession = (): StoredReviewSession | null => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(REVIEW_RESUME_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as StoredReviewSession | null;
    if (!parsed || !Array.isArray(parsed.cards) || parsed.cards.length === 0) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

export const persistReviewSession = (payload: StoredReviewSession): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(REVIEW_RESUME_STORAGE_KEY, JSON.stringify(payload));
};

export const clearStoredReviewSession = (): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(REVIEW_RESUME_STORAGE_KEY);
};

export const advanceStoredReviewSession = (
  session: StoredReviewSession,
): StoredReviewSession => {
  if (session.currentIndex + 1 < session.cards.length) {
    return {
      ...session,
      currentIndex: session.currentIndex + 1,
      phase: "challenge",
      revealState: null,
      typedAnswer: "",
    };
  }
  return {
    ...session,
    completed: true,
    phase: "challenge",
    revealState: null,
    typedAnswer: "",
  };
};
