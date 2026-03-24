import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import KnowledgeMapPage from "@/app/knowledge-map/page";
import {
  getKnowledgeMapOverview,
} from "@/lib/knowledge-map-client";

jest.mock("@/lib/knowledge-map-client");

describe("KnowledgeMapPage", () => {
  const mockGetKnowledgeMapOverview = getKnowledgeMapOverview as jest.MockedFunction<typeof getKnowledgeMapOverview>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetKnowledgeMapOverview.mockResolvedValue({
      bucket_size: 100,
      total_entries: 200,
      ranges: [
        {
          range_start: 1,
          range_end: 100,
          total_entries: 2,
          counts: { undecided: 1, to_learn: 1, learning: 0, known: 0 },
        },
        {
          range_start: 101,
          range_end: 200,
          total_entries: 2,
          counts: { undecided: 0, to_learn: 1, learning: 1, known: 0 },
        },
      ],
    });
  });

  it("renders only the full-map overview and links ranges to dedicated range routes", async () => {
    render(<KnowledgeMapPage />);

    expect(await screen.findByText(/full knowledge map/i)).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-map-mobile-shell")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-map-tile-grid")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /1-100/i })).toHaveAttribute(
      "href",
      "/knowledge-map/range/1",
    );
    expect(screen.getByRole("link", { name: /101-200/i })).toHaveAttribute(
      "href",
      "/knowledge-map/range/101",
    );
    expect(screen.queryByTestId("knowledge-card-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("knowledge-range-strip")).not.toBeInTheDocument();
    expect(screen.queryByText(/^knowledge map$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/loading range/i)).not.toBeInTheDocument();
  });
});
