"use client";

type ReviewerSummaryCardProps = {
  summary: {
    senseCount: number;
    formVariantCount: number;
    confusableCount: number;
    provenanceSources: string[];
    primaryDefinition: string | null;
    primaryExample: string | null;
    phraseKind?: string | null;
  };
  warningLabels?: string[];
  title?: string;
};

export function ReviewerSummaryCard({
  summary,
  warningLabels = [],
  title = "Reviewer summary",
}: ReviewerSummaryCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{title}</p>
        {warningLabels.map((warning) => (
          <span key={warning} className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
            {warning}
          </span>
        ))}
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Senses</p>
          <p className="mt-1 text-lg font-semibold text-slate-900">{summary.senseCount}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Form variants</p>
          <p className="mt-1 text-lg font-semibold text-slate-900">{summary.formVariantCount}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Confusables</p>
          <p className="mt-1 text-lg font-semibold text-slate-900">{summary.confusableCount}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Phrase kind</p>
          <p className="mt-1 text-lg font-semibold text-slate-900">{summary.phraseKind ?? "—"}</p>
        </div>
      </div>
      <div className="mt-3 space-y-2 text-sm text-slate-600">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Primary definition</p>
          <p className="mt-1 text-slate-900">{summary.primaryDefinition ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Primary example</p>
          <p className="mt-1 text-slate-900">{summary.primaryExample ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Provenance</p>
          <div className="mt-1 flex flex-wrap gap-2">
            {summary.provenanceSources.length ? summary.provenanceSources.map((source) => (
              <span key={source} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700">
                {source}
              </span>
            )) : (
              <span className="text-slate-900">—</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
