"use client";

import Link from "next/link";
import { startTransition, useEffect, useState, type CSSProperties } from "react";
import {
  getKnowledgeMapEntryDetail,
  type KnowledgeEntryType,
  type KnowledgeMapEntryDetail,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences, type UserPreferences } from "@/lib/user-preferences-client";

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "Should Learn",
  learning: "Learning",
  known: "Known",
};

const PRIMARY_STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "Should Learn" },
  { status: "known", label: "Already Know" },
];

const ALL_STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "To Learn" },
  { status: "learning", label: "Learning" },
  { status: "known", label: "Known" },
];

const ACCENT_LABELS: Record<UserPreferences["accent_preference"], string> = {
  us: "US",
  uk: "UK",
  au: "AU",
};

function statusChipClass(status: KnowledgeStatus): string {
  switch (status) {
    case "known":
      return "bg-[#dcfbff] text-[#1485a5]";
    case "learning":
      return "bg-[#f0d9ff] text-[#8d3cff]";
    case "to_learn":
      return "bg-[#ecd6ff] text-[#8e26ff]";
    default:
      return "bg-[#e4e7f3] text-[#59607d]";
  }
}

function actionButtonClass(status: KnowledgeStatus, activeStatus: KnowledgeStatus): string {
  if (status === activeStatus) {
    return status === "known"
      ? "bg-[#45c5dd] text-white"
      : "bg-[#a52fff] text-white";
  }

  return "bg-white text-[#684f85]";
}

function buildHeroStyle(seed: string): CSSProperties {
  const palettes = [
    ["#2f1450", "#8f2fff", "#4bc6de"],
    ["#211243", "#5d28bf", "#38d1c8"],
    ["#38155d", "#bf2dff", "#63c7ff"],
    ["#2b1247", "#7c3bff", "#46cddd"],
  ];
  const hash = Array.from(seed).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const palette = palettes[hash % palettes.length];

  return {
    backgroundImage: [
      "radial-gradient(circle at 22% 18%, rgba(255,255,255,0.30), transparent 18%)",
      "radial-gradient(circle at 80% 15%, rgba(255,255,255,0.18), transparent 12%)",
      `radial-gradient(circle at 70% 72%, ${palette[2]}aa, transparent 30%)`,
      `linear-gradient(160deg, ${palette[0]} 0%, ${palette[1]} 55%, ${palette[2]} 100%)`,
    ].join(", "),
  };
}

