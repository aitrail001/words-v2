"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  LexiconJsonlReviewItem,
  LexiconJsonlReviewMaterializeResult,
  LexiconJsonlReviewSession,
  loadLexiconJsonlReviewSession,
  materializeLexiconJsonlReviewOutputs,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function LexiconJsonlReviewPage() {
  const [artifactPath, setArtifactPath] = useState("");
  const [decisionsPath, setDecisionsPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [session, setSession] = useState<LexiconJsonlReviewSession | null>(null);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [materializeResult, setMaterializeResult] = useState<LexiconJsonlReviewMaterializeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/jsonl-review");
    }
  }, []);

  const filteredItems = useMemo(() => {
    const items = session?.items ?? [];
    const normalizedSearch = search.trim().toLowerCase();
    return items.filter((item) => {
      if (statusFilter !== "all" && item.review_status !== statusFilter) return false;
      if (!normalizedSearch) return true;
      return [item.entry_id, item.display_text, item.normalized_form ?? ""].some((value) =>
        value.toLowerCase().includes(normalizedSearch),
      );
    });
  }, [search, session?.items, statusFilter]);

  const selectedItem = useMemo(
    () => filteredItems.find((item) => item.entry_id === selectedItemId) ?? filteredItems[0] ?? null,
    [filteredItems, selectedItemId],
  );

  useEffect(() => {
    setSelectedItemId(selectedItem?.entry_id ?? "");
  }, [selectedItem?.entry_id]);

  useEffect(() => {
    setDecisionReason(selectedItem?.decision_reason ?? "");
  }, [selectedItem?.decision_reason, selectedItem?.entry_id]);

  const loadSession = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    setMaterializeResult(null);
    try {
      const nextSession = await loadLexiconJsonlReviewSession({
        artifactPath,
        decisionsPath: decisionsPath || undefined,
        outputDir: outputDir || undefined,
      });
      setSession(nextSession);
      setDecisionsPath(nextSession.decisions_path);
      setOutputDir(nextSession.output_dir ?? outputDir);
      setMessage(`Loaded ${nextSession.artifact_filename}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load artifact.");
    } finally {
      setLoading(false);
    }
  };

  const replaceItem = (updated: LexiconJsonlReviewItem) => {
    setSession((current) => {
      if (!current) return current;
      const items = current.items.map((item) => (item.entry_id === updated.entry_id ? updated : item));
      const approvedCount = items.filter((item) => item.review_status === "approved").length;
      const rejectedCount = items.filter((item) => item.review_status === "rejected").length;
      return {
        ...current,
        items,
        approved_count: approvedCount,
        rejected_count: rejectedCount,
        pending_count: items.length - approvedCount - rejectedCount,
      };
    });
  };

  const saveDecision = async (reviewStatus: "pending" | "approved" | "rejected") => {
    if (!selectedItem || !session) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateLexiconJsonlReviewItem(selectedItem.entry_id, {
        artifactPath: session.artifact_path,
        decisionsPath: decisionsPath || session.decisions_path,
        reviewStatus,
        decisionReason: decisionReason || null,
      });
      replaceItem(updated);
      setMessage(`Saved ${updated.entry_id} as ${updated.review_status}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save decision.");
    } finally {
      setSaving(false);
    }
  };

  const materialize = async () => {
    if (!session) return;
    setSaving(true);
    setMessage(null);
    try {
      const result = await materializeLexiconJsonlReviewOutputs({
        artifactPath: session.artifact_path,
        decisionsPath: decisionsPath || session.decisions_path,
        outputDir: outputDir || undefined,
      });
      setMaterializeResult(result);
      setMessage("Materialized outputs.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to materialize outputs.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="lexicon-jsonl-review-page">
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="text-2xl font-semibold text-gray-900" data-testid="lexicon-jsonl-review-title">
          JSONL-Only Lexicon Review
        </h3>
        <p className="mt-1 text-sm text-gray-600">
          Review compiled artifacts directly from JSONL and persist decisions as a sidecar without using review DB tables.
        </p>

        <form onSubmit={loadSession} className="mt-6 grid gap-3 md:grid-cols-1">
          <label className="grid gap-1 text-sm text-gray-700">
            <span>Artifact path</span>
            <input
              aria-label="Artifact path"
              value={artifactPath}
              onChange={(event) => setArtifactPath(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span>Decisions path</span>
            <input
              aria-label="Decisions path"
              value={decisionsPath}
              onChange={(event) => setDecisionsPath(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span>Output directory</span>
            <input
              aria-label="Output directory"
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2"
            />
          </label>
          <div className="flex gap-3">
            <button type="submit" disabled={!artifactPath || loading} className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {loading ? "Loading..." : "Load Artifact"}
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void materialize()} className="rounded-md border border-blue-300 px-4 py-2 text-sm text-blue-700 disabled:opacity-50">
              Materialize Outputs
            </button>
          </div>
        </form>
        {message ? <p className="mt-3 text-sm text-gray-700">{message}</p> : null}
      </section>

      {session ? (
        <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="mb-3 text-sm text-gray-500">
              pending {session.pending_count} · approved {session.approved_count} · rejected {session.rejected_count}
            </div>
            <div className="grid gap-2">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search entry id or display text"
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as "all" | "pending" | "approved" | "rejected")}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            <div className="mt-4 space-y-2">
              {filteredItems.map((item) => (
                <button
                  key={item.entry_id}
                  type="button"
                  onClick={() => setSelectedItemId(item.entry_id)}
                  className={`w-full rounded-lg border p-3 text-left ${item.entry_id === selectedItem?.entry_id ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
                >
                  <p className="font-medium text-gray-900">{item.display_text}</p>
                  <p className="text-xs text-gray-500">{item.entry_type} · {item.review_status}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            {selectedItem ? (
              <div className="space-y-4">
                <div>
                  <h4 className="text-xl font-semibold text-gray-900">{selectedItem.display_text}</h4>
                  <p className="text-sm text-gray-500">
                    {selectedItem.entry_id} · {selectedItem.entry_type} · reviewed {formatDateTime(selectedItem.reviewed_at)}
                  </p>
                </div>
                <textarea
                  data-testid="jsonl-review-decision-reason"
                  value={decisionReason}
                  onChange={(event) => setDecisionReason(event.target.value)}
                  className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
                <div className="flex gap-3">
                  <button type="button" data-testid="jsonl-review-approve-button" disabled={saving} onClick={() => void saveDecision("approved")} className="rounded-md border border-green-300 px-4 py-2 text-sm text-green-700 disabled:opacity-50">
                    Approve
                  </button>
                  <button type="button" data-testid="jsonl-review-reject-button" disabled={saving} onClick={() => void saveDecision("rejected")} className="rounded-md border border-red-300 px-4 py-2 text-sm text-red-700 disabled:opacity-50">
                    Reject
                  </button>
                  <button type="button" data-testid="jsonl-review-reopen-button" disabled={saving} onClick={() => void saveDecision("pending")} className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 disabled:opacity-50">
                    Reopen
                  </button>
                </div>
                <pre className="overflow-auto rounded-lg bg-gray-950 p-4 text-xs text-gray-100">
                  {JSON.stringify(selectedItem.compiled_payload, null, 2)}
                </pre>
              </div>
            ) : (
              <p className="text-sm text-gray-500">No items match the current filter.</p>
            )}
          </div>
        </section>
      ) : null}

      {materializeResult ? (
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm text-sm text-gray-700">
          <p>{materializeResult.approved_output_path}</p>
          <p>{materializeResult.rejected_output_path}</p>
          <p>{materializeResult.regenerate_output_path}</p>
        </section>
      ) : null}
    </div>
  );
}
