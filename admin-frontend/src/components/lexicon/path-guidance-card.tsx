type PathGuidanceCardProps = {
  modeNote: string;
  className?: string;
};

export function PathGuidanceCard({ modeNote, className = "" }: PathGuidanceCardProps) {
  return (
    <section className={`rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950 ${className}`.trim()}>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">Path format</p>
      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <div>
          <p className="font-medium text-amber-950">Compiled artifact</p>
          <p className="mt-1 break-all font-mono text-xs text-amber-900">data/lexicon/snapshots/&lt;snapshot&gt;/words.enriched.jsonl</p>
        </div>
        <div>
          <p className="font-medium text-amber-950">Reviewed directory</p>
          <p className="mt-1 break-all font-mono text-xs text-amber-900">data/lexicon/snapshots/&lt;snapshot&gt;/reviewed/</p>
        </div>
        <div>
          <p className="font-medium text-amber-950">Approved import input</p>
          <p className="mt-1 break-all font-mono text-xs text-amber-900">data/lexicon/snapshots/&lt;snapshot&gt;/reviewed/approved.jsonl</p>
        </div>
        <div>
          <p className="font-medium text-amber-950">Decision ledger</p>
          <p className="mt-1 break-all font-mono text-xs text-amber-900">data/lexicon/snapshots/&lt;snapshot&gt;/reviewed/review.decisions.jsonl</p>
        </div>
      </div>
      <p className="mt-3 text-xs leading-5 text-amber-800">
        Docker-visible equivalents may also use <span className="font-mono">/app/data/...</span>.
      </p>
      <p className="mt-2 text-xs leading-5 text-amber-800">{modeNote}</p>
    </section>
  );
}
