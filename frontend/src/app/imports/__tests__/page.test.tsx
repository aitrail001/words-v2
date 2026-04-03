import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportsPage from "@/app/imports/page";
import {
  bulkDeleteImportJobs,
  createWordListImport,
  deleteImportJob,
  listImportJobs,
} from "@/lib/imports-client";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/lib/imports-client", () => ({
  bulkDeleteImportJobs: jest.fn(),
  createWordListImport: jest.fn(),
  deleteImportJob: jest.fn(),
  listImportJobs: jest.fn(),
  getImportJob: jest.fn(),
  getImportElapsedSeconds: jest.fn((job) => job.processing_duration_seconds ?? null),
  getImportProgressPercent: jest.fn((job) => {
    const total = job.progress_total || job.total_items;
    const completed = job.progress_total ? job.progress_completed : job.processed_items;
    if (!total) return 0;
    return Math.round((completed / total) * 100);
  }),
  isImportJobTerminal: jest.fn((status: string) => status === "completed" || status === "failed"),
}));

describe("ImportsPage", () => {
  const mockBulkDeleteImportJobs = bulkDeleteImportJobs as jest.Mock;
  const mockCreateWordListImport = createWordListImport as jest.Mock;
  const mockDeleteImportJob = deleteImportJob as jest.Mock;
  const mockListImportJobs = listImportJobs as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockPush.mockReset();
    window.confirm = jest.fn(() => true);
    mockListImportJobs.mockImplementation(async (_limit: number, statusView?: string) => {
      if (statusView === "history") {
        return [
          {
            id: "history-1",
            status: "completed",
            list_name: "Imported list",
            source_filename: "book.epub",
            source_title: "Book Title",
            source_author: "Alice, Bob",
            source_publisher: "Publisher House",
            source_published_year: 2024,
            source_isbn: "9781234567890",
            total_items: 10,
            processed_items: 10,
            progress_stage: "completed",
            progress_total: 10,
            progress_completed: 10,
            progress_current_label: "Completed from cached import",
            word_entry_count: 8,
            phrase_entry_count: 2,
            matched_entry_count: 10,
            total_entries_extracted: 10,
            processing_duration_seconds: 12,
            from_cache: true,
            created_at: "2026-04-03T00:00:00.000Z",
          },
        ];
      }
      return [];
    });
  });

  it("renders import form and navigation links", async () => {
    render(<ImportsPage />);

    expect(await screen.findByTestId("imports-page-title")).toBeInTheDocument();
    expect(screen.getByTestId("imports-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("imports-word-lists-link")).toHaveAttribute("href", "/word-lists");
    expect(screen.getByTestId("imports-upload-input")).toBeInTheDocument();
  });

  it("submits epub and routes to dedicated import detail page", async () => {
    const user = userEvent.setup();
    mockCreateWordListImport.mockResolvedValueOnce({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "book.epub",
      progress_stage: "completed",
      progress_total: 2,
      progress_completed: 2,
      progress_current_label: "Import completed",
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
      expect(mockPush).toHaveBeenCalledWith("/imports/job-1");
    });
  });

  it("shows labeled history metadata and supports single deletion", async () => {
    const user = userEvent.setup();
    mockDeleteImportJob.mockResolvedValueOnce(undefined);

    render(<ImportsPage />);

    await user.click(await screen.findByTestId("imports-history-toggle"));
    expect(await screen.findByTestId("imports-history-jobs-list")).toHaveTextContent("Title:");
    expect(screen.getByTestId("imports-history-jobs-list")).toHaveTextContent("Author:");
    expect(screen.getByTestId("imports-history-jobs-list")).toHaveTextContent("Publisher:");
    expect(screen.getByTestId("imports-history-jobs-list")).toHaveTextContent("Published:");
    expect(screen.getByTestId("imports-history-jobs-list")).toHaveTextContent("ISBN:");
    expect(screen.getByTestId("imports-progress-label-history-1")).toHaveTextContent("Completed from cached import");

    await user.click(screen.getByTestId("imports-delete-history-1"));
    await waitFor(() => expect(mockDeleteImportJob).toHaveBeenCalledWith("history-1"));
  });

  it("normalizes cached filename-like titles for display", async () => {
    mockListImportJobs.mockImplementation(async (_limit: number, statusView?: string) => {
      if (statusView === "history") {
        return [
          {
            id: "history-1",
            status: "completed",
            list_name: "Imported list",
            source_filename: "Pygmalion by George Bernard Shaw ( PDFDrive.com ).epub",
            source_title: "Pygmalion by George Bernard Shaw ( PDFDrive.com ).epub",
            source_author: "George Bernard Shaw",
            source_publisher: null,
            source_published_year: 1913,
            source_isbn: null,
            total_items: 10,
            processed_items: 10,
            progress_stage: "completed",
            progress_total: 10,
            progress_completed: 10,
            progress_current_label: "Completed from cached import",
            word_entry_count: 8,
            phrase_entry_count: 2,
            matched_entry_count: 10,
            total_entries_extracted: 10,
            processing_duration_seconds: 12,
            from_cache: true,
            created_at: "2026-04-03T00:00:00.000Z",
          },
        ];
      }
      return [];
    });

    render(<ImportsPage />);
    await userEvent.click(await screen.findByTestId("imports-history-toggle"));
    expect(await screen.findByTestId("imports-title-history-1")).toHaveTextContent("Title: Pygmalion");
    expect(screen.getByTestId("imports-title-history-1")).not.toHaveTextContent("PDFDrive");
    expect(screen.getByTestId("imports-title-history-1")).not.toHaveTextContent(".epub");
  });

  it("supports bulk deletion for selected import history rows", async () => {
    const user = userEvent.setup();
    mockBulkDeleteImportJobs.mockResolvedValueOnce(undefined);
    mockListImportJobs.mockImplementation(async (_limit: number, statusView?: string) => {
      if (statusView === "history") {
        return [
          {
            id: "history-1",
            status: "completed",
            list_name: "Imported list",
            source_filename: "book.epub",
            source_title: "Book Title",
            source_author: "Alice, Bob",
            source_publisher: "Publisher House",
            source_published_year: 2024,
            source_isbn: "9781234567890",
            total_items: 10,
            processed_items: 10,
            progress_stage: "completed",
            progress_total: 10,
            progress_completed: 10,
            progress_current_label: "Completed from cached import",
            word_entry_count: 8,
            phrase_entry_count: 2,
            matched_entry_count: 10,
            total_entries_extracted: 10,
            processing_duration_seconds: 12,
            from_cache: true,
            created_at: "2026-04-03T00:00:00.000Z",
          },
          {
            id: "history-2",
            status: "failed",
            list_name: "Second import",
            source_filename: "second.epub",
            source_title: "Second Title",
            source_author: "Carol",
            source_publisher: "Second Press",
            source_published_year: 2021,
            source_isbn: "9781111111111",
            total_items: 5,
            processed_items: 5,
            progress_stage: "failed",
            progress_total: 5,
            progress_completed: 5,
            progress_current_label: "Import failed",
            word_entry_count: 5,
            phrase_entry_count: 0,
            matched_entry_count: 5,
            total_entries_extracted: 5,
            processing_duration_seconds: 6,
            from_cache: false,
            created_at: "2026-04-02T00:00:00.000Z",
          },
        ];
      }
      return [];
    });

    render(<ImportsPage />);
    await user.click(await screen.findByTestId("imports-history-toggle"));
    await user.click(screen.getByTestId("imports-history-select-all"));
    await user.click(screen.getByTestId("imports-history-delete-selected"));

    await waitFor(() => {
      expect(mockBulkDeleteImportJobs).toHaveBeenCalledWith(["history-1", "history-2"]);
    });
  });
});
