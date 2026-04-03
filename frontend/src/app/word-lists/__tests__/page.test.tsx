import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WordListsPage from "@/app/word-lists/page";
import {
  bulkDeleteWordLists,
  createEmptyWordList,
  listWordLists,
} from "@/lib/imports-client";

jest.mock("@/lib/imports-client", () => ({
  bulkDeleteWordLists: jest.fn(),
  createEmptyWordList: jest.fn(),
  listWordLists: jest.fn(),
}));

describe("WordListsPage", () => {
  const mockBulkDeleteWordLists = bulkDeleteWordLists as jest.Mock;
  const mockCreateEmptyWordList = createEmptyWordList as jest.Mock;
  const mockListWordLists = listWordLists as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockListWordLists.mockResolvedValue([
      {
        id: "list-1",
        name: "My Import",
        user_id: "user-1",
        description: null,
        source_type: "epub",
        source_reference: "job-1",
        created_at: "2026-04-02T00:00:00.000Z",
      },
    ]);
    window.confirm = jest.fn(() => true);
  });

  it("renders its own route with home/import navigation", async () => {
    render(<WordListsPage />);

    expect(screen.getByTestId("word-lists-page-title")).toBeInTheDocument();
    expect(screen.getByTestId("word-lists-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("word-lists-import-link")).toHaveAttribute("href", "/imports");
    await waitFor(() => expect(mockListWordLists).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId("word-list-open-list-1")).toHaveAttribute("href", "/word-lists/list-1");
  });

  it("creates a new word list from the index modal", async () => {
    const user = userEvent.setup();
    mockCreateEmptyWordList.mockResolvedValueOnce({
      id: "list-2",
      name: "Fresh List",
      user_id: "user-1",
      description: "Notes",
      source_type: null,
      source_reference: null,
      created_at: "2026-04-03T00:00:00.000Z",
    });

    render(<WordListsPage />);
    await waitFor(() => expect(screen.getByTestId("word-lists-new-button")).toBeInTheDocument());

    await user.click(screen.getByTestId("word-lists-new-button"));
    await user.type(screen.getByTestId("word-lists-create-name-input"), "Fresh List");
    await user.type(screen.getByTestId("word-lists-create-description-input"), "Notes");
    await user.click(screen.getByTestId("word-lists-create-submit-button"));

    await waitFor(() => {
      expect(mockCreateEmptyWordList).toHaveBeenCalledWith({
        name: "Fresh List",
        description: "Notes",
      });
      expect(screen.getByTestId("word-lists-list")).toHaveTextContent("Fresh List");
    });
  });

  it("supports bulk delete from the index", async () => {
    const user = userEvent.setup();
    mockBulkDeleteWordLists.mockResolvedValueOnce(undefined);

    render(<WordListsPage />);
    await waitFor(() => expect(screen.getByTestId("word-list-select-list-1")).toBeInTheDocument());

    await user.click(screen.getByTestId("word-list-select-list-1"));
    await user.click(screen.getByTestId("word-lists-bulk-delete-button"));

    await waitFor(() => {
      expect(mockBulkDeleteWordLists).toHaveBeenCalledWith(["list-1"]);
      expect(screen.getByTestId("word-lists-empty-state")).toBeInTheDocument();
    });
  });
});
