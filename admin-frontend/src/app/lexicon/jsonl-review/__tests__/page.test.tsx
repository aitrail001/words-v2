import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconJsonlReviewPage from "@/app/lexicon/jsonl-review/page";
import {
  loadLexiconJsonlReviewSession,
  materializeLexiconJsonlReviewOutputs,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";

jest.mock("@/lib/lexicon-jsonl-reviews-client", () => ({
  loadLexiconJsonlReviewSession: jest.fn(),
  materializeLexiconJsonlReviewOutputs: jest.fn(),
  updateLexiconJsonlReviewItem: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconJsonlReviewPage", () => {
  const mockLoadSession = loadLexiconJsonlReviewSession as jest.Mock;
  const mockUpdateItem = updateLexiconJsonlReviewItem as jest.Mock;
  const mockMaterialize = materializeLexiconJsonlReviewOutputs as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockLoadSession.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/review.decisions.jsonl",
      output_dir: "/tmp/materialized",
      total_items: 2,
      pending_count: 1,
      approved_count: 1,
      rejected_count: 0,
      items: [
        {
          entry_id: "word:bank",
          entry_type: "word",
          normalized_form: "bank",
          display_text: "bank",
          review_priority: "normal",
          warning_count: 0,
          warning_labels: [],
          review_summary: {
            sense_count: 1,
            form_variant_count: 1,
            confusable_count: 0,
            provenance_sources: ["snapshot"],
            primary_definition: "a financial institution",
            primary_example: "She went to the bank.",
          },
          review_status: "approved",
          decision_reason: "ready",
          reviewed_at: "2026-03-21T01:00:00Z",
          compiled_payload: { entry_id: "word:bank", word: "bank" },
        },
        {
          entry_id: "phrase:break-a-leg",
          entry_type: "phrase",
          normalized_form: "break a leg",
          display_text: "break a leg",
          review_priority: "warning",
          warning_count: 2,
          warning_labels: ["missing_source_provenance", "missing_examples"],
          review_summary: {
            sense_count: 1,
            form_variant_count: 0,
            confusable_count: 0,
            provenance_sources: [],
            primary_definition: "good luck",
            primary_example: null,
          },
          review_status: "pending",
          decision_reason: null,
          reviewed_at: null,
          compiled_payload: { entry_id: "phrase:break-a-leg", word: "break a leg" },
        },
      ],
    });
    mockUpdateItem.mockResolvedValue({
      entry_id: "phrase:break-a-leg",
      entry_type: "phrase",
      normalized_form: "break a leg",
      display_text: "break a leg",
      review_priority: "warning",
      warning_count: 2,
      warning_labels: ["missing_source_provenance", "missing_examples"],
      review_summary: {
        sense_count: 1,
        form_variant_count: 0,
        confusable_count: 0,
        provenance_sources: [],
        primary_definition: "good luck",
        primary_example: null,
      },
      review_status: "rejected",
      decision_reason: "regen",
      reviewed_at: "2026-03-21T02:00:00Z",
      compiled_payload: { entry_id: "phrase:break-a-leg", word: "break a leg" },
    });
    mockMaterialize.mockResolvedValue({
      approved_count: 1,
      rejected_count: 1,
      regenerate_count: 1,
      approved_output_path: "/tmp/materialized/approved.jsonl",
      rejected_output_path: "/tmp/materialized/rejected.jsonl",
      regenerate_output_path: "/tmp/materialized/regenerate.jsonl",
      decisions_output_path: "/tmp/review.decisions.jsonl",
    });
  });

  it("loads rows, filters them, saves a decision sidecar update, and materializes outputs", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/jsonl-review?artifactPath=%2Ftmp%2Fwords.enriched.jsonl&decisionsPath=%2Ftmp%2Freview.decisions.jsonl&outputDir=%2Ftmp%2Fmaterialized&sourceReference=lexicon-20260321-wordfreq&autostart=1",
    );
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-jsonl-review-title")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent("Artifact: /tmp/words.enriched.jsonl"));
    expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent(
      "Source reference: lexicon-20260321-wordfreq",
    );
    expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent(
      "Output dir: /tmp/materialized",
    );
    expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent(
      "Stage: Alternate review path",
    );
    expect(screen.getByText(/Approve keeps the compiled row eligible for approved\.jsonl, the reviewed file you should import into the final DB\./)).toBeInTheDocument();
    expect(screen.getByText(/Reject records the row in review\.decisions\.jsonl, writes the rejected overlay, and adds a regeneration request row\./)).toBeInTheDocument();
    expect(screen.getByText(/Reopen removes the final decision so the row stays pending until you decide again\./)).toBeInTheDocument();
    expect(screen.getByLabelText("Artifact path")).toHaveValue("/tmp/words.enriched.jsonl");
    expect(screen.getByLabelText("Decisions path")).toHaveValue("/tmp/review.decisions.jsonl");
    expect(screen.getByLabelText("Output directory")).toHaveValue("/tmp/materialized");

    await user.type(screen.getByLabelText("Artifact path"), "/tmp/words.enriched.jsonl");
    await user.type(screen.getByLabelText("Decisions path"), "/tmp/review.decisions.jsonl");
    await user.type(screen.getByLabelText("Output directory"), "/tmp/materialized");
    await user.click(screen.getByRole("button", { name: "Load Artifact" }));

    await waitFor(() =>
      expect(mockLoadSession).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/review.decisions.jsonl",
        outputDir: "/tmp/materialized",
      }),
    );
    await waitFor(() => expect(screen.getAllByText("break a leg").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("missing_source_provenance").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText("good luck")).toBeInTheDocument());
    expect(screen.getByText("Risk first")).toBeInTheDocument();
    expect(screen.getByText(/Shortcuts:/)).toBeInTheDocument();

    await user.click(screen.getByText("Risk first"));
    await user.keyboard("j");
    await waitFor(() => expect(screen.getByText("break a leg")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("Search entry id or display text"), "break");
    expect(screen.getAllByText("break a leg").length).toBeGreaterThan(0);
    expect(screen.queryByText("bank")).not.toBeInTheDocument();

    await user.click(screen.getAllByText("break a leg")[0]);
    await user.type(screen.getByTestId("jsonl-review-decision-reason"), "regen");
    await user.click(screen.getByTestId("jsonl-review-reject-button"));

    await waitFor(() =>
      expect(mockUpdateItem).toHaveBeenCalledWith("phrase:break-a-leg", {
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/review.decisions.jsonl",
        reviewStatus: "rejected",
        decisionReason: "regen",
      }),
    );

    await user.clear(screen.getByPlaceholderText("Search entry id or display text"));
    await user.click(screen.getByText("Risk first"));
    await user.keyboard("j");
    await user.keyboard("a");
    await waitFor(() =>
      expect(mockUpdateItem).toHaveBeenCalledWith("word:bank", {
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/review.decisions.jsonl",
        reviewStatus: "approved",
        decisionReason: "ready",
      }),
    );

    await user.click(screen.getByRole("button", { name: "Materialize Outputs" }));
    await waitFor(() =>
      expect(mockMaterialize).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/review.decisions.jsonl",
        outputDir: "/tmp/materialized",
      }),
    );
    await waitFor(() => expect(screen.getByText("approved.jsonl")).toBeInTheDocument());
    expect(screen.getByText(/approved\.jsonl is the reviewed file for Import DB\./)).toBeInTheDocument();
  });
});
