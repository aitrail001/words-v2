"use client";

import { useEffect, useState } from "react";
import { rewriteLexiconVoiceStorage, type LexiconVoiceStoragePolicy, type RewriteLexiconVoiceStorageResponse } from "@/lib/lexicon-ops-client";

type VoiceStoragePanelProps = {
  testIdPrefix: string;
  selectedPolicy: LexiconVoiceStoragePolicy | null;
};

export function VoiceStoragePanel({ testIdPrefix, selectedPolicy }: VoiceStoragePanelProps) {
  const [voiceStorageKind, setVoiceStorageKind] = useState("local");
  const [voiceStorageBase, setVoiceStorageBase] = useState("");
  const [fallbackVoiceStorageKind, setFallbackVoiceStorageKind] = useState("");
  const [fallbackVoiceStorageBase, setFallbackVoiceStorageBase] = useState("");
  const [voiceStorageLoading, setVoiceStorageLoading] = useState(false);
  const [voiceStorageMessage, setVoiceStorageMessage] = useState<string | null>(null);
  const [voiceStorageResult, setVoiceStorageResult] = useState<RewriteLexiconVoiceStorageResponse | null>(null);

  useEffect(() => {
    if (!selectedPolicy) {
      return;
    }
    setVoiceStorageKind(selectedPolicy.primary_storage_kind);
    setVoiceStorageBase(selectedPolicy.primary_storage_base);
    setFallbackVoiceStorageKind(selectedPolicy.fallback_storage_kind ?? "");
    setFallbackVoiceStorageBase(selectedPolicy.fallback_storage_base ?? "");
  }, [selectedPolicy]);

  const runVoiceStorageRewrite = async (dryRun: boolean) => {
    if (!selectedPolicy || !voiceStorageKind || !voiceStorageBase) return;
    setVoiceStorageLoading(true);
    setVoiceStorageMessage(null);
    try {
      const result = await rewriteLexiconVoiceStorage({
        policy_ids: [selectedPolicy.id],
        storage_kind: voiceStorageKind,
        storage_base: voiceStorageBase,
        fallback_storage_kind: fallbackVoiceStorageKind || undefined,
        fallback_storage_base: fallbackVoiceStorageBase || undefined,
        dry_run: dryRun,
      });
      setVoiceStorageResult(result);
      setVoiceStorageMessage(
        result.dry_run
          ? `would update ${result.matched_count}`
          : `updated ${result.updated_count} of ${result.matched_count}`,
      );
    } catch (error) {
      setVoiceStorageResult(null);
      setVoiceStorageMessage(error instanceof Error ? error.message : "Voice storage rewrite failed.");
    } finally {
      setVoiceStorageLoading(false);
    }
  };

  return (
    <section id={`${testIdPrefix}-panel`} className="rounded border border-gray-200 bg-white p-4" data-testid={`${testIdPrefix}-panel`}>
      <div>
        <h5 className="text-base font-semibold text-gray-900">Policy Editor</h5>
        <p className="text-sm text-gray-500">Edit the selected DB storage policy separately from voice import. Voice import updates asset relative paths; policy roots set how those paths resolve at runtime.</p>
      </div>
      <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
        <p className="text-slate-700">
          <span className="font-medium text-slate-900">Editing policy</span>
          {selectedPolicy ? ` ${selectedPolicy.policy_key} · Scope: ${selectedPolicy.content_scope}` : " No policy selected"}
        </p>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <label className="grid gap-1 text-sm text-gray-700">
          <span className="font-medium">Storage kind</span>
          <select
            data-testid={`${testIdPrefix}-storage-kind`}
            value={voiceStorageKind}
            onChange={(event) => setVoiceStorageKind(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="local">local</option>
            <option value="s3">s3</option>
            <option value="gcs">gcs</option>
            <option value="http">http</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm text-gray-700">
          <span className="font-medium">Storage base</span>
          <input
            data-testid={`${testIdPrefix}-storage-base`}
            value={voiceStorageBase}
            onChange={(event) => setVoiceStorageBase(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="https://cdn.example.com/voice"
          />
        </label>
        <label className="grid gap-1 text-sm text-gray-700">
          <span className="font-medium">Fallback storage kind</span>
          <select
            data-testid={`${testIdPrefix}-fallback-storage-kind`}
            value={fallbackVoiceStorageKind}
            onChange={(event) => setFallbackVoiceStorageKind(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">none</option>
            <option value="local">local</option>
            <option value="s3">s3</option>
            <option value="gcs">gcs</option>
            <option value="http">http</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm text-gray-700">
          <span className="font-medium">Fallback storage base</span>
          <input
            data-testid={`${testIdPrefix}-fallback-storage-base`}
            value={fallbackVoiceStorageBase}
            onChange={(event) => setFallbackVoiceStorageBase(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="optional"
          />
        </label>
      </div>
      <div className="mt-4 flex justify-end">
        <div className="flex gap-3">
          <button
            type="button"
            data-testid={`${testIdPrefix}-dry-run-button`}
            disabled={!selectedPolicy || !voiceStorageKind || !voiceStorageBase || voiceStorageLoading}
            onClick={() => void runVoiceStorageRewrite(true)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            {voiceStorageLoading ? "Working..." : "Dry Run"}
          </button>
          <button
            type="button"
            data-testid={`${testIdPrefix}-apply-button`}
            disabled={!selectedPolicy || !voiceStorageKind || !voiceStorageBase || voiceStorageLoading}
            onClick={() => void runVoiceStorageRewrite(false)}
            className="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Apply
          </button>
        </div>
      </div>
      {voiceStorageMessage ? <p className="mt-3 text-sm text-gray-700">{voiceStorageMessage}</p> : null}
      {voiceStorageResult ? (
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-5" data-testid={`${testIdPrefix}-result`}>
          <div className="rounded border border-gray-200 p-3">
            <p className="text-gray-500">Matched assets</p>
            <p className="font-medium">{voiceStorageResult.matched_count}</p>
          </div>
          <div className="rounded border border-gray-200 p-3">
            <p className="text-gray-500">Updated assets</p>
            <p className="font-medium">{voiceStorageResult.updated_count}</p>
          </div>
          <div className="rounded border border-gray-200 p-3">
            <p className="text-gray-500">Storage kind</p>
            <p className="font-medium">{voiceStorageResult.storage_kind}</p>
          </div>
          <div className="rounded border border-gray-200 p-3">
            <p className="text-gray-500">Storage base</p>
            <p className="font-medium break-all">{voiceStorageResult.storage_base}</p>
          </div>
          <div className="rounded border border-gray-200 p-3">
            <p className="text-gray-500">Fallback</p>
            <p className="font-medium break-all">
              {voiceStorageResult.fallback_storage_kind && voiceStorageResult.fallback_storage_base
                ? `${voiceStorageResult.fallback_storage_kind} | ${voiceStorageResult.fallback_storage_base}`
                : "cleared"}
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
