"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { LexiconSectionNav } from "@/components/lexicon/section-nav";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { getLexiconVoiceRunDetail, getLexiconVoiceRuns, type LexiconVoiceRunDetail, type LexiconVoiceRunSummary } from "@/lib/lexicon-ops-client";

function artifactLabel(key: string, url: string): string {
  const fileName = url.split("/").filter(Boolean).pop();
  return fileName || key;
}

function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "application/x-ndjson" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function LexiconVoiceRunsPage() {
  const router = useRouter();
  const RUNS_PER_PAGE = 10;
  const [runs, setRuns] = useState<LexiconVoiceRunSummary[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [runPage, setRunPage] = useState(0);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRunName, setSelectedRunName] = useState("");
  const [selectedRunDetail, setSelectedRunDetail] = useState<LexiconVoiceRunDetail | null>(null);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  const loadRuns = useCallback(async (activeRunName: string) => {
    setRunsLoading(true);
    try {
      const result = await getLexiconVoiceRuns({
        q: searchQuery || undefined,
        limit: RUNS_PER_PAGE,
        offset: runPage * RUNS_PER_PAGE,
      });
      setRuns(result.items);
      setRunTotal(result.total);
      setRunsError(null);
      if (!result.items.length) {
        setSelectedRunName("");
        setSelectedRunDetail(null);
        return;
      }
      if (activeRunName && result.items.some((run) => run.run_name === activeRunName)) {
        setSelectedRunName(activeRunName);
        return;
      }
      setSelectedRunName(result.items[0].run_name);
    } catch (error) {
      setRuns([]);
      setRunTotal(0);
      setRunsError(error instanceof Error ? error.message : "Failed to load voice runs.");
    } finally {
      setRunsLoading(false);
    }
  }, [runPage, searchQuery]);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/voice-runs");
    }
  }, []);

  useEffect(() => {
    void loadRuns(selectedRunName);
  }, [loadRuns, selectedRunName]);

  useEffect(() => {
    if (!selectedRunName) {
      setSelectedRunDetail(null);
      setRunDetailError(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      setRunDetailLoading(true);
      try {
        const result = await getLexiconVoiceRunDetail(selectedRunName);
        if (cancelled) return;
        setSelectedRunDetail(result);
        setRunDetailError(null);
      } catch (error) {
        if (cancelled) return;
        setSelectedRunDetail(null);
        setRunDetailError(error instanceof Error ? error.message : "Failed to load voice run detail.");
      } finally {
        if (!cancelled) setRunDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedRunName]);

  function formatDateTime(value: string | null | undefined): string {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  }

  async function downloadArtifact(name: string, url: string): Promise<void> {
    const token = readAccessToken();
    if (!token) {
      redirectToLogin("/lexicon/voice-runs");
      return;
    }
    try {
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error(`Artifact download failed: ${response.status}`);
      }
      downloadTextFile(artifactLabel(name, url), await response.text());
      setArtifactError(null);
    } catch (error) {
      setArtifactError(error instanceof Error ? error.message : "Failed to download artifact.");
    }
  }

  function openVoiceImport(runPath: string): void {
    const params = new URLSearchParams({
      inputPath: `${runPath.replace(/\/$/, "")}/voice_manifest.jsonl`,
      language: "en",
    });
    router.push(`/lexicon/voice-import?${params.toString()}`);
  }

  const totalRunPages = Math.max(1, Math.ceil(runTotal / RUNS_PER_PAGE));

  return (
    <div className="space-y-6" data-testid="lexicon-voice-page">
      <section className="rounded-lg border border-slate-200 bg-slate-50 p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Voice admin</p>
        <h3 className="mt-1 text-2xl font-semibold text-slate-950">Lexicon Voice Runs</h3>
        <p className="mt-1 text-sm text-slate-600">
          Inspect generated voice-run outputs and launch the DB import flow from a specific manifest.
        </p>
        <div className="mt-4">
          <LexiconSectionNav
            testId="lexicon-voice-section-nav"
            items={[
              { label: "Storage", href: "/lexicon/voice-storage" },
              { label: "Voice Runs", href: "/lexicon/voice-runs", active: true },
              { label: "Voice DB Import", href: "/lexicon/voice-import" },
            ]}
          />
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" data-testid="lexicon-voice-runs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Recent voice runs</p>
            <p className="mt-1 text-sm text-slate-600">Paged horizontal cards keep run history compact while preserving quick access to details.</p>
          </div>
          <div className="flex min-w-[22rem] items-center justify-end gap-2">
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Search voice runs"
              data-testid="lexicon-voice-runs-search"
              className="min-w-0 flex-1 rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
            />
            <button
              type="button"
              onClick={() => {
                setSearchQuery(searchDraft.trim());
                setRunPage(0);
              }}
              className="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
            >
              Apply
            </button>
          </div>
          <div className="flex min-w-[18rem] items-center justify-end gap-2" data-testid="lexicon-voice-run-pagination">
            <button
              type="button"
              data-testid="lexicon-voice-runs-refresh"
              onClick={() => void loadRuns(selectedRunName)}
              disabled={runsLoading}
              className="min-w-[5.5rem] rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
            >
              {runsLoading ? "Refreshing..." : "Refresh"}
            </button>
            <button
              type="button"
              onClick={() => setRunPage((current) => Math.max(0, current - 1))}
              disabled={runPage === 0}
              className="min-w-[5.5rem] rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
            >
              Previous
            </button>
            <p className="min-w-[5rem] text-center text-sm text-slate-600">
              Page {runPage + 1} of {totalRunPages}
            </p>
            <button
              type="button"
              onClick={() => setRunPage((current) => Math.min(totalRunPages - 1, current + 1))}
              disabled={runPage >= totalRunPages - 1}
              className="min-w-[5.5rem] rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
        {runsError ? <p className="mt-3 text-sm text-red-600">{runsError}</p> : null}
        {runsLoading ? <p className="mt-3 text-sm text-slate-500">Loading voice runs...</p> : null}
        {runs.length ? (
          <div className="mt-4 grid gap-4 xl:grid-cols-2" data-testid="lexicon-voice-run-page">
            {runs.map((run) => (
              <div
                key={run.run_name}
                className={`w-full rounded border p-3 text-left text-sm ${selectedRunName === run.run_name ? "border-emerald-400 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-900">{run.run_name}</p>
                    <p className="text-slate-500">{formatDateTime(run.updated_at)}</p>
                  </div>
                  <p className="break-all text-xs text-slate-500">{run.run_path}</p>
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-4">
                  <div className="rounded border border-slate-200 bg-white p-2">planned: {run.planned_count}</div>
                  <div className="rounded border border-slate-200 bg-white p-2">generated: {run.generated_count}</div>
                  <div className="rounded border border-slate-200 bg-white p-2">existing: {run.existing_count}</div>
                  <div className="rounded border border-slate-200 bg-white p-2">failed: {run.failed_count}</div>
                </div>
                <div className="mt-3 flex flex-wrap gap-3">
                  <button
                    type="button"
                    data-testid={`lexicon-voice-run-${run.run_name}`}
                    onClick={() => setSelectedRunName(run.run_name)}
                    className="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                  >
                    View details
                  </button>
                  <button
                    type="button"
                    data-testid={`lexicon-voice-run-import-${run.run_name}`}
                    onClick={() => openVoiceImport(run.run_path)}
                    className="rounded border border-slate-900 bg-slate-900 px-3 py-2 text-sm text-white hover:bg-slate-800"
                  >
                    Import voice assets
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No voice runs found.</p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" data-testid="lexicon-voice-run-detail">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Run detail</p>
        {runDetailError ? <p className="mt-3 text-sm text-red-600">{runDetailError}</p> : null}
        {artifactError ? <p className="mt-3 text-sm text-red-600">{artifactError}</p> : null}
        {runDetailLoading ? <p className="mt-3 text-sm text-slate-500">Loading run detail...</p> : null}
        {selectedRunDetail ? (
          <div className="mt-4 space-y-4">
            <div>
              <p className="font-medium text-slate-900">{selectedRunDetail.run_name}</p>
              <p className="break-all text-sm text-slate-500">{selectedRunDetail.run_path}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Locale counts</p>
                {Object.keys(selectedRunDetail.locale_counts).length ? (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {Object.entries(selectedRunDetail.locale_counts).map(([locale, count]) => (
                      <li key={locale}>{locale}: {count}</li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-slate-500">No locale rows.</p>}
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Voice role counts</p>
                {Object.keys(selectedRunDetail.voice_role_counts).length ? (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {Object.entries(selectedRunDetail.voice_role_counts).map(([voiceRole, count]) => (
                      <li key={voiceRole}>{voiceRole}: {count}</li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-slate-500">No voice role rows.</p>}
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Content scope counts</p>
                {Object.keys(selectedRunDetail.content_scope_counts).length ? (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {Object.entries(selectedRunDetail.content_scope_counts).map(([scope, count]) => (
                      <li key={scope}>{scope}: {count}</li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-slate-500">No scope rows.</p>}
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              {Object.entries(selectedRunDetail.artifacts).map(([name, url]) => (
                <button
                  key={name}
                  type="button"
                  data-testid={`lexicon-voice-artifact-${artifactLabel(name, url)}`}
                  onClick={() => void downloadArtifact(name, url)}
                  className="rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                >
                  {artifactLabel(name, url)}
                </button>
              ))}
              <button
                type="button"
                data-testid="lexicon-voice-run-detail-import"
                onClick={() => openVoiceImport(selectedRunDetail.run_path)}
                className="rounded border border-slate-900 bg-slate-900 px-3 py-2 text-sm text-white hover:bg-slate-800"
              >
                Import voice assets
              </button>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Latest manifest rows</p>
                {selectedRunDetail.latest_manifest_rows.length ? (
                  <pre className="mt-2 overflow-x-auto text-xs text-slate-700">
                    {JSON.stringify(selectedRunDetail.latest_manifest_rows, null, 2)}
                  </pre>
                ) : <p className="mt-2 text-sm text-slate-500">No manifest rows recorded.</p>}
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Latest error rows</p>
                {selectedRunDetail.latest_error_rows.length ? (
                  <pre className="mt-2 overflow-x-auto text-xs text-slate-700">
                    {JSON.stringify(selectedRunDetail.latest_error_rows, null, 2)}
                  </pre>
                ) : <p className="mt-2 text-sm text-slate-500">No error rows recorded.</p>}
              </div>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">Select a run to inspect its latest manifest and error rows.</p>
        )}
      </section>
    </div>
  );
}
