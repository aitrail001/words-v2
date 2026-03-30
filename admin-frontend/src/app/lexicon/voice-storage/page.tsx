"use client";

import { useCallback, useEffect, useState } from "react";

import { VoiceStoragePanel } from "@/app/lexicon/voice/voice-storage-panel";
import { LexiconSectionNav } from "@/components/lexicon/section-nav";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { getLexiconVoiceStoragePolicies, type LexiconVoiceStoragePolicy } from "@/lib/lexicon-ops-client";

function policyKindBadgeLabel(policy: LexiconVoiceStoragePolicy): string {
  return policy.primary_storage_kind === "local" ? "local" : "remote";
}

export default function LexiconVoiceStoragePage() {
  const [editingPolicyId, setEditingPolicyId] = useState("");
  const [storagePolicies, setStoragePolicies] = useState<LexiconVoiceStoragePolicy[]>([]);
  const [storagePoliciesLoading, setStoragePoliciesLoading] = useState(false);
  const [storagePoliciesError, setStoragePoliciesError] = useState<string | null>(null);

  const loadStoragePolicies = useCallback(async () => {
    setStoragePoliciesLoading(true);
    try {
      const result = await getLexiconVoiceStoragePolicies(undefined);
      setStoragePolicies(result);
      setEditingPolicyId((current) => (result.some((policy) => policy.id === current) ? current : ""));
      setStoragePoliciesError(null);
    } catch (error) {
      setStoragePolicies([]);
      setEditingPolicyId("");
      setStoragePoliciesError(error instanceof Error ? error.message : "Failed to load storage policies.");
    } finally {
      setStoragePoliciesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/voice-storage");
    }
  }, []);

  useEffect(() => {
    void loadStoragePolicies();
  }, [loadStoragePolicies]);

  function editPolicy(policyId: string): void {
    setEditingPolicyId(policyId);
    if (typeof document !== "undefined") {
      const panel = document.getElementById("lexicon-voice-panel");
      if (panel && typeof panel.scrollIntoView === "function") {
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  const selectedPolicy = storagePolicies.find((policy) => policy.id === editingPolicyId) ?? null;

  return (
    <div className="space-y-6" data-testid="lexicon-voice-page">
      <section className="rounded-lg border border-slate-200 bg-slate-50 p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Voice admin</p>
        <h3 className="mt-1 text-2xl font-semibold text-slate-950">Lexicon Voice Storage</h3>
        <p className="mt-1 text-sm text-slate-600">
          Manage the live DB storage-policy roots that voice assets resolve against at runtime.
        </p>
        <div className="mt-4">
          <LexiconSectionNav
            testId="lexicon-voice-section-nav"
            items={[
              { label: "Storage", href: "/lexicon/voice-storage", active: true },
              { label: "Voice Runs", href: "/lexicon/voice-runs" },
              { label: "Voice DB Import", href: "/lexicon/voice-import" },
            ]}
          />
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm" data-testid="lexicon-voice-current-policies">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Current DB storage policies</p>
        {storagePoliciesError ? <p className="mt-3 text-sm text-red-600">{storagePoliciesError}</p> : null}
        <p className="mt-1 text-sm text-slate-600">
          These are the live DB storage policies used by voice assets. Voice import updates asset relative paths and voice metadata only; playback and resolved targets are derived from the current DB policy shown here.
        </p>
        {storagePoliciesLoading ? <p className="mt-3 text-sm text-slate-500">Loading storage policies...</p> : null}
        {storagePolicies.length ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {storagePolicies.map((policy) => (
              <div key={policy.id} className="rounded border border-slate-200 bg-slate-50 p-3 text-sm">
                <div data-testid={`lexicon-voice-policy-${policy.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-slate-900">{policy.policy_key}</p>
                      <p className="mt-1 text-slate-700">scope: {policy.content_scope}</p>
                    </div>
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

      {selectedPolicy ? (
        <VoiceStoragePanel
          testIdPrefix="lexicon-voice"
          selectedPolicy={selectedPolicy}
          onPolicyApplied={loadStoragePolicies}
        />
      ) : null}
    </div>
  );
}
