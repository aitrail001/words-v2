import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportsPage from "@/app/imports/page";
import {
  createListFromImport,
  createWordListImport,
  getImportEntries,
  listImportJobs,
} from "@/lib/imports-client";

jest.mock("@/lib/imports-client", () => ({
  createWordListImport: jest.fn(),
  createListFromImport: jest.fn(),
  getImportEntries: jest.fn(),
  listImportJobs: jest.fn(),
  getImportJob: jest.fn(),
  getImportProgressPercent: jest.fn((job) => {
    if (!job.total_items) return 0;
    return Math.round((job.processed_items / job.total_items) * 100);
  }),
  isImportJobTerminal: jest.fn((status: string) => status === "completed" || status === "failed"),
}));

describe("ImportsPage", () => {
  const mockCreateWordListImport = createWordListImport as jest.Mock;
  const mockCreateListFromImport = createListFromImport as jest.Mock;
  const mockGetImportEntries = getImportEntries as jest.Mock;
  const mockListImportJobs = listImportJobs as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockListImportJobs.mockResolvedValue([]);
    mockGetImportEntries.mockResolvedValue({
      total: 2,
      items: [
        {
          entry_type: "word",
          entry_id: "word-1",
          display_text: "run",
          frequency_count: 3,
          browse_rank: 10,
          normalized_form: "run",
          cefr_level: "A1",
          phrase_kind: null,
        },
        {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "make up for",
          frequency_count: 2,
          browse_rank: 120,
          normalized_form: "make up for",
          cefr_level: "B2",
          phrase_kind: "phrasal_verb",
        },
      ],
    });
  });

  it("renders import form and navigation links", async () => {
    render(<ImportsPage />);

    expect(await screen.findByTestId("imports-page-title")).toBeInTheDocument();
    expect(screen.getByTestId("imports-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("imports-word-lists-link")).toHaveAttribute("href", "/word-lists");
    expect(screen.getByTestId("imports-upload-input")).toBeInTheDocument();
    expect(screen.getByTestId("imports-submit-button")).toBeInTheDocument();
  });

  it("submits epub and renders review panel for completed import", async () => {
    const user = userEvent.setup();
    mockCreateWordListImport.mockResolvedValueOnce({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "book.epub",
      total_items: 2,
      processed_items: 2,
      created_at: "2026-04-02T00:00:00.000Z",
      word_list_id: null,
    });

    render(<ImportsPage />);

    const fileInput = screen.getByTestId("imports-upload-input") as HTMLInputElement;
    const file = new File(["epub content"], "book.epub", { type: "application/epub+zip" });

    await user.upload(fileInput, file);
    await user.click(screen.getByTestId("imports-submit-button"));

    await waitFor(() => {
      expect(mockCreateWordListImport).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("imports-review-panel")).toBeInTheDocument();
      expect(screen.getByTestId("imports-selected-count")).toHaveTextContent("2 selected");
    });
  });

  it("creates list from selected review entries and links into the word-list manager", async () => {
    const user = userEvent.setup();
    mockCreateWordListImport.mockResolvedValueOnce({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "book.epub",
      total_items: 2,
      processed_items: 2,
      created_at: "2026-04-02T00:00:00.000Z",
      word_list_id: null,
    });
    mockCreateListFromImport.mockResolvedValueOnce({
      id: "list-1",
      name: "My Import",
      user_id: "user-1",
      description: null,
      source_type: "epub",
      source_reference: "job-1",
      created_at: "2026-04-02T00:00:00.000Z",
    });

    render(<ImportsPage />);

    const fileInput = screen.getByTestId("imports-upload-input") as HTMLInputElement;
    const file = new File(["epub content"], "book.epub", { type: "application/epub+zip" });
    await user.upload(fileInput, file);
    await user.click(screen.getByTestId("imports-submit-button"));

    await waitFor(() => expect(screen.getByTestId("imports-create-list-button")).toBeInTheDocument());
    await user.click(screen.getByTestId("imports-create-list-button"));

    await waitFor(() => {
      expect(mockCreateListFromImport).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("imports-created-list-panel")).toBeInTheDocument();
      expect(screen.getByTestId("imports-open-created-list-link")).toHaveAttribute(
        "href",
        "/word-lists?list=list-1",
      );
    });
  });
});
