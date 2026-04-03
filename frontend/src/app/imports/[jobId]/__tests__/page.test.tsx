import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportJobDetailRoute from "@/app/imports/[jobId]/page";
import { createListFromImport, getImportEntries, getImportJob } from "@/lib/imports-client";

jest.mock("@/lib/imports-client", () => ({
  createListFromImport: jest.fn(),
  getImportElapsedSeconds: jest.fn((job) => job.processing_duration_seconds ?? null),
  getImportEntries: jest.fn(),
  getImportJob: jest.fn(),
  getImportProgressPercent: jest.fn((job) => {
    const total = job.progress_total || job.total_items;
    const completed = job.progress_total ? job.progress_completed : job.processed_items;
    if (!total) return 0;
    return Math.round((completed / total) * 100);
  }),
  isImportJobTerminal: jest.fn((status: string) => status === "completed" || status === "failed"),
}));

describe("ImportJobDetailRoute", () => {
  const mockCreateListFromImport = createListFromImport as jest.Mock;
  const mockGetImportEntries = getImportEntries as jest.Mock;
  const mockGetImportJob = getImportJob as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetImportJob.mockResolvedValue({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "book.epub",
      source_title: "Book Title",
      source_author: "Alice, Bob",
      source_publisher: "Publisher House",
      source_published_year: 2024,
      source_isbn: "9781234567890",
      total_items: 2,
      processed_items: 2,
      progress_stage: "completed",
      progress_total: 2,
      progress_completed: 2,
      progress_current_label: "Import completed",
      word_entry_count: 1,
      phrase_entry_count: 1,
      matched_entry_count: 2,
      total_entries_extracted: 2,
      processing_duration_seconds: 10,
      from_cache: false,
      created_at: "2026-04-03T00:00:00.000Z",
      word_list_id: null,
    });
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

  it("renders dedicated import job metadata and selected review entries", async () => {
    render(await ImportJobDetailRoute({ params: Promise.resolve({ jobId: "job-1" }) }));

    expect(await screen.findByTestId("import-job-detail-title")).toHaveTextContent("Book Title");
    expect(screen.getByTestId("import-job-summary")).toHaveTextContent("Title:");
    expect(screen.getByTestId("import-job-summary")).toHaveTextContent("Author:");
    expect(screen.getByTestId("import-job-summary")).toHaveTextContent("Publisher:");
    expect(screen.getByTestId("import-job-summary")).toHaveTextContent("Published:");
    expect(screen.getByTestId("import-job-summary")).toHaveTextContent("ISBN:");
    await waitFor(() => {
      expect(screen.getByTestId("imports-selected-count")).toHaveTextContent("2 selected");
    });
    expect(screen.getByTestId("import-job-back-link")).toHaveAttribute("href", "/imports");
  });

  it("shows live progress details for an active import", async () => {
    mockGetImportJob.mockResolvedValueOnce({
      id: "job-1",
      status: "processing",
      list_name: "My Import",
      source_filename: "book.epub",
      source_title: "Book Title",
      source_author: "Alice, Bob",
      source_publisher: "Publisher House",
      source_published_year: 2024,
      source_isbn: "9781234567890",
      total_items: 0,
      processed_items: 0,
      progress_stage: "extracting_text",
      progress_total: 12,
      progress_completed: 4,
      progress_current_label: "Extracting text 4/12",
      word_entry_count: 0,
      phrase_entry_count: 0,
      matched_entry_count: 0,
      total_entries_extracted: 0,
      processing_duration_seconds: null,
      started_at: new Date(Date.now() - 2000).toISOString(),
      from_cache: false,
      created_at: "2026-04-03T00:00:00.000Z",
      word_list_id: null,
    });

    render(await ImportJobDetailRoute({ params: Promise.resolve({ jobId: "job-1" }) }));

    expect(await screen.findByTestId("import-job-progress-label")).toHaveTextContent("Extracting text 4/12");
    expect(screen.getByTestId("import-job-progress-counts")).toHaveTextContent("4/12");
  });

  it("creates a list from the dedicated import detail page", async () => {
    const user = userEvent.setup();
    mockCreateListFromImport.mockResolvedValueOnce({
      id: "list-1",
      name: "My Import",
      user_id: "user-1",
      description: null,
      source_type: "epub",
      source_reference: "job-1",
      created_at: "2026-04-03T00:00:00.000Z",
    });

    render(await ImportJobDetailRoute({ params: Promise.resolve({ jobId: "job-1" }) }));

    await user.clear(await screen.findByTestId("imports-create-list-name-input"));
    await user.type(screen.getByTestId("imports-create-list-name-input"), "My Import");
    await user.click(screen.getByTestId("imports-create-list-button"));

    await waitFor(() => {
      expect(mockCreateListFromImport).toHaveBeenCalledWith("job-1", expect.objectContaining({ name: "My Import" }));
      expect(screen.getByTestId("imports-created-list-panel")).toBeInTheDocument();
      expect(screen.getByTestId("imports-open-created-list-link")).toHaveAttribute("href", "/word-lists/list-1");
    });
  });

  it("normalizes filename-like cached titles on the detail page", async () => {
    mockGetImportJob.mockResolvedValueOnce({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "Pygmalion by George Bernard Shaw ( PDFDrive.com ).epub",
      source_title: "Pygmalion by George Bernard Shaw ( PDFDrive.com ).epub",
      source_author: "George Bernard Shaw",
      source_publisher: null,
      source_published_year: 1913,
      source_isbn: null,
      total_items: 2,
      processed_items: 2,
      progress_stage: "completed",
      progress_total: 2,
      progress_completed: 2,
      progress_current_label: "Completed from cached import",
      word_entry_count: 1,
      phrase_entry_count: 1,
      matched_entry_count: 2,
      total_entries_extracted: 2,
      processing_duration_seconds: 10,
      from_cache: true,
      created_at: "2026-04-03T00:00:00.000Z",
      word_list_id: null,
    });

    render(await ImportJobDetailRoute({ params: Promise.resolve({ jobId: "job-1" }) }));

    expect(await screen.findByTestId("import-job-detail-title")).toHaveTextContent("Pygmalion");
    expect(screen.getByTestId("import-job-summary-title")).toHaveTextContent("Title: Pygmalion");
    expect(screen.getByTestId("import-job-summary-title")).not.toHaveTextContent("PDFDrive");
  });
});
