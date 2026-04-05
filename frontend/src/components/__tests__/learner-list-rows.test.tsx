import { render, screen } from "@testing-library/react";
import { LearnerListRows } from "@/components/learner-list-rows";

describe("LearnerListRows", () => {
  it("does not expose learning as a triage option for non-learning entries", () => {
    render(
      <LearnerListRows
        items={[
          {
            entry_type: "word",
            entry_id: "word-1",
            display_text: "bank",
            status: "to_learn",
            primary_definition: "A financial institution.",
            translation: "银行",
          },
        ]}
        showTranslations
        emptyMessage="Empty"
        listTestId="learner-list"
        emptyTestId="learner-list-empty"
        onStatusChange={() => undefined}
      />,
    );

    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["New", "To Learn", "Already knew"]);
  });

  it("keeps the current learning value selectable while still showing triage statuses", () => {
    render(
      <LearnerListRows
        items={[
          {
            entry_type: "word",
            entry_id: "word-1",
            display_text: "bank",
            status: "learning",
            primary_definition: "A financial institution.",
            translation: "银行",
          },
        ]}
        showTranslations
        emptyMessage="Empty"
        listTestId="learner-list"
        emptyTestId="learner-list-empty"
        onStatusChange={() => undefined}
      />,
    );

    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Learning"]);
  });

  it("renders rank plus bilingual example content when available", () => {
    render(
      <LearnerListRows
        items={[
          {
            entry_type: "word",
            entry_id: "word-1",
            display_text: "bank",
            browse_rank: 20,
            status: "to_learn",
            primary_definition: "A financial institution.",
            primary_example: "I went to the bank.",
            primary_example_translation: "我去了银行。",
            translation: "银行",
          },
        ]}
        showTranslations
        emptyMessage="Empty"
        listTestId="learner-list"
        emptyTestId="learner-list-empty"
      />,
    );

    expect(screen.getByText("#20")).toBeInTheDocument();
    expect(screen.getByText("A financial institution.")).toBeInTheDocument();
    expect(screen.getByText("银行")).toBeInTheDocument();
    expect(screen.getByText("I went to the bank.")).toBeInTheDocument();
    expect(screen.getByText("我去了银行。")).toBeInTheDocument();
  });
});
