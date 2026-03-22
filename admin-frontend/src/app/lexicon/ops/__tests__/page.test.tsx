import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconOpsPage from "@/app/lexicon/ops/page";
import { useRouter } from "next/navigation";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  getLexiconOpsSnapshot,
  listLexiconOpsSnapshots,
} from "@/lib/lexicon-ops-client";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/lexicon-ops-client", () => ({
  listLexiconOpsSnapshots: jest.fn(),
  getLexiconOpsSnapshot: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
  readRefreshToken: jest.fn(() => null),
  storeTokens: jest.fn(),
  clearTokens: jest.fn(),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconOpsPage", () => {
  const mockListLexiconOpsSnapshots = listLexiconOpsSnapshots as jest.Mock;
  const mockGetLexiconOpsSnapshot = getLexiconOpsSnapshot as jest.Mock;
  const mockReadAccessToken = readAccessToken as jest.Mock;
  const mockRedirectToLogin = redirectToLogin as jest.Mock;
  const mockUseRouter = useRouter as jest.Mock;
  const push = jest.fn();

  const snapshots = [
    {
      snapshot: "words-100-20260312",
      snapshot_path: "/data/lexicon/snapshots/words-100-20260312",
      snapshot_id: "lexicon-20260312-wordnet-wordfreq",
      updated_at: "2026-03-12T07:40:00Z",
      artifact_counts: {
        lexemes: 100,
        senses: 320,
        enrichments: 48,
        compiled_words: 0,
        selection_decisions: 100,
        ambiguous_forms: 9,
      },
      has_enrichments: true,
      has_compiled_export: true,
      has_selection_decisions: true,
      has_ambiguous_forms: true,
      workflow_stage: "approved_ready_for_import",
      recommended_action: "open_import_db",
      preferred_review_artifact_path: "/data/lexicon/snapshots/words-100-20260312/words.enriched.jsonl",
      preferred_import_artifact_path: "/data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
      outside_portal_steps: [
        "Run import-db with /data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
        "Verify the imported rows in DB Inspector after import-db completes for snapshot_path /data/lexicon/snapshots/words-100-20260312",
      ],
    },
    {
      snapshot: "words-50-20260311",
      snapshot_path: "/data/lexicon/snapshots/words-50-20260311",
      snapshot_id: "lexicon-20260311-wordnet-wordfreq",
      updated_at: "2026-03-11T07:40:00Z",
      artifact_counts: {
        lexemes: 50,
        senses: 156,
        enrichments: 156,
        compiled_words: 50,
        selection_decisions: 50,
        ambiguous_forms: 0,
      },
      has_enrichments: true,
      has_compiled_export: true,
      has_selection_decisions: true,
      has_ambiguous_forms: false,
      workflow_stage: "compiled_ready_for_review",
      recommended_action: "open_compiled_review",
      preferred_review_artifact_path: "/data/lexicon/snapshots/words-50-20260311/words.enriched.jsonl",
      preferred_import_artifact_path: null,
      outside_portal_steps: [
        "Review /data/lexicon/snapshots/words-50-20260311/words.enriched.jsonl in Compiled Review or JSONL Review",
        "Materialize or export reviewed/approved.jsonl under snapshot_path /data/lexicon/snapshots/words-50-20260311 before import-db",
      ],
    },
    {
      snapshot: "words-raw-20260310",
      snapshot_path: "/data/lexicon/snapshots/words-raw-20260310",
      snapshot_id: "lexicon-20260310-wordnet-wordfreq",
      updated_at: "2026-03-10T07:40:00Z",
      artifact_counts: {
        lexemes: 80,
        senses: 240,
        enrichments: 0,
        compiled_words: 0,
        selection_decisions: 0,
        ambiguous_forms: 0,
      },
      has_enrichments: false,
      has_compiled_export: false,
      has_selection_decisions: false,
      has_ambiguous_forms: false,
      workflow_stage: "base_artifacts",
      recommended_action: "run_compile_export",
      preferred_review_artifact_path: null,
      preferred_import_artifact_path: null,
      outside_portal_steps: [
        "Run enrich and compile-export outside the portal for snapshot_path /data/lexicon/snapshots/words-raw-20260310",
      ],
    },
  ];

  const detail = {
    snapshot: "words-100-20260312",
    snapshot_path: "/data/lexicon/snapshots/words-100-20260312",
    snapshot_id: "lexicon-20260312-wordnet-wordfreq",
    updated_at: "2026-03-12T07:40:00Z",
    artifact_counts: {
      lexemes: 100,
      senses: 320,
      enrichments: 48,
      compiled_words: 0,
      selection_decisions: 100,
      ambiguous_forms: 9,
    },
    has_enrichments: true,
    has_compiled_export: false,
    has_selection_decisions: true,
    has_ambiguous_forms: true,
    workflow_stage: "approved_ready_for_import",
    recommended_action: "open_import_db",
    preferred_review_artifact_path: "/data/lexicon/snapshots/words-100-20260312/words.enriched.jsonl",
    preferred_import_artifact_path: "/data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
    outside_portal_steps: [
      "Run import-db with /data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
      "Verify the imported rows in DB Inspector after import-db completes for snapshot_path /data/lexicon/snapshots/words-100-20260312",
    ],
    artifacts: [
      {
        file_name: "lexemes.jsonl",
        exists: true,
        row_count: 100,
        size_bytes: 4000,
        modified_at: "2026-03-12T07:35:00Z",
        read_error: null,
      },
      {
        file_name: "enrichments.jsonl",
        exists: true,
        row_count: 48,
        size_bytes: 24000,
        modified_at: "2026-03-12T07:40:00Z",
        read_error: null,
      },
      {
        file_name: "reviewed/approved.jsonl",
        exists: true,
        row_count: 12,
        size_bytes: 3200,
        modified_at: "2026-03-12T07:41:00Z",
        read_error: null,
      },
      {
        file_name: "notes.json",
        exists: true,
        row_count: null,
        size_bytes: 120,
        modified_at: "2026-03-12T07:39:00Z",
        read_error: null,
      },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockReadAccessToken.mockReturnValue("active-token");
    mockListLexiconOpsSnapshots.mockResolvedValue(snapshots);
    mockGetLexiconOpsSnapshot.mockResolvedValue(detail);
    mockUseRouter.mockReturnValue({ push });
  });

  it("loads snapshot list and selected snapshot detail using backend contract fields", async () => {
    render(<LexiconOpsPage />);

    await waitFor(() => {
      expect(mockListLexiconOpsSnapshots.mock.calls.length).toBeGreaterThanOrEqual(1);
      expect(mockGetLexiconOpsSnapshot).toHaveBeenCalledWith("words-100-20260312");
    });

    expect(screen.getByTestId("lexicon-ops-snapshots-list")).toHaveTextContent(
      "words-100-20260312",
    );
    expect(screen.getByTestId("lexicon-ops-snapshots-list")).toHaveTextContent(
      "snapshot_id: lexicon-20260312-wordnet-wordfreq",
    );
    expect(screen.getByTestId("lexicon-ops-detail-panel")).toHaveTextContent(
      "enrichments.jsonl",
    );
    expect(screen.getByTestId("lexicon-ops-detail-panel")).toHaveTextContent(
      "rows: 48",
    );
  });

  it("refreshes snapshots from the refresh action", async () => {
    const user = userEvent.setup();
    render(<LexiconOpsPage />);

    await waitFor(() =>
      expect(mockListLexiconOpsSnapshots.mock.calls.length).toBeGreaterThanOrEqual(1),
    );

    const callsBeforeRefresh = mockListLexiconOpsSnapshots.mock.calls.length;
    await user.click(screen.getByTestId("lexicon-ops-refresh-button"));

    await waitFor(() =>
      expect(mockListLexiconOpsSnapshots.mock.calls.length).toBeGreaterThan(
        callsBeforeRefresh,
      ),
    );
  });

  it("clears stale detail while switching snapshots", async () => {
    const user = userEvent.setup();
    let resolveSecondDetail: ((value: typeof detail) => void) | null = null;

    mockGetLexiconOpsSnapshot
      .mockResolvedValueOnce(detail)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSecondDetail = resolve;
          }),
      );

    render(<LexiconOpsPage />);

    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-detail-panel")).toHaveTextContent(
        "enrichments.jsonl",
      ),
    );

    await user.click(screen.getByTestId("lexicon-ops-snapshot-words-50-20260311"));

    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-detail-panel")).not.toHaveTextContent(
        "enrichments.jsonl",
      ),
    );

    resolveSecondDetail?.({
      ...detail,
      snapshot: "words-50-20260311",
      snapshot_path: "/data/lexicon/snapshots/words-50-20260311",
      snapshot_id: "lexicon-20260311-wordnet-wordfreq",
      artifacts: [
        {
          file_name: "words.enriched.jsonl",
          exists: true,
          row_count: 50,
          size_bytes: 12000,
          modified_at: "2026-03-11T07:40:00Z",
          read_error: null,
        },
      ],
    });

    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-detail-panel")).toHaveTextContent(
        "words.enriched.jsonl",
      ),
    );
  });

  it("redirects unauthenticated users to login", async () => {
    mockReadAccessToken.mockReturnValue(null);

    render(<LexiconOpsPage />);

    await waitFor(() => {
      expect(mockRedirectToLogin).toHaveBeenCalledWith("/lexicon/ops");
    });
  });

  it("offers snapshot launch actions into review, import, and db inspector flows", async () => {
    const user = userEvent.setup();
    render(<LexiconOpsPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-ops-open-jsonl-review")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-import-input-path")).toHaveValue(
        "/data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
      ),
    );

    await user.click(screen.getByTestId("lexicon-ops-open-jsonl-review"));
    await user.click(screen.getByTestId("lexicon-ops-open-compiled-review"));
    await user.click(screen.getByTestId("lexicon-ops-open-import-db"));
    await user.click(screen.getByTestId("lexicon-ops-open-db-inspector"));

    expect(push).toHaveBeenCalledWith(expect.stringContaining("/lexicon/jsonl-review"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("artifactPath=%2Fdata%2Flexicon%2Fsnapshots%2Fwords-100-20260312%2Fwords.enriched.jsonl"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("autostart=1"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("/lexicon/compiled-review"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("/lexicon/import-db"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("inputPath=%2Fdata%2Flexicon%2Fsnapshots%2Fwords-100-20260312%2Freviewed%2Fapproved.jsonl"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("/lexicon/db-inspector"));
  });

  it("shows workflow shell guidance for the selected snapshot", async () => {
    render(<LexiconOpsPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-ops-workflow-shell")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-workflow-stage")).toHaveTextContent("Import approved rows"),
    );
    expect(screen.getByTestId("lexicon-ops-next-step")).toHaveTextContent("Open Import DB");
    expect(screen.getByTestId("lexicon-ops-outside-portal")).toHaveTextContent("reviewed/approved.jsonl");
    expect(screen.getByTestId("lexicon-ops-outside-portal")).toHaveTextContent("snapshot_path");
  });

  it("shows a final-import panel for the selected snapshot", async () => {
    render(<LexiconOpsPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-ops-import-panel")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-ops-import-input-path")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-import-input-path")).toHaveValue(
        "/data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
      ),
    );
    expect(screen.getByTestId("lexicon-ops-import-dry-run-button")).toBeInTheDocument();
    expect(screen.getByTestId("lexicon-ops-import-run-button")).toBeInTheDocument();
  });

  it("disables review and import actions when the selected snapshot is not ready", async () => {
    const user = userEvent.setup();
    mockGetLexiconOpsSnapshot.mockImplementation(async (snapshotName: string) => {
      if (snapshotName === "words-raw-20260310") {
        return {
          ...detail,
          snapshot: "words-raw-20260310",
          snapshot_path: "/data/lexicon/snapshots/words-raw-20260310",
          snapshot_id: "lexicon-20260310-wordnet-wordfreq",
          has_enrichments: false,
          has_compiled_export: false,
          has_selection_decisions: false,
          workflow_stage: "base_artifacts",
          recommended_action: "run_compile_export",
          preferred_review_artifact_path: null,
          preferred_import_artifact_path: null,
          artifacts: [
            {
              file_name: "lexemes.jsonl",
              exists: true,
              row_count: 80,
              size_bytes: 3200,
              modified_at: "2026-03-10T07:35:00Z",
              read_error: null,
            },
          ],
        };
      }
      return detail;
    });

    render(<LexiconOpsPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-ops-snapshot-words-raw-20260310")).toBeInTheDocument());
    await user.click(screen.getByTestId("lexicon-ops-snapshot-words-raw-20260310"));

    await waitFor(() =>
      expect(screen.getByTestId("lexicon-ops-action-reasons")).toHaveTextContent("Run compile-export first"),
    );

    expect(screen.getByTestId("lexicon-ops-open-jsonl-review")).toBeDisabled();
    expect(screen.getByTestId("lexicon-ops-open-compiled-review")).toBeDisabled();
    expect(screen.getByTestId("lexicon-ops-open-import-db")).toBeDisabled();
    expect(screen.getByTestId("lexicon-ops-open-db-inspector")).not.toBeDisabled();

    await user.click(screen.getByTestId("lexicon-ops-open-jsonl-review"));
    await user.click(screen.getByTestId("lexicon-ops-open-compiled-review"));
    await user.click(screen.getByTestId("lexicon-ops-open-import-db"));

    expect(push).not.toHaveBeenCalledWith(expect.stringContaining("/lexicon/jsonl-review"));
    expect(push).not.toHaveBeenCalledWith(expect.stringContaining("/lexicon/compiled-review"));
    expect(push).not.toHaveBeenCalledWith(expect.stringContaining("/lexicon/import-db"));
  });
});
