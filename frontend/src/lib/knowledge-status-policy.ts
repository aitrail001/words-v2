import type { KnowledgeStatus } from "@/lib/knowledge-map-client";

export type KnowledgeAction = {
  status: KnowledgeStatus;
  label: string;
};

export type KnowledgeActionSurface = "detail" | "range";

const DETAIL_ACTIONS: Record<KnowledgeStatus, KnowledgeAction[]> = {
  undecided: [
    { status: "to_learn", label: "Should Learn" },
    { status: "known", label: "Already Know" },
  ],
  to_learn: [
    { status: "learning", label: "Learn Now" },
    { status: "known", label: "Already Know" },
  ],
  learning: [{ status: "known", label: "Already Knew" }],
  known: [{ status: "to_learn", label: "Should Learn" }],
};

const RANGE_ACTIONS: Record<KnowledgeStatus, KnowledgeAction[]> = {
  undecided: [
    { status: "to_learn", label: "Should Learn" },
    { status: "known", label: "Already Know" },
  ],
  to_learn: [
    { status: "learning", label: "Learn Now" },
    { status: "known", label: "Already Know" },
  ],
  learning: [],
  known: [{ status: "to_learn", label: "Should Learn" }],
};

const TRIAGE_SELECT_OPTIONS: KnowledgeAction[] = [
  { status: "undecided", label: "New" },
  { status: "to_learn", label: "To Learn" },
  { status: "known", label: "Already knew" },
];

export function getKnowledgeStatusActions(
  status: KnowledgeStatus,
  surface: KnowledgeActionSurface,
): KnowledgeAction[] {
  return surface === "detail" ? DETAIL_ACTIONS[status] : RANGE_ACTIONS[status];
}

export function getKnowledgeStatusSelectOptions(status: KnowledgeStatus): KnowledgeAction[] {
  if (status === "learning") {
    return [{ status: "learning", label: "Learning" }];
  }
  return TRIAGE_SELECT_OPTIONS;
}

export function shouldOpenLearningFlow(previousStatus: KnowledgeStatus, nextStatus: KnowledgeStatus): boolean {
  return previousStatus === "to_learn" && nextStatus === "learning";
}