function formatRelationType(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

export function getKnowledgeEntryHref(entryType: KnowledgeEntryType, entryId: string): string {
  return entryType === "word" ? `/word/${entryId}` : `/phrase/${entryId}`;
}

export function KnowledgeEntryDetailPage({
  entryType,
  entryId,
}: {
  entryType: KnowledgeEntryType;
  entryId: string;
}) {
  const [detail, setDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [preferences, setPreferences] = useState<UserPreferences>({
    accent_preference: "us",
    translation_locale: "zh-Hans",
    knowledge_view_preference: "cards",
    show_translations_by_default: true,
  });
  const [showTranslations, setShowTranslations] = useState(true);
  const [meaningIndex, setMeaningIndex] = useState(0);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let active = true;
    setLoadState("loading");
    setDetail(null);
    setMeaningIndex(0);

    Promise.all([
      getKnowledgeMapEntryDetail(entryType, entryId),
      getUserPreferences(),
    ])
      .then(([detailResponse, preferencesResponse]) => {
        if (!active) {
          return;
        }
        setPreferences(preferencesResponse);
        setShowTranslations(preferencesResponse.show_translations_by_default);
        setDetail(detailResponse);
        setLoadState("ready");
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setLoadState("error");
      });

    return () => {
      active = false;
    };
  }, [entryId, entryType]);

  const updateStatus = async (status: KnowledgeStatus) => {
    if (!detail) {
      return;
    }
    const response = await updateKnowledgeEntryStatus(detail.entry_type, detail.entry_id, status);
    startTransition(() => {
      setDetail((current) => (current ? { ...current, status: response.status } : current));
    });
  };

  if (loadState === "loading") {
    return <p className="text-sm text-slate-500">Loading learner detail...</p>;
  }

  if (loadState === "error" || !detail) {
    return (
      <section className="mx-auto max-w-[46rem] rounded-[2rem] bg-white/94 px-5 py-6 text-[#43235f] shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <h1 className="text-[1.7rem] font-semibold text-[#572c80]">Unable to load this entry</h1>
        <p className="mt-3 text-sm leading-6 text-[#6d6084]">
          The learner card could not be loaded right now.
        </p>
        <Link
          href="/knowledge-map"
          className="mt-5 inline-flex rounded-[1rem] bg-[#f1ddff] px-4 py-3 text-sm font-semibold text-[#7d2cff]"
        >
          Back to Knowledge Map
        </Link>
      </section>
    );
  }

  const contentItems = detail.entry_type === "word" ? detail.meanings : detail.senses;
  const activeContent =
    contentItems[Math.min(meaningIndex, Math.max(contentItems.length - 1, 0))] ?? null;
  const activeWordMeaning = detail.entry_type === "word"
    ? detail.meanings[Math.min(meaningIndex, Math.max(detail.meanings.length - 1, 0))] ?? null
    : null;
  const contentCount = Math.max(contentItems.length, 1);
  const activeDefinition = activeContent?.definition ?? detail.primary_definition;
  const activePartOfSpeech = activeContent?.part_of_speech ?? null;
  const activeExample = activeContent?.examples[0]?.sentence ?? null;
  const activeTranslation =
    detail.entry_type === "word"
      ? activeWordMeaning?.translations.find(
          (translation) => translation.language === preferences.translation_locale,
        )?.translation ??
        activeWordMeaning?.translations[0]?.translation ??
        detail.translation
      : detail.translation;
  const accentLabel = detail.pronunciation
    ? `${ACCENT_LABELS[preferences.accent_preference]} Accent`
    : null;
  const statusActions = detail.status === "undecided" ? PRIMARY_STATUS_ACTIONS : ALL_STATUS_ACTIONS;

  return (
    <div
      data-testid="knowledge-detail-mobile-shell"
      className="mx-auto max-w-[46rem] space-y-3 pb-32 text-[#43235f]"
    >
      <section
        data-testid="knowledge-detail-hero"
        className="relative overflow-hidden rounded-[0.75rem] shadow-[0_10px_24px_rgba(84,46,135,0.10)]"
      >
        <div className="h-[18rem]" style={buildHeroStyle(detail.display_text)} />

        <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 py-4">
          <Link
            href="/knowledge-map"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/75 text-sm font-semibold text-[#62368f] backdrop-blur"
          >
            ←
          </Link>
          <button
            type="button"
            aria-label="Detail options"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/75 text-sm font-semibold text-[#62368f] backdrop-blur"
          >
            •••
          </button>
        </div>

        <div className="absolute inset-x-0 bottom-0 h-20 bg-[linear-gradient(180deg,transparent,rgba(34,12,66,0.32))]" />
      </section>

      <section>
        <div className="space-y-3 rounded-[0.55rem] bg-white px-4 py-4 shadow-[0_8px_20px_rgba(85,48,139,0.08)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-[1.55rem] font-semibold leading-none text-[#572c80]">
                {detail.display_text}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm font-semibold text-[#7c7395]">
                {accentLabel && detail.pronunciation && (
                  <span className="rounded-full bg-[#eef8ff] px-3 py-1 text-[#1687a6]">
                    {accentLabel}
                  </span>
                )}
                <span>{detail.pronunciation ?? "Pronunciation unavailable"}</span>
                <span>#{detail.browse_rank.toLocaleString()}</span>
              </div>
            </div>
            <span className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[#7ebed7]">
              {activePartOfSpeech ?? detail.entry_type}
            </span>
            <span className="sr-only">Status: {STATUS_LABELS[detail.status]}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[0.74rem] font-semibold text-[#7c7395]">
            {detail.cefr_level && <span>{detail.cefr_level}</span>}
            {detail.entry_type === "phrase" && detail.normalized_form && <span>{detail.normalized_form}</span>}
          </div>

          {showTranslations && activeTranslation && (
            <p className="text-sm font-semibold text-[#9a39f2]">{activeTranslation}</p>
          )}

          <p className="text-[1rem] font-semibold leading-6 text-[#4d295f]">
            {activeDefinition ?? "No learner definition has been generated yet."}
          </p>

          {activeExample && (
            <div className="border-t border-[#ebedf5] pt-2">
              <p className="text-[0.92rem] italic leading-6 text-[#5e4a74]">{activeExample}</p>
            </div>
          )}

          {contentCount > 1 && (
            <div className="flex items-center justify-between gap-3 rounded-[0.45rem] bg-[#f6f4fb] px-3 py-2.5">
              <button
                type="button"
                onClick={() => setMeaningIndex((current) => Math.max(current - 1, 0))}
                disabled={meaningIndex === 0}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-xl font-semibold text-[#6d35cb] disabled:opacity-40"
              >
                {"<"}
              </button>
              <p className="text-sm font-semibold text-[#5f4f78]">
                Meaning {meaningIndex + 1} of {contentCount}
              </p>
              <button
                type="button"
                onClick={() =>
                  setMeaningIndex((current) => Math.min(current + 1, contentCount - 1))
                }
                disabled={meaningIndex >= contentCount - 1}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-xl font-semibold text-[#6d35cb] disabled:opacity-40"
              >
                {">"}
              </button>
            </div>
          )}
        </div>
      </section>

      {(detail.relation_groups.length > 0 || detail.confusable_words.length > 0) && (
        <section className="space-y-3 rounded-[0.55rem] bg-[#f5f6fb] px-3 py-3">
          <div className="text-center">
            <p className="text-sm font-semibold tracking-[0.12em] text-[#8e38f2]">Pro Tips</p>
          </div>

          {detail.relation_groups.map((group) => (
            <article
              key={group.relation_type}
              className="rounded-[0.45rem] bg-white px-4 py-4 shadow-[0_6px_16px_rgba(86,54,145,0.06)]"
            >
              <h2 className="text-lg font-semibold text-[#572c80]">
                {formatRelationType(group.relation_type)}
              </h2>
              <p className="mt-1 text-sm leading-6 text-[#7a6d90]">
                Use this link to separate close meanings faster while you review.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {group.related_words.map((relatedWord) => (
                  <span
                    key={`${group.relation_type}-${relatedWord}`}
                    className="rounded-full bg-[#f1ddff] px-3 py-2 text-sm font-semibold text-[#7d2cff]"
                  >
                    {relatedWord}
                  </span>
                ))}
              </div>
            </article>
          ))}

          {detail.confusable_words.length > 0 && (
            <article className="rounded-[0.45rem] bg-white px-4 py-4 shadow-[0_6px_16px_rgba(86,54,145,0.06)]">
              <h2 className="text-lg font-semibold text-[#572c80]">Confusing Words</h2>
              <p className="mt-1 text-sm leading-6 text-[#7a6d90]">
                Watch these nearby forms before you mark the word as fully known.
              </p>
              <div className="mt-3 space-y-3">
                {detail.confusable_words.map((item) => (
                  <div key={`${item.word}-${item.note ?? "note"}`} className="rounded-[0.4rem] bg-[#f8f5fc] px-4 py-3">
                    <p className="font-semibold text-[#53287c]">{item.word}</p>
                    {item.note && (
                      <p className="mt-1 text-sm leading-6 text-[#75698a]">{item.note}</p>
                    )}
                  </div>
                ))}
              </div>
            </article>
          )}
        </section>
      )}

      <div
        data-testid="knowledge-detail-bottom-bar"
        className="fixed bottom-[calc(env(safe-area-inset-bottom,0px)+5.85rem)] left-1/2 z-30 flex w-[min(46rem,calc(100vw-1rem))] -translate-x-1/2 flex-col gap-2 rounded-[0.65rem] bg-[rgba(245,240,252,0.96)] p-2.5 shadow-[0_12px_26px_rgba(84,46,135,0.14)] backdrop-blur"
      >
        <button
          type="button"
          onClick={() => setShowTranslations((current) => !current)}
          className={`rounded-[0.95rem] px-4 py-3 text-sm font-semibold ${
            showTranslations ? "bg-[#f1ddff] text-[#7d2cff]" : "bg-white text-[#684f85]"
          }`}
        >
          Translation {showTranslations ? "On" : "Off"}
        </button>

        <div className={`grid gap-3 ${statusActions.length === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
          {statusActions.map((action) => (
            <button
              key={action.status}
              type="button"
              onClick={() => void updateStatus(action.status)}
              className={`rounded-[0.95rem] px-3 py-3 text-sm font-semibold ${actionButtonClass(action.status, detail.status)}`}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
