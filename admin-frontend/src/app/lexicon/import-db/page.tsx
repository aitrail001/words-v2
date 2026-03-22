"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  LexiconImportResult,
  dryRunLexiconImport,
  runLexiconImport,
} from "@/lib/lexicon-imports-client";

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

export default function LexiconImportDbPage() {
  const [inputPath, setInputPath] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [language, setLanguage] = useState("en");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<LexiconImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const autoStart = searchParam("autostart") === "1";

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/import-db");
      return;
    }
    setInputPath(searchParam("inputPath"));
    setSourceReference(searchParam("sourceReference"));
    setLanguage(searchParam("language") || "en");
  }, []);

  const canRun = inputPath.trim().length > 0;
  const importSummaryEntries = useMemo(
    () => Object.entries(result?.import_summary ?? {}),
    [result?.import_summary],
  );
  const hasContext =
    Boolean(searchParam("inputPath") || searchParam("sourceReference") || searchParam("language")) ||
    inputPath.trim().length > 0 ||
    sourceReference.trim().length > 0 ||
    language.trim() !== "en";

  const execute = useCallback(async (mode: "dry-run" | "run") => {
    if (!canRun) return;
    setLoading(true);
    setMessage(null);
    try {
      const payload = {
        inputPath,
        sourceType: "lexicon_snapshot",
        sourceReference: sourceReference || undefined,
        language,
      };
      const nextResult = mode === "dry-run"
        ? await dryRunLexiconImport(payload)
        : await runLexiconImport(payload);
      setResult(nextResult);
      setMessage(mode === "dry-run" ? "Import dry-run complete." : "Import completed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Import request failed.");
    } finally {
      setLoading(false);
    }
  }, [canRun, inputPath, language, sourceReference]);

  useEffect(() => {
    if (!autoStart || !inputPath.trim() || loading || result) {
      return;
    }
    void execute("dry-run");
  }, [autoStart, execute, inputPath, loading, result]);

  return (
    <div className="space-y-6" data-testid="lexicon-import-db-page">
      {hasContext ? (
        <section className="rounded-lg border border-gray-200 bg-slate-50 p-4 text-sm text-slate-800" data-testid="lexicon-import-db-context">
          <p className="font-medium">Workflow context</p>
          <p className="mt-1">Input path: {inputPath || "—"}</p>
          <p>Source reference: {sourceReference || "—"}</p>
          <p>Language: {language || "—"}</p>
          <p className="mt-1">Stage: Final DB write</p>
          <p>Next step: Open DB Inspector after import to verify the final state.</p>
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-gray-900">Lexicon Import to Final DB</h3>
            <p className="mt-1 max-w-3xl text-sm text-gray-600">
              Dry-run or execute the final `import-db` write step using an approved compiled artifact.
            </p>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Use approved.jsonl from Compiled Review export or JSONL Review materialize, not the raw words.enriched.jsonl artifact unless you are intentionally bypassing review.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_10rem_auto]">
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Input path</span>
            <input
              data-testid="lexicon-import-db-input-path"
              value={inputPath}
              onChange={(event) => setInputPath(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
              placeholder="data/lexicon/snapshots/.../approved.jsonl"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Source reference</span>
            <input
              value={sourceReference}
              onChange={(event) => setSourceReference(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              placeholder="optional source reference"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Language</span>
            <input
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <div className="flex flex-wrap items-end gap-3">
            <button
              type="button"
              data-testid="lexicon-import-db-dry-run-button"
              onClick={() => void execute("dry-run")}
              disabled={!canRun || loading}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
            >
              {loading ? "Working..." : "Dry Run"}
            </button>
            <button
              type="button"
              data-testid="lexicon-import-db-run-button"
              onClick={() => void execute("run")}
              disabled={!canRun || loading}
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Import
            </button>
          </div>
        </div>

        {message ? <p className="mt-4 text-sm text-gray-700">{message}</p> : null}
      </section>

      {result ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Result</h4>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-rows">
              <p className="text-gray-500">Rows</p>
              <p className="font-medium">{result.row_summary.row_count}</p>
            </div>
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-words">
              <p className="text-gray-500">Words</p>
              <p className="font-medium">{result.row_summary.word_count}</p>
            </div>
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-phrases">
              <p className="text-gray-500">Phrases</p>
              <p className="font-medium">{result.row_summary.phrase_count}</p>
            </div>
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-references">
              <p className="text-gray-500">References</p>
              <p className="font-medium">{result.row_summary.reference_count}</p>
            </div>
          </div>
          {importSummaryEntries.length > 0 ? (
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {importSummaryEntries.map(([key, value]) => (
                <div key={key} className="rounded border border-gray-200 p-3 text-sm">
                  <p className="text-gray-500">{key}</p>
                  <p className="font-medium">{value}</p>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
