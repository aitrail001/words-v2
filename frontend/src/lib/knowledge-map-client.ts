import { apiClient } from "@/lib/api-client";

export type KnowledgeStatus = "undecided" | "to_learn" | "learning" | "known";
export type KnowledgeEntryType = "word" | "phrase";

export type KnowledgeMapEntrySummary = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  normalized_form: string | null;
  browse_rank: number;
  status: KnowledgeStatus;
  cefr_level: string | null;
  pronunciation: string | null;
  translation: string | null;
  primary_definition: string | null;
  part_of_speech: string | null;
  phrase_kind: string | null;
};

export type KnowledgeMapOverview = {
  bucket_size: number;
  total_entries: number;
  ranges: Array<{
    range_start: number;
    range_end: number;
    total_entries: number;
    counts: Record<KnowledgeStatus, number>;
  }>;
};

export type KnowledgeMapDashboard = {
  total_entries: number;
  counts: Record<KnowledgeStatus, number>;
  discovery_range_start: number | null;
  discovery_range_end: number | null;
  discovery_entry: {
    entry_type: KnowledgeEntryType;
    entry_id: string;
    display_text: string;
    browse_rank: number;
    status: KnowledgeStatus;
  } | null;
  next_learn_entry: {
    entry_type: KnowledgeEntryType;
    entry_id: string;
    display_text: string;
    browse_rank: number;
    status: KnowledgeStatus;
  } | null;
};

export type KnowledgeMapRange = {
  range_start: number;
  range_end: number;
  previous_range_start: number | null;
  next_range_start: number | null;
  items: KnowledgeMapEntrySummary[];
};

export type KnowledgeMapMeaning = {
  id: string;
  definition: string;
  part_of_speech: string | null;
  examples: Array<{ id: string; sentence: string; difficulty: string | null }>;
  translations: Array<{ id: string; language: string; translation: string }>;
  relations: Array<{ id: string; relation_type: string; related_word: string }>;
};

export type KnowledgeMapSense = {
  sense_id: string | null;
  definition: string;
  part_of_speech: string | null;
  examples: Array<{ id: string; sentence: string; difficulty: string | null }>;
};

export type KnowledgeMapEntryDetail = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  normalized_form: string | null;
  browse_rank: number;
  status: KnowledgeStatus;
  cefr_level: string | null;
  pronunciation: string | null;
  translation: string | null;
  primary_definition: string | null;
  meanings: KnowledgeMapMeaning[];
  senses: KnowledgeMapSense[];
  previous_entry: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  next_entry: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
};

export type KnowledgeMapSearchHistoryList = {
  items: Array<{
    query: string;
    entry_type: KnowledgeEntryType | null;
    entry_id: string | null;
    last_searched_at: string;
  }>;
};

export type KnowledgeMapListStatus = "new" | "to_learn" | "learning" | "known";
export type KnowledgeMapListSort = "rank" | "rank_desc" | "alpha";

export const getKnowledgeMapOverview = (): Promise<KnowledgeMapOverview> =>
  apiClient.get<KnowledgeMapOverview>("/knowledge-map/overview");

export const getKnowledgeMapDashboard = (): Promise<KnowledgeMapDashboard> =>
  apiClient.get<KnowledgeMapDashboard>("/knowledge-map/dashboard");

export const getKnowledgeMapRange = (rangeStart: number): Promise<KnowledgeMapRange> =>
  apiClient.get<KnowledgeMapRange>(`/knowledge-map/ranges/${rangeStart}`);

export const getKnowledgeMapEntryDetail = (
  entryType: KnowledgeEntryType,
  entryId: string,
): Promise<KnowledgeMapEntryDetail> =>
  apiClient.get<KnowledgeMapEntryDetail>(`/knowledge-map/entries/${entryType}/${entryId}`);

export const updateKnowledgeEntryStatus = (
  entryType: KnowledgeEntryType,
  entryId: string,
  status: KnowledgeStatus,
): Promise<{ entry_type: KnowledgeEntryType; entry_id: string; status: KnowledgeStatus }> =>
  apiClient.put(`/knowledge-map/entries/${entryType}/${entryId}/status`, { status });

export const searchKnowledgeMap = (query: string): Promise<{ items: KnowledgeMapEntrySummary[] }> =>
  apiClient.get<{ items: KnowledgeMapEntrySummary[] }>(`/knowledge-map/search?q=${encodeURIComponent(query)}`);

export const getKnowledgeMapList = (params: {
  status: KnowledgeMapListStatus;
  q?: string;
  sort?: KnowledgeMapListSort;
  limit?: number;
}): Promise<{ items: KnowledgeMapEntrySummary[] }> => {
  const searchParams = new URLSearchParams();
  searchParams.set("status", params.status);
  if (params.q) {
    searchParams.set("q", params.q);
  }
  if (params.sort) {
    searchParams.set("sort", params.sort);
  }
  if (params.limit) {
    searchParams.set("limit", String(params.limit));
  }
  return apiClient.get<{ items: KnowledgeMapEntrySummary[] }>(`/knowledge-map/list?${searchParams.toString()}`);
};

export const getKnowledgeMapSearchHistory = (): Promise<KnowledgeMapSearchHistoryList> =>
  apiClient.get<KnowledgeMapSearchHistoryList>("/knowledge-map/search-history");

export const createKnowledgeMapSearchHistory = (payload: {
  query: string;
  entry_type?: KnowledgeEntryType;
  entry_id?: string;
}): Promise<{ query: string; entry_type: KnowledgeEntryType | null; entry_id: string | null; last_searched_at?: string }> =>
  apiClient.post("/knowledge-map/search-history", payload);
