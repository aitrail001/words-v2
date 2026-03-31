"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { LearnerPronunciations, LearnerVoiceAsset } from "@/lib/knowledge-map-client";

export type LearnerAccent = "us" | "uk" | "au";

const localeToAccent = (locale: string | null | undefined): LearnerAccent | null => {
  const normalized = (locale ?? "").trim().toLowerCase().replace(/-/g, "_");
  if (normalized === "en_us" || normalized === "us") {
    return "us";
  }
  if (normalized === "en_gb" || normalized === "uk") {
    return "uk";
  }
  if (normalized === "en_au" || normalized === "au") {
    return "au";
  }
  return null;
};

const playbackCache = new Map<string, string>();
let sharedAudio: HTMLAudioElement | null = null;

function normalizePlaybackPath(playbackUrl: string): string {
  return playbackUrl.startsWith("/api/") ? playbackUrl.slice(4) : playbackUrl;
}

export function getPlayableLearnerAccents(
  voiceAssets: LearnerVoiceAsset[] | null | undefined,
): LearnerAccent[] {
  const accents = new Set<LearnerAccent>();
  for (const asset of voiceAssets ?? []) {
    const accent = localeToAccent(asset.locale);
    if (accent) {
      accents.add(accent);
    }
  }
  return accents.size > 0 ? ["us", "uk"] : [];
}

export function getEntryLevelVoiceAssets(
  voiceAssets: LearnerVoiceAsset[] | null | undefined,
): LearnerVoiceAsset[] {
  return (voiceAssets ?? []).filter((asset) => asset.content_scope === "word");
}

export function resolveDisplayedPronunciation(
  pronunciation: string | null | undefined,
  pronunciations: LearnerPronunciations | null | undefined,
  accent: LearnerAccent,
): string | null {
  const normalized = pronunciations ?? {};
  const direct = normalized[accent];
  if (direct) {
    return direct;
  }
  const alternateAccent = accent === "us" ? "uk" : "us";
  if (normalized[alternateAccent]) {
    return normalized[alternateAccent] ?? null;
  }
  if (normalized.au) {
    return normalized.au;
  }
  return pronunciation ?? null;
}

export function resolveLearnerVoiceAsset(
  voiceAssets: LearnerVoiceAsset[] | null | undefined,
  accent: LearnerAccent,
  filters: {
    contentScope?: string;
    meaningId?: string | null;
    meaningExampleId?: string | null;
    phraseSenseId?: string | null;
    phraseSenseExampleId?: string | null;
  } = {},
): LearnerVoiceAsset | null {
  const filtered = (voiceAssets ?? []).filter((asset) => {
    if (filters.contentScope && asset.content_scope !== filters.contentScope) {
      return false;
    }
    if (filters.meaningId !== undefined && (asset.meaning_id ?? null) !== filters.meaningId) {
      return false;
    }
    if (
      filters.meaningExampleId !== undefined
      && (asset.meaning_example_id ?? null) !== filters.meaningExampleId
    ) {
      return false;
    }
    if (filters.phraseSenseId !== undefined && (asset.phrase_sense_id ?? null) !== filters.phraseSenseId) {
      return false;
    }
    if (
      filters.phraseSenseExampleId !== undefined
      && (asset.phrase_sense_example_id ?? null) !== filters.phraseSenseExampleId
    ) {
      return false;
    }
    return Boolean(asset.playback_url);
  });

  if (filtered.length === 0) {
    return null;
  }

  const exact = filtered.find((asset) => localeToAccent(asset.locale) === accent);
  if (exact) {
    return exact;
  }

  const alternateAccent = accent === "us" ? "uk" : "us";
  const alternate = filtered.find((asset) => localeToAccent(asset.locale) === alternateAccent);
  if (alternate) {
    return alternate;
  }

  return filtered[0] ?? null;
}

async function fetchAudioBlobUrl(playbackUrl: string): Promise<string> {
  const normalizedPlaybackUrl = normalizePlaybackPath(playbackUrl);
  const cached = playbackCache.get(normalizedPlaybackUrl);
  if (cached) {
    return cached;
  }

  const blob = await apiClient.getBlob(normalizedPlaybackUrl);
  const objectUrl = URL.createObjectURL(blob);
  playbackCache.set(normalizedPlaybackUrl, objectUrl);
  return objectUrl;
}

export async function playLearnerEntryAudio(
  voiceAssets: LearnerVoiceAsset[] | null | undefined,
  accent: LearnerAccent,
  filters: {
    contentScope?: string;
    meaningId?: string | null;
    meaningExampleId?: string | null;
    phraseSenseId?: string | null;
    phraseSenseExampleId?: string | null;
  } = {},
): Promise<boolean> {
  const asset = resolveLearnerVoiceAsset(voiceAssets, accent, filters);
  if (!asset?.playback_url) {
    return false;
  }

  const objectUrl = await fetchAudioBlobUrl(asset.playback_url);
  if (!sharedAudio) {
    sharedAudio = new Audio();
  }
  sharedAudio.pause();
  sharedAudio.src = objectUrl;
  await sharedAudio.play();
  return true;
}

export function useLearnerAudio() {
  const [loadingUrl, setLoadingUrl] = useState<string | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const play = useCallback(async (playbackUrl: string) => {
    setLoadingUrl(playbackUrl);
    const objectUrl = await fetchAudioBlobUrl(playbackUrl);
    if (!sharedAudio) {
      sharedAudio = new Audio();
    }
    sharedAudio.pause();
    sharedAudio.src = objectUrl;
    await sharedAudio.play();
    if (mountedRef.current) {
      setLoadingUrl(null);
      setPlayingUrl(playbackUrl);
    }
  }, []);

  return { play, loadingUrl, playingUrl };
}
