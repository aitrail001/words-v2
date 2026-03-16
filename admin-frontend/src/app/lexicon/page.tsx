import Link from "next/link";

const cards = [
  {
    href: "/lexicon/words",
    title: "Words",
    description: "Inspect imported DB words and see the full persisted lexicon schema, including provenance and translations.",
    testId: "lexicon-landing-words-link",
  },
  {
    href: "/lexicon/ops",
    title: "Operations",
    description: "Monitor offline snapshot folders, artifact counts, and pipeline progress for the active lexicon workflow.",
    testId: "lexicon-landing-ops-link",
  },
  {
    href: "/lexicon/review",
    title: "Legacy Review",
    description: "Open the older staged-review flow for optional `selection_decisions.jsonl` imports and manual publish review.",
    testId: "lexicon-landing-review-link",
  },
];

export default function LexiconPage() {
  return (
    <div className="space-y-6" data-testid="lexicon-landing-page">
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-gray-900">Lexicon Admin</h2>
        <p className="mt-2 max-w-3xl text-sm text-gray-600">
          The active operator workflow is split by concern: inspect imported DB words in
          <span className="font-medium"> Words</span>, inspect offline snapshot progress in
          <span className="font-medium"> Operations</span>, and keep staged review available only as a
          <span className="font-medium"> legacy</span> tool.
        </p>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        {cards.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm transition hover:border-blue-300 hover:bg-blue-50"
            data-testid={card.testId}
          >
            <h3 className="text-lg font-semibold text-gray-900">{card.title}</h3>
            <p className="mt-2 text-sm text-gray-600">{card.description}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
