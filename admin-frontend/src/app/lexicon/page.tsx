"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  LexiconCandidateMetadata,
  LexiconReviewBatch,
  LexiconReviewBatchPublishPreview,
  LexiconReviewCandidateEntry,
  LexiconReviewItem,
  LexiconReviewStatus,
  getLexiconReviewBatch,
  importLexiconReviewBatch,
  listLexiconReviewBatches,
  listLexiconReviewItems,
  previewLexiconReviewBatchPublish,
  publishLexiconReviewBatch,
  updateLexiconReviewItem,
} from "@/lib/lexicon-reviews-client";
import {
  WordEnrichmentDetail,
  WordSearchResult,
  getWordEnrichmentDetail,
  searchWords,
} from "@/lib/words-client";

const REVIEW_STATUSES: LexiconReviewStatus[] = ["pending", "approved", "rejected", "needs_edit"];
const RISK_BANDS = ["all", "deterministic_only", "rerank_recommended", "rerank_and_review_candidate"] as const;
type ReviewRequiredFilter = "all" | "true" | "false";
type TabKey = "review" | "db";

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const parseOverrideIds = (value: string): string[] | null => {
  const ids = value.split(/[\s,]+/).map((part) => part.trim()).filter(Boolean);
  return ids.length > 0 ? ids : null;
};

const selectedIdsForItem = (item: LexiconReviewItem | null): string[] => {
  if (!item) return [];
  if (item.selected_wn_synset_ids?.length) return item.selected_wn_synset_ids;
  return item.review_override_wn_synset_ids ?? item.reranked_selected_wn_synset_ids ?? item.deterministic_selected_wn_synset_ids ?? [];
};

const formatSourceLabel = (value: string | null | undefined): string => {
  const labels: Record<string, string> = {
    review_override: "Review override",
    reranked: "Reranked",
    deterministic: "Deterministic",
    none: "None",
  };
  if (!value) return "Unknown";
  return labels[value] ?? value.replaceAll("_", " ");
};

const normalizeFlags = (metadata?: LexiconCandidateMetadata): string[] => {
  const values = metadata?.candidate_flags ?? metadata?.flags;
  return Array.isArray(values)
    ? values.map((value) => String(value).trim()).filter(Boolean)
    : [];
};

const formatNumericHint = (value: number | null | undefined): string | null => {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
};

const deriveCandidateEntries = (item: LexiconReviewItem | null): LexiconReviewCandidateEntry[] => {
  if (!item) return [];
  if (item.candidate_entries?.length) return item.candidate_entries;

  const metadataById = new Map<string, LexiconCandidateMetadata>();
  for (const candidate of item.candidate_metadata ?? []) {
    const synsetId = String(candidate.wn_synset_id ?? "").trim();
    if (!synsetId || metadataById.has(synsetId)) continue;
    metadataById.set(synsetId, candidate);
  }

  const orderedIds = [
    ...metadataById.keys(),
    ...selectedIdsForItem(item),
    ...(item.deterministic_selected_wn_synset_ids ?? []),
    ...(item.reranked_selected_wn_synset_ids ?? []),
    ...(item.review_override_wn_synset_ids ?? []),
  ].filter((value, index, values) => value && values.indexOf(value) === index);

  const deterministicSet = new Set(item.deterministic_selected_wn_synset_ids ?? []);
  const rerankedSet = new Set(item.reranked_selected_wn_synset_ids ?? []);
  const overrideSet = new Set(item.review_override_wn_synset_ids ?? []);
  const selectedSet = new Set(selectedIdsForItem(item));

  return orderedIds.map((synsetId) => {
    const metadata = metadataById.get(synsetId);
    return {
      wn_synset_id: synsetId,
      canonical_label: String(metadata?.canonical_label ?? metadata?.label ?? "").trim() || null,
      gloss: String(metadata?.canonical_gloss ?? metadata?.gloss ?? metadata?.definition ?? "").trim() || null,
      definition: String(metadata?.definition ?? metadata?.canonical_gloss ?? metadata?.gloss ?? "").trim() || null,
      part_of_speech: String(metadata?.part_of_speech ?? metadata?.pos ?? "").trim() || null,
      rank_hint:
        typeof metadata?.rerank_rank === "number"
          ? metadata.rerank_rank
          : typeof metadata?.candidate_rank === "number"
            ? metadata.candidate_rank
            : typeof metadata?.selection_rank === "number"
              ? metadata.selection_rank
              : typeof metadata?.rank === "number"
                ? metadata.rank
                : null,
      reason_hint:
        String(
          metadata?.reason_hint
            ?? metadata?.selection_reason
            ?? metadata?.rerank_reason
            ?? metadata?.note
            ?? "",
        ).trim() || null,
      deterministic_selected: deterministicSet.has(synsetId),
      reranked_selected: rerankedSet.has(synsetId),
      review_override_selected: overrideSet.has(synsetId),
      selected: selectedSet.has(synsetId),
    };
  });
};

