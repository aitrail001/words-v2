"use client";

import { useEffect, useState } from "react";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { VoiceStoragePanel } from "@/app/lexicon/voice/voice-storage-panel";
import { getLexiconVoiceRunDetail, getLexiconVoiceRuns, getLexiconVoiceStoragePolicies, type LexiconVoiceRunDetail, type LexiconVoiceRunSummary, type LexiconVoiceStoragePolicy } from "@/lib/lexicon-ops-client";

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

function policyKindBadgeLabel(policy: LexiconVoiceStoragePolicy): string {
  return policy.primary_storage_kind === "local" ? "local" : "remote";
}

export default function LexiconVoicePage() {
  const RUNS_PER_PAGE = 2;
  const [selectedPolicyId, setSelectedPolicyId] = useState("");
  const [runs, setRuns] = useState<LexiconVoiceRunSummary[]>([]);
  const [runPage, setRunPage] = useState(0);
  const [selectedRunName, setSelectedRunName] = useState("");
  const [selectedRunDetail, setSelectedRunDetail] = useState<LexiconVoiceRunDetail | null>(null);
  const [storagePolicies, setStoragePolicies] = useState<LexiconVoiceStoragePolicy[]>([]);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [storagePoliciesError, setStoragePoliciesError] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/voice");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getLexiconVoiceStoragePolicies(undefined);
        if (cancelled) return;
        setStoragePolicies(result);
        setSelectedPolicyId((current) => (result.some((policy) => policy.id === current) ? current : (result[0]?.id ?? "")));
        setStoragePoliciesError(null);
      } catch (error) {
        if (cancelled) return;
        setStoragePolicies([]);
        setSelectedPolicyId("");
        setStoragePoliciesError(error instanceof Error ? error.message : "Failed to load storage policies.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getLexiconVoiceRuns();
        if (cancelled) return;
        setRuns(result);
        setRunPage((current) => {
          const maxPage = Math.max(0, Math.ceil(result.length / RUNS_PER_PAGE) - 1);
          return Math.min(current, maxPage);
        });
        setRunsError(null);
        if (result.length && !selectedRunName) {
          setSelectedRunName(result[0].run_name);
        }
      } catch (error) {
        if (cancelled) return;
        setRuns([]);
        setRunsError(error instanceof Error ? error.message : "Failed to load voice runs.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedRunName]);

  useEffect(() => {
    if (!selectedRunName) {
      setSelectedRunDetail(null);
      setRunDetailError(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const result = await getLexiconVoiceRunDetail(selectedRunName);
        if (cancelled) return;
        setSelectedRunDetail(result);
        setRunDetailError(null);
      } catch (error) {
        if (cancelled) return;
        setSelectedRunDetail(null);
        setRunDetailError(error instanceof Error ? error.message : "Failed to load voice run detail.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedRunName]);

  function formatDateTime(value: string | null | undefined): string {
    if (!value) {
      return "—";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  }

  async function downloadArtifact(name: string, url: string): Promise<void> {
    const token = readAccessToken();
    if (!token) {
      redirectToLogin("/lexicon/voice");
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

  function editPolicy(policyId: string): void {
    setSelectedPolicyId(policyId);
    if (typeof document !== "undefined") {
      const panel = document.getElementById("lexicon-voice-panel");
      if (panel && typeof panel.scrollIntoView === "function") {
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  const selectedPolicy = storagePolicies.find((policy) => policy.id === selectedPolicyId) ?? null;
  const totalRunPages = Math.max(1, Math.ceil(runs.length / RUNS_PER_PAGE));
  const visibleRuns = runs.slice(runPage * RUNS_PER_PAGE, (runPage + 1) * RUNS_PER_PAGE);

  return (
    <div className="space-y-6" data-testid="lexicon-voice-page">
      <section className="rounded-lg border border-slate-200 bg-slate-50 p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Voice admin</p>
        <h3 className="mt-1 text-2xl font-semibold text-slate-950">Lexicon Voice</h3>
        <p className="mt-1 text-sm text-slate-600">
          Manage voice asset storage rewrites and future voice-run operations without crowding the main snapshot workflow page.
        </p>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" data-testid="lexicon-voice-current-policies">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Current DB storage policies</p>
        {storagePoliciesError ? <p className="mt-3 text-sm text-red-600">{storagePoliciesError}</p> : null}
        <p className="mt-1 text-sm text-slate-600">These are the live DB storage policies used by voice assets. Voice runs are shown separately below.</p>
        {storagePolicies.length ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {storagePolicies.map((policy) => (
              <div key={policy.id} className="rounded border border-slate-200 bg-slate-50 p-3 text-sm">
                <div data-testid={`lexicon-voice-policy-${policy.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <label className="flex items-start gap-3">
                      <input
                        type="radio"
                        name="voice-storage-policy"
                        checked={selectedPolicyId === policy.id}
                        onChange={() => setSelectedPolicyId(policy.id)}
                        className="mt-1 h-4 w-4 rounded border-slate-300"
                      />
                      <div>
                        <p className="font-medium text-slate-900">{policy.policy_key}</p>
                        <p className="mt-1 text-slate-700">scope: {policy.content_scope}</p>
                      </div>
                    </label>
                    <button
                      type="button"
                      onClick={() => editPolicy(policy.id)}
                      className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700"
                    >
                      Edit policy
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] font-medium text-white">
                      {policyKindBadgeLabel(policy)}
                    </span>
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                      {policy.primary_storage_kind}
                    </span>
                    {policy.fallback_storage_kind ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                        fallback-enabled
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-3 break-all text-slate-700">
                    primary: {policy.primary_storage_kind} | {policy.primary_storage_base}
                  </p>
                  <p className="mt-1 break-all text-slate-500">
                    fallback: {policy.fallback_storage_kind && policy.fallback_storage_base ? `${policy.fallback_storage_kind} | ${policy.fallback_storage_base}` : "—"}
                  </p>
                  <p className="mt-1 text-slate-500">assets: {policy.asset_count}</p>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <VoiceStoragePanel
        testIdPrefix="lexicon-voice"
        selectedPolicy={selectedPolicy}
      />

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" data-testid="lexicon-voice-runs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Recent voice runs</p>
            <p className="mt-1 text-sm text-slate-600">Paged horizontal cards keep run history compact while preserving quick access to details.</p>
          </div>
          <div className="flex min-w-[18rem] items-center justify-end gap-2" data-testid="lexicon-voice-run-pagination">
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
        {runs.length ? (
          <div className="mt-4 grid gap-4 xl:grid-cols-2" data-testid="lexicon-voice-run-page">
            {visibleRuns.map((run) => (
              <button
                type="button"
                key={run.run_name}
                data-testid={`lexicon-voice-run-${run.run_name}`}
                onClick={() => setSelectedRunName(run.run_name)}
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
              </button>
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
                      <li key={locale}>
                        {locale}: {count}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">No locale rows.</p>
                )}
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Voice role counts</p>
                {Object.keys(selectedRunDetail.voice_role_counts).length ? (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {Object.entries(selectedRunDetail.voice_role_counts).map(([voiceRole, count]) => (
                      <li key={voiceRole}>
                        {voiceRole}: {count}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">No voice-role rows.</p>
                )}
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Content scope counts</p>
                {Object.keys(selectedRunDetail.content_scope_counts).length ? (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {Object.entries(selectedRunDetail.content_scope_counts).map(([contentScope, count]) => (
                      <li key={contentScope}>
                        {contentScope}: {count}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">No content-scope rows.</p>
                )}
              </div>
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-slate-900">Run artifacts</p>
                  <p className="mt-1 text-sm text-slate-500">Download the plan, manifest, or error ledgers from this CLI run.</p>
                </div>
              </div>
              {selectedRunDetail.source_references.length ? (
                <p className="mt-2 text-sm text-slate-600">
                  Source references recorded in this run: {selectedRunDetail.source_references.join(", ")}
                </p>
              ) : (
                <p className="mt-2 text-sm text-slate-500">No source reference found in this run ledger.</p>
              )}
              <div className="mt-3 flex flex-wrap gap-3 text-sm">
                {Object.entries(selectedRunDetail.artifacts).map(([artifactName, artifactUrl]) => (
                  <button
                    type="button"
                    key={artifactName}
                    data-testid={`lexicon-voice-artifact-${artifactLabel(artifactName, artifactUrl)}`}
                    onClick={() => void downloadArtifact(artifactName, artifactUrl)}
                    className="rounded border border-slate-300 bg-white px-3 py-2 text-slate-700 hover:bg-slate-100"
                  >
                    {artifactLabel(artifactName, artifactUrl)}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Latest manifest rows</p>
                <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-xs text-slate-700">
                  {JSON.stringify(selectedRunDetail.latest_manifest_rows, null, 2)}
                </pre>
              </div>
              <div className="rounded border border-slate-200 bg-slate-50 p-3">
                <p className="font-medium text-slate-900">Latest error rows</p>
                <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-xs text-slate-700">
                  {JSON.stringify(selectedRunDetail.latest_error_rows, null, 2)}
                </pre>
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
