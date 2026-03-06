import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportsPage from "@/app/imports/page";
import { createWordListImport, listWordLists } from "@/lib/imports-client";

jest.mock("@/lib/imports-client", () => ({
  createWordListImport: jest.fn(),
  getImportJob: jest.fn(),
  listWordLists: jest.fn(),
  getImportProgressPercent: jest.fn((job) => {
    if (!job.total_items) return 0;
    return Math.round((job.processed_items / job.total_items) * 100);
  }),
  isImportJobTerminal: jest.fn((status: string) =>
    status === "completed" || status === "failed",
  ),
}));

describe("ImportsPage", () => {
  const mockCreateWordListImport = createWordListImport as jest.Mock;
  const mockListWordLists = listWordLists as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockListWordLists.mockResolvedValue([]);
  });

  it("renders import form", async () => {
    render(<ImportsPage />);

    expect(screen.getByTestId("imports-page-title")).toBeInTheDocument();
    expect(screen.getByTestId("imports-upload-input")).toBeInTheDocument();
    expect(screen.getByTestId("imports-submit-button")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockListWordLists).toHaveBeenCalledTimes(1);
    });
  });

  it("submits epub and renders queued import row", async () => {
    const user = userEvent.setup();
    mockCreateWordListImport.mockResolvedValueOnce({
      id: "job-1",
      status: "queued",
      list_name: "My Import",
      source_filename: "book.epub",
      total_items: 0,
      processed_items: 0,
    });

    render(<ImportsPage />);

    const fileInput = screen.getByTestId("imports-upload-input") as HTMLInputElement;
    const file = new File(["epub content"], "book.epub", {
      type: "application/epub+zip",
    });

    await user.upload(fileInput, file);
    await user.click(screen.getByTestId("imports-submit-button"));

    await waitFor(() => {
      expect(mockCreateWordListImport).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("imports-row-job-1")).toBeInTheDocument();
      expect(screen.getByText("queued")).toBeInTheDocument();
    });
  });
});