type DetailBadgeTone = "blue" | "green" | "amber" | "slate" | "violet";

const DETAIL_BADGE_TONES: Record<DetailBadgeTone, string> = {
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  green: "border-green-200 bg-green-50 text-green-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  slate: "border-gray-200 bg-gray-100 text-gray-700",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
};

const DetailBadge = ({ children, tone = "slate" }: { children: ReactNode; tone?: DetailBadgeTone }) => (
  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${DETAIL_BADGE_TONES[tone]}`}>
    {children}
  </span>
);

type SenseCardProps = {
  entry: LexiconReviewCandidateEntry;
  metadata?: LexiconCandidateMetadata;
  fallbackLabel: string;
};

const SenseCard = ({ entry, metadata, fallbackLabel }: SenseCardProps) => {
  const label = entry.canonical_label ?? fallbackLabel;
  const flags = normalizeFlags(metadata);
  const score = formatNumericHint(
    typeof metadata?.selection_score === "number"
      ? metadata.selection_score
      : typeof metadata?.score === "number"
        ? metadata.score
        : undefined,
  );
  const lemmaCount = formatNumericHint(typeof metadata?.lemma_count === "number" ? metadata.lemma_count : undefined);
  const borderClass = entry.selected
    ? "border-blue-300 bg-blue-50"
    : entry.review_override_selected
      ? "border-green-200 bg-green-50"
      : entry.reranked_selected
        ? "border-violet-200 bg-violet-50"
        : entry.deterministic_selected
          ? "border-amber-200 bg-amber-50"
          : "border-gray-200 bg-white";

  return (
    <article className={`rounded-lg border p-4 text-sm ${borderClass}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-base font-semibold text-gray-900">{label}</p>
          <p className="mt-1 break-all font-mono text-xs text-gray-500">{entry.wn_synset_id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {entry.part_of_speech ? <DetailBadge>{entry.part_of_speech}</DetailBadge> : null}
          {entry.rank_hint !== null ? <DetailBadge tone="slate">rank {entry.rank_hint}</DetailBadge> : null}
          {entry.selected ? <DetailBadge tone="blue">current</DetailBadge> : null}
          {entry.review_override_selected ? <DetailBadge tone="green">override</DetailBadge> : null}
          {entry.reranked_selected ? <DetailBadge tone="violet">reranked</DetailBadge> : null}
          {entry.deterministic_selected ? <DetailBadge tone="amber">deterministic</DetailBadge> : null}
        </div>
      </div>
      <div className="mt-3 space-y-2 text-gray-700">
        <p><span className="font-medium text-gray-900">Gloss:</span> {entry.gloss ?? "—"}</p>
        {entry.definition && entry.definition !== entry.gloss ? (
          <p><span className="font-medium text-gray-900">Definition:</span> {entry.definition}</p>
        ) : null}
        {entry.reason_hint ? <p><span className="font-medium text-gray-900">Reason hint:</span> {entry.reason_hint}</p> : null}
      </div>
      {(flags.length > 0 || score || lemmaCount) ? (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-600">
          {score ? <DetailBadge tone="slate">score {score}</DetailBadge> : null}
          {lemmaCount ? <DetailBadge tone="slate">lemma count {lemmaCount}</DetailBadge> : null}
          {flags.map((flag) => <DetailBadge key={flag} tone="slate">{flag}</DetailBadge>)}
        </div>
      ) : null}
    </article>
  );
};

type SenseSectionProps = {
  title: string;
  description: string;
  entries: LexiconReviewCandidateEntry[];
  metadataById: Map<string, LexiconCandidateMetadata | undefined>;
  fallbackLabel: string;
  emptyText: string;
  testId: string;
};

const SenseSection = ({
  title,
  description,
  entries,
  metadataById,
  fallbackLabel,
  emptyText,
  testId,
}: SenseSectionProps) => (
  <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4" data-testid={testId}>
    <div>
      <h4 className="text-base font-semibold text-gray-900">{title}</h4>
      <p className="text-sm text-gray-500">{description}</p>
    </div>
    {entries.length > 0 ? (
      <div className="space-y-3">
        {entries.map((entry) => (
          <SenseCard
            key={`${testId}-${entry.wn_synset_id}`}
            entry={entry}
            metadata={metadataById.get(entry.wn_synset_id)}
            fallbackLabel={fallbackLabel}
          />
        ))}
      </div>
    ) : (
      <p className="text-sm text-gray-500">{emptyText}</p>
    )}
  </section>
);

export default function LexiconPage() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("review");

  const [batches, setBatches] = useState<LexiconReviewBatch[]>([]);
  const [batchDetail, setBatchDetail] = useState<LexiconReviewBatch | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const selectedBatchIdRef = useRef("");
  const [batchesLoading, setBatchesLoading] = useState(false);
  const [batchesError, setBatchesError] = useState<string | null>(null);

  const [importFile, setImportFile] = useState<File | null>(null);
  const [importSourceReference, setImportSourceReference] = useState("");
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  const [reviewStatusFilter, setReviewStatusFilter] = useState("all");
  const [riskBandFilter, setRiskBandFilter] = useState<(typeof RISK_BANDS)[number]>("all");
  const [reviewRequiredFilter, setReviewRequiredFilter] = useState<ReviewRequiredFilter>("all");

  const [items, setItems] = useState<LexiconReviewItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState("");

  const [editorStatus, setEditorStatus] = useState<LexiconReviewStatus>("pending");
  const [editorComment, setEditorComment] = useState("");
  const [editorOverrideIds, setEditorOverrideIds] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const [preview, setPreview] = useState<LexiconReviewBatchPublishPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [publishLoading, setPublishLoading] = useState(false);
  const [publishMessage, setPublishMessage] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<WordSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedWordId, setSelectedWordId] = useState("");
  const [wordDetail, setWordDetail] = useState<WordEnrichmentDetail | null>(null);
  const [wordDetailLoading, setWordDetailLoading] = useState(false);
  const [wordDetailError, setWordDetailError] = useState<string | null>(null);

  const selectedBatch = useMemo(() => batches.find((batch) => batch.id === selectedBatchId) ?? batchDetail, [batches, batchDetail, selectedBatchId]);
  useEffect(() => {
    const hasToken = Boolean(readAccessToken());
    setIsAuthenticated(hasToken);
    if (!hasToken) {
      redirectToLogin("/lexicon");
    }
  }, []);
  const selectedItem = useMemo(() => items.find((item) => item.id === selectedItemId) ?? null, [items, selectedItemId]);

  useEffect(() => { selectedBatchIdRef.current = selectedBatchId; }, [selectedBatchId]);

  const loadBatches = useCallback(async (preferredBatchId?: string) => {
    setBatchesLoading(true);
    setBatchesError(null);
    try {
      const nextBatches = await listLexiconReviewBatches();
      setBatches(nextBatches);
      const currentSelected = selectedBatchIdRef.current;
      const targetBatchId = preferredBatchId ?? (nextBatches.some((batch) => batch.id === currentSelected) ? currentSelected : nextBatches[0]?.id ?? "");
      setSelectedBatchId(targetBatchId);
      if (targetBatchId) {
        setBatchDetail(await getLexiconReviewBatch(targetBatchId));
      } else {
        setBatchDetail(null);
      }
    } catch (error) {
      console.error("Failed to load lexicon review batches", error);
      setBatchesError("Failed to load lexicon review batches.");
    } finally {
      setBatchesLoading(false);
    }
  }, []);

  useEffect(() => { void loadBatches(); }, [loadBatches]);

  useEffect(() => {
    if (!selectedBatchId) {
      setItems([]);
      setSelectedItemId("");
      return;
    }
    let active = true;
    setItemsLoading(true);
    setItemsError(null);
    setPreview(null);
    setPreviewError(null);
    const filters = {
      ...(reviewStatusFilter !== "all" ? { reviewStatus: reviewStatusFilter as LexiconReviewStatus } : {}),
      ...(riskBandFilter !== "all" ? { riskBand: riskBandFilter } : {}),
      ...(reviewRequiredFilter !== "all" ? { reviewRequired: reviewRequiredFilter === "true" } : {}),
    };
    void (async () => {
      try {
        const [detail, nextItems] = await Promise.all([
          getLexiconReviewBatch(selectedBatchId),
          listLexiconReviewItems(selectedBatchId, filters),
        ]);
        if (!active) return;
        setBatchDetail(detail);
        setItems(nextItems);
        setSelectedItemId((current) => nextItems.some((item) => item.id === current) ? current : (nextItems[0]?.id ?? ""));
      } catch (error) {
        console.error("Failed to load lexicon review items", error);
        if (!active) return;
        setItemsError("Failed to load lexicon review items.");
        setItems([]);
        setSelectedItemId("");
      } finally {
        if (active) setItemsLoading(false);
      }
    })();
    return () => { active = false; };
  }, [selectedBatchId, reviewStatusFilter, riskBandFilter, reviewRequiredFilter]);

  useEffect(() => {
    if (!selectedItem) {
      setEditorStatus("pending");
      setEditorComment("");
      setEditorOverrideIds("");
      return;
    }
    setEditorStatus(selectedItem.review_status);
    setEditorComment(selectedItem.review_comment ?? "");
    setEditorOverrideIds((selectedItem.review_override_wn_synset_ids ?? []).join("\n"));
    setSaveMessage(null);
  }, [selectedItem]);

  const handleImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!importFile) {
      setImportError("Choose a selection_decisions JSONL file first.");
      return;
    }
    setImportLoading(true);
    setImportError(null);
    try {
      const batch = await importLexiconReviewBatch({ file: importFile, sourceReference: importSourceReference || undefined });
      setImportFile(null);
      setImportSourceReference("");
      const input = document.getElementById("lexicon-review-import-file") as HTMLInputElement | null;
      if (input) input.value = "";
      await loadBatches(batch.id);
      setActiveTab("review");
    } catch (error) {
      console.error("Failed to import review batch", error);
      setImportError("Failed to import review batch.");
    } finally {
      setImportLoading(false);
    }
  };

  const handleSaveItem = async () => {
    if (!selectedItem) return;
    setSaveLoading(true);
    setSaveMessage(null);
    try {
      const updated = await updateLexiconReviewItem(selectedItem.id, {
        review_status: editorStatus,
        review_comment: editorComment.trim() || null,
        review_override_wn_synset_ids: parseOverrideIds(editorOverrideIds),
      });
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSaveMessage("Review decision saved.");
    } catch (error) {
      console.error("Failed to save review item", error);
      setSaveMessage("Failed to save review decision.");
    } finally {
      setSaveLoading(false);
    }
  };

  const handlePreviewPublish = async () => {
    if (!selectedBatchId) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      setPreview(await previewLexiconReviewBatchPublish(selectedBatchId));
    } catch (error) {
      console.error("Failed to preview publish", error);
      setPreview(null);
      setPreviewError("Failed to build publish preview. Make sure there are approved items.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handlePublish = async () => {
    if (!selectedBatchId) return;
    setPublishLoading(true);
    setPublishMessage(null);
    try {
      const result = await publishLexiconReviewBatch(selectedBatchId);
      setPublishMessage(`Published ${result.published_item_count} items to ${result.published_word_count} words.`);
      await loadBatches(selectedBatchId);
      await handlePreviewPublish();
    } catch (error) {
      console.error("Failed to publish batch", error);
      setPublishMessage("Failed to publish approved items.");
    } finally {
      setPublishLoading(false);
    }
  };

  const handleWordSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (searchQuery.trim().length < 2) {
      setSearchResults([]);
      setSearchError("Enter at least 2 characters.");
      return;
    }
    setSearchLoading(true);
    setSearchError(null);
    try {
      const results = await searchWords(searchQuery.trim());
      setSearchResults(results);
      setSelectedWordId((current) => results.some((word) => word.id === current) ? current : (results[0]?.id ?? ""));
    } catch (error) {
      console.error("Failed to search imported words", error);
      setSearchResults([]);
      setSelectedWordId("");
      setSearchError("Failed to search imported words.");
    } finally {
      setSearchLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedWordId) {
      setWordDetail(null);
      return;
    }
    let active = true;
    setWordDetailLoading(true);
    setWordDetailError(null);
    void (async () => {
      try {
        const detail = await getWordEnrichmentDetail(selectedWordId);
        if (!active) return;
        setWordDetail(detail);
      } catch (error) {
        console.error("Failed to load word detail", error);
        if (!active) return;
        setWordDetail(null);
        setWordDetailError("Failed to load word enrichment detail.");
      } finally {
        if (active) setWordDetailLoading(false);
      }
    })();
    return () => { active = false; };
  }, [selectedWordId]);

  const selectedSynsetIds = selectedIdsForItem(selectedItem);
  const candidateEntries = useMemo(() => deriveCandidateEntries(selectedItem), [selectedItem]);
  const candidateMetadataById = useMemo(
    () => new Map(candidateEntries.map((entry) => [entry.wn_synset_id, selectedItem?.candidate_metadata.find((candidate) => String(candidate.wn_synset_id ?? "") === entry.wn_synset_id) ?? undefined])),
    [candidateEntries, selectedItem],
  );
  const candidateEntryById = useMemo(
    () => new Map(candidateEntries.map((entry) => [entry.wn_synset_id, entry])),
    [candidateEntries],
  );
  const toEntries = useCallback(
    (ids: string[] | null | undefined) => (ids ?? []).map((synsetId) => candidateEntryById.get(synsetId) ?? {
      wn_synset_id: synsetId,
      canonical_label: null,
      gloss: null,
      definition: null,
      part_of_speech: null,
      rank_hint: null,
      reason_hint: null,
      deterministic_selected: selectedItem?.deterministic_selected_wn_synset_ids.includes(synsetId) ?? false,
      reranked_selected: selectedItem?.reranked_selected_wn_synset_ids?.includes(synsetId) ?? false,
      review_override_selected: selectedItem?.review_override_wn_synset_ids?.includes(synsetId) ?? false,
      selected: selectedSynsetIds.includes(synsetId),
    }),
    [candidateEntryById, selectedItem, selectedSynsetIds],
  );
  const currentSelectedEntries = useMemo(() => toEntries(selectedSynsetIds), [selectedSynsetIds, toEntries]);
  const deterministicEntries = useMemo(
    () => toEntries(selectedItem?.deterministic_selected_wn_synset_ids),
    [selectedItem, toEntries],
  );
  const rerankedEntries = useMemo(
    () => toEntries(selectedItem?.reranked_selected_wn_synset_ids),
    [selectedItem, toEntries],
  );
  const overrideEntries = useMemo(
    () => toEntries(selectedItem?.review_override_wn_synset_ids),
    [selectedItem, toEntries],
  );

  if (!isAuthenticated) {
    return <div data-testid="admin-auth-loading" className="text-sm text-gray-500">Checking authentication…</div>;
  }

  return (
    <div className="space-y-6" data-testid="lexicon-admin-page">
      <div>
        <h2 className="text-2xl font-bold" data-testid="lexicon-admin-title">Lexicon Admin Portal</h2>
        <p className="text-sm text-gray-600">Review staged lexicon batches, publish approved decisions, and inspect imported learner-facing words already in the local DB.</p>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" data-testid="lexicon-admin-workflow-note">
        <p className="font-medium">Workflow note</p>
        <p>Staged review batches are separate from the main word tables. This portal helps you review and publish staged batches; `import-db` still imports whatever compiled JSONL file you pass to it directly.</p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Lexicon admin tabs">
        <button type="button" onClick={() => setActiveTab("review")} className={`rounded-md px-4 py-2 text-sm font-medium ${activeTab === "review" ? "bg-blue-600 text-white" : "border border-gray-300 bg-white text-gray-700"}`} data-testid="lexicon-tab-review">Review Queue</button>
        <button type="button" onClick={() => setActiveTab("db")} className={`rounded-md px-4 py-2 text-sm font-medium ${activeTab === "db" ? "bg-blue-600 text-white" : "border border-gray-300 bg-white text-gray-700"}`} data-testid="lexicon-tab-db">DB Inspector</button>
      </div>

      {activeTab === "review" ? (
        <div className="space-y-6" data-testid="lexicon-review-panel">
          <form className="space-y-4 rounded-lg border border-gray-200 bg-white p-4" onSubmit={handleImport}>
            <div>
              <h3 className="text-lg font-semibold">Import staged review batch</h3>
              <p className="text-sm text-gray-500">Upload a `selection_decisions.jsonl` file so review-needed items are loaded into staged review tables.</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="lexicon-review-import-file" className="text-sm font-medium text-gray-700">Review JSONL file</label>
                <input id="lexicon-review-import-file" data-testid="lexicon-review-import-file" type="file" accept=".jsonl,application/json" onChange={(event) => setImportFile(event.target.files?.[0] ?? null)} className="w-full rounded-md border border-gray-300 px-3 py-2" />
              </div>
              <div className="space-y-2">
                <label htmlFor="lexicon-review-source-reference" className="text-sm font-medium text-gray-700">Source reference (optional)</label>
                <input id="lexicon-review-source-reference" data-testid="lexicon-review-source-reference" value={importSourceReference} onChange={(event) => setImportSourceReference(event.target.value)} placeholder="lexicon-stage3-preview" className="w-full rounded-md border border-gray-300 px-3 py-2" />
              </div>
            </div>
            <button type="submit" disabled={importLoading} data-testid="lexicon-review-import-submit" className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50">{importLoading ? "Importing..." : "Import Review Batch"}</button>
            {importError ? <p className="text-sm text-red-600">{importError}</p> : null}
          </form>

          <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
            <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4" data-testid="lexicon-batch-list-panel">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-lg font-semibold">Review batches</h3>
                  <p className="text-sm text-gray-500">Existing staged lexicon review imports.</p>
                </div>
                <button type="button" onClick={() => void loadBatches()} className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50" data-testid="lexicon-batches-refresh">Refresh</button>
              </div>
              {batchesLoading ? <p className="text-sm text-gray-500">Loading batches...</p> : null}
              {batchesError ? <p className="text-sm text-red-600">{batchesError}</p> : null}
              {batches.length === 0 && !batchesLoading ? <p className="text-sm text-gray-500" data-testid="lexicon-batches-empty">No staged lexicon review batches yet.</p> : null}
              <div className="space-y-2" data-testid="lexicon-batches-list">
                {batches.map((batch) => (
                  <button key={batch.id} type="button" onClick={() => setSelectedBatchId(batch.id)} className={`w-full rounded-md border p-3 text-left ${selectedBatchId === batch.id ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`} data-testid={`lexicon-batch-${batch.id}`}>
                    <p className="font-medium">{batch.source_filename || batch.snapshot_id || batch.id}</p>
                    <p className="text-xs text-gray-500">status: {batch.status}</p>
                    <p className="text-xs text-gray-500">review required: {batch.review_required_count} / total: {batch.total_items}</p>
                  </button>
                ))}
              </div>
            </section>

            <div className="space-y-6">
              <section className="rounded-lg border border-gray-200 bg-white p-4" data-testid="lexicon-batch-detail-panel">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-semibold">Batch detail</h3>
                    <p className="text-sm text-gray-500">Inspect staged review status before publish.</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={handlePreviewPublish} disabled={!selectedBatchId || previewLoading} data-testid="lexicon-publish-preview-button" className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">{previewLoading ? "Previewing..." : "Publish Preview"}</button>
                    <button type="button" onClick={handlePublish} disabled={!selectedBatchId || publishLoading} data-testid="lexicon-publish-button" className="rounded-md bg-green-600 px-3 py-2 text-sm text-white hover:bg-green-700 disabled:opacity-50">{publishLoading ? "Publishing..." : "Publish Approved"}</button>
                  </div>
                </div>
                {selectedBatch ? (
                  <div className="mt-4 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Snapshot</p><p className="font-medium">{selectedBatch.snapshot_id ?? "—"}</p></div>
                    <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Total items</p><p className="font-medium">{selectedBatch.total_items}</p></div>
                    <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Review required</p><p className="font-medium">{selectedBatch.review_required_count}</p></div>
                    <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Auto accepted</p><p className="font-medium">{selectedBatch.auto_accepted_count}</p></div>
                    <div className="rounded border border-gray-200 p-3 md:col-span-2 xl:col-span-4"><p className="text-gray-500">Source reference</p><p className="font-medium">{selectedBatch.source_reference ?? "—"}</p><p className="mt-1 text-xs text-gray-500">Created {formatDateTime(selectedBatch.created_at)}</p></div>
                  </div>
                ) : <p className="mt-4 text-sm text-gray-500">Select a batch to inspect staged review items.</p>}
                {previewError ? <p className="mt-3 text-sm text-red-600">{previewError}</p> : null}
                {publishMessage ? <p className="mt-3 text-sm text-gray-700">{publishMessage}</p> : null}
                {preview ? (
                  <div className="mt-4 space-y-3 rounded border border-gray-200 bg-gray-50 p-4" data-testid="lexicon-publish-preview-panel">
                    <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-5">
                      <div><span className="text-gray-500">Publishable:</span> {preview.publishable_item_count}</div>
                      <div><span className="text-gray-500">Create words:</span> {preview.created_word_count}</div>
                      <div><span className="text-gray-500">Update words:</span> {preview.updated_word_count}</div>
                      <div><span className="text-gray-500">Replace meanings:</span> {preview.replaced_meaning_count}</div>
                      <div><span className="text-gray-500">Create meanings:</span> {preview.created_meaning_count}</div>
                    </div>
                    <div className="space-y-2">
                      {preview.items.slice(0, 10).map((item) => (
                        <div key={item.item_id} className="rounded border border-gray-200 bg-white p-3 text-sm">
                          <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">{item.lemma}</p><span className="text-xs text-gray-500">{item.action}</span></div>
                          <p className="text-xs text-gray-500">selected synsets: {item.selected_synset_ids.join(", ")}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
                <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
                  <div><h3 className="text-lg font-semibold">Review items</h3><p className="text-sm text-gray-500">Filter and pick a staged item to review.</p></div>
                  <div className="grid gap-3">
                    <label className="text-sm font-medium text-gray-700">Review status<select value={reviewStatusFilter} onChange={(event) => setReviewStatusFilter(event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" data-testid="lexicon-filter-review-status"><option value="all">All</option>{REVIEW_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
                    <label className="text-sm font-medium text-gray-700">Risk band<select value={riskBandFilter} onChange={(event) => setRiskBandFilter(event.target.value as (typeof RISK_BANDS)[number])} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" data-testid="lexicon-filter-risk-band">{RISK_BANDS.map((band) => <option key={band} value={band}>{band}</option>)}</select></label>
                    <label className="text-sm font-medium text-gray-700">Review required<select value={reviewRequiredFilter} onChange={(event) => setReviewRequiredFilter(event.target.value as ReviewRequiredFilter)} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" data-testid="lexicon-filter-review-required"><option value="all">All</option><option value="true">True</option><option value="false">False</option></select></label>
                  </div>
                  {itemsLoading ? <p className="text-sm text-gray-500">Loading items...</p> : null}
                  {itemsError ? <p className="text-sm text-red-600">{itemsError}</p> : null}
                  {items.length === 0 && !itemsLoading ? <p className="text-sm text-gray-500" data-testid="lexicon-items-empty">No items match this filter.</p> : null}
                  <div className="space-y-2" data-testid="lexicon-items-list">
                    {items.map((item) => (
                      <button key={item.id} type="button" onClick={() => setSelectedItemId(item.id)} className={`w-full rounded-md border p-3 text-left ${selectedItemId === item.id ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`} data-testid={`lexicon-item-${item.id}`}>
                        <div className="flex items-center justify-between gap-2"><p className="font-medium">{item.lemma}</p><span className="text-xs text-gray-500">risk {item.selection_risk_score}</span></div>
                        <p className="text-xs text-gray-500">{item.review_status} · {item.risk_band}</p>
                        <p className="text-xs text-gray-500">review required: {String(item.review_required)}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4" data-testid="lexicon-item-detail-panel">
                  {selectedItem ? (
                    <>
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="space-y-2">
                          <div>
                            <h3 className="text-lg font-semibold">Review item: {selectedItem.lemma}</h3>
                            <p className="text-sm text-gray-500">generated {formatDateTime(selectedItem.created_at)}</p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <DetailBadge tone="blue">selected source: {formatSourceLabel(selectedItem.selected_source)}</DetailBadge>
                            <DetailBadge tone={selectedItem.review_required ? "amber" : "green"}>review required: {String(selectedItem.review_required)}</DetailBadge>
                            <DetailBadge>{selectedItem.review_status}</DetailBadge>
                            <DetailBadge>risk band: {selectedItem.risk_band}</DetailBadge>
                            <DetailBadge>risk score: {selectedItem.selection_risk_score}</DetailBadge>
                            <DetailBadge>wordfreq rank: {selectedItem.wordfreq_rank ?? "—"}</DetailBadge>
                          </div>
                        </div>
                      </div>

                      <section className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-4" data-testid="lexicon-item-review-controls">
                        <div>
                          <h4 className="text-base font-semibold text-gray-900">Review decision</h4>
                          <p className="text-sm text-gray-500">Override synset IDs if you want to replace the current selection before publish.</p>
                        </div>
                        <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)]">
                          <label className="text-sm font-medium text-gray-700">Review status<select value={editorStatus} onChange={(event) => setEditorStatus(event.target.value as LexiconReviewStatus)} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" data-testid="lexicon-item-review-status">{REVIEW_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
                          <label className="text-sm font-medium text-gray-700">Override synset ids (newline or comma separated)<textarea value={editorOverrideIds} onChange={(event) => setEditorOverrideIds(event.target.value)} rows={4} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm" data-testid="lexicon-item-override-ids" /></label>
                        </div>
                        <label className="text-sm font-medium text-gray-700">Review comment<textarea value={editorComment} onChange={(event) => setEditorComment(event.target.value)} rows={4} className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" data-testid="lexicon-item-review-comment" /></label>
                        <div className="flex flex-wrap items-center gap-3">
                          <button type="button" onClick={handleSaveItem} disabled={saveLoading} className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50" data-testid="lexicon-item-save-button">{saveLoading ? "Saving..." : "Save Review Decision"}</button>
                          {saveMessage ? <p className="text-sm text-gray-700">{saveMessage}</p> : null}
                        </div>
                      </section>

                      <SenseSection
                        title="Current selected senses"
                        description={`These are the senses that would publish right now (${formatSourceLabel(selectedItem.selected_source)}).`}
                        entries={currentSelectedEntries}
                        metadataById={candidateMetadataById}
                        fallbackLabel={selectedItem.lemma}
                        emptyText="No selected senses are available for this review item."
                        testId="lexicon-item-current-selection"
                      />

                      <SenseSection
                        title="Deterministic baseline"
                        description="Baseline selection before any rerank or manual override."
                        entries={deterministicEntries}
                        metadataById={candidateMetadataById}
                        fallbackLabel={selectedItem.lemma}
                        emptyText="No deterministic baseline senses recorded."
                        testId="lexicon-item-deterministic-selection"
                      />

                      {rerankedEntries.length > 0 ? (
                        <SenseSection
                          title="Reranked selected senses"
                          description="LLM rerank proposal captured for this lexeme."
                          entries={rerankedEntries}
                          metadataById={candidateMetadataById}
                          fallbackLabel={selectedItem.lemma}
                          emptyText="No reranked senses recorded."
                          testId="lexicon-item-reranked-selection"
                        />
                      ) : null}

                      {overrideEntries.length > 0 ? (
                        <SenseSection
                          title="Manual override senses"
                          description="Reviewer override that will take precedence at publish time."
                          entries={overrideEntries}
                          metadataById={candidateMetadataById}
                          fallbackLabel={selectedItem.lemma}
                          emptyText="No override senses recorded."
                          testId="lexicon-item-override-selection"
                        />
                      ) : null}

                      <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4" data-testid="lexicon-item-candidates-section">
                        <div>
                          <h4 className="text-base font-semibold text-gray-900">Candidate senses</h4>
                          <p className="text-sm text-gray-500">Compare every candidate with glosses, definitions, WordNet IDs, POS tags, reason hints, and selection badges.</p>
                        </div>
                        <div className="max-h-[720px] space-y-3 overflow-y-auto pr-1" data-testid="lexicon-item-candidates">
                          {candidateEntries.length > 0 ? candidateEntries.map((entry) => (
                            <SenseCard
                              key={`candidate-${entry.wn_synset_id}`}
                              entry={entry}
                              metadata={candidateMetadataById.get(entry.wn_synset_id)}
                              fallbackLabel={selectedItem.lemma}
                            />
                          )) : <p className="text-sm text-gray-500">No candidate senses recorded for this item.</p>}
                        </div>
                      </section>
                    </>
                  ) : <p className="text-sm text-gray-500">Select a staged review item to inspect and edit.</p>}
                </div>
              </section>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6" data-testid="lexicon-db-panel">
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <div><h3 className="text-lg font-semibold">Imported word inspector</h3><p className="text-sm text-gray-500">Search words already present in the main local DB and inspect learner-facing enrichment.</p></div>
            <form className="mt-4 flex flex-col gap-3 md:flex-row" onSubmit={handleWordSearch}>
              <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search imported words..." className="flex-1 rounded-md border border-gray-300 px-3 py-2" data-testid="lexicon-db-search-input" />
              <button type="submit" disabled={searchLoading} className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50" data-testid="lexicon-db-search-button">{searchLoading ? "Searching..." : "Search"}</button>
            </form>
            {searchError ? <p className="mt-3 text-sm text-red-600">{searchError}</p> : null}
            <div className="mt-4 grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
              <div className="space-y-2" data-testid="lexicon-db-results-list">{searchResults.length === 0 ? <p className="text-sm text-gray-500">No search results yet.</p> : searchResults.map((word) => <button key={word.id} type="button" onClick={() => setSelectedWordId(word.id)} className={`w-full rounded-md border p-3 text-left ${selectedWordId === word.id ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`} data-testid={`lexicon-db-word-${word.id}`}><p className="font-medium">{word.word}</p><p className="text-xs text-gray-500">rank: {word.frequency_rank ?? "—"}</p></button>)}</div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4" data-testid="lexicon-db-word-detail-panel">
                {wordDetailLoading ? <p className="text-sm text-gray-500">Loading word detail...</p> : null}
                {wordDetailError ? <p className="text-sm text-red-600">{wordDetailError}</p> : null}
                {wordDetail ? (
                  <div className="space-y-4">
                    <div><h4 className="text-xl font-semibold">{wordDetail.word}</h4><p className="text-sm text-gray-500">phonetic: {wordDetail.phonetic ?? "—"} · CEFR: {wordDetail.cefr_level ?? "—"} · POS: {wordDetail.part_of_speech?.join(", ") || "—"}</p></div>
                    <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4"><div className="rounded border border-gray-200 bg-white p-3"><p className="text-gray-500">Frequency rank</p><p className="font-medium">{wordDetail.frequency_rank ?? "—"}</p></div><div className="rounded border border-gray-200 bg-white p-3"><p className="text-gray-500">Phonetic source</p><p className="font-medium">{wordDetail.phonetic_source ?? "—"}</p></div><div className="rounded border border-gray-200 bg-white p-3"><p className="text-gray-500">Meanings</p><p className="font-medium">{wordDetail.meanings.length}</p></div><div className="rounded border border-gray-200 bg-white p-3"><p className="text-gray-500">Enrichment runs</p><p className="font-medium">{wordDetail.enrichment_runs.length}</p></div></div>
                    <div className="space-y-3"><p className="text-sm font-medium text-gray-900">Meanings</p>{wordDetail.meanings.map((meaning) => <div key={meaning.id} className="rounded border border-gray-200 bg-white p-4 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">{meaning.order_index + 1}. {meaning.definition}</p><span className="text-xs text-gray-500">{meaning.part_of_speech ?? "—"}</span></div><p className="mt-1 text-xs text-gray-500">wn_synset_id: {meaning.wn_synset_id ?? "—"}</p><p className="mt-1 text-gray-700">domain: {meaning.primary_domain ?? "—"}{meaning.register ? ` · register: ${meaning.register}` : ""}</p>{meaning.usage_note ? <p className="mt-1 text-gray-700">usage: {meaning.usage_note}</p> : null}{meaning.examples.length > 0 ? <div className="mt-2"><p className="text-xs font-medium uppercase tracking-wide text-gray-500">Examples</p><ul className="mt-1 space-y-1 text-gray-700">{meaning.examples.slice(0, 3).map((example) => <li key={example.id}>• {example.sentence}</li>)}</ul></div> : null}</div>)}</div>
                  </div>
                ) : !wordDetailLoading ? <p className="text-sm text-gray-500">Search and select a word to inspect imported learner-facing data.</p> : null}
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
