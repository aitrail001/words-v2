import { apiClient } from "@/lib/api-client";

export const SUPPORTED_TRANSLATION_LOCALES = ["ar", "es", "ja", "pt-BR", "zh-Hans"] as const;
export type TranslationLocale = (typeof SUPPORTED_TRANSLATION_LOCALES)[number];
export const TRANSLATION_LANGUAGE_LABELS: Record<TranslationLocale, string> = {
  ar: "Arabic",
  es: "Spanish",
  ja: "Japanese",
  "pt-BR": "Portuguese (Brazil)",
  "zh-Hans": "Chinese (Simplified)",
};

export type UserPreferences = {
  accent_preference: "us" | "uk" | "au";
  translation_locale: TranslationLocale;
  knowledge_view_preference: "cards" | "tags" | "list";
  show_translations_by_default: boolean;
  review_depth_preset: "gentle" | "balanced" | "deep";
  timezone: string;
  enable_confidence_check: boolean;
  enable_word_spelling: boolean;
  enable_audio_spelling: boolean;
  show_pictures_in_questions: boolean;
};

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  accent_preference: "us",
  translation_locale: "zh-Hans",
  knowledge_view_preference: "cards",
  show_translations_by_default: true,
  review_depth_preset: "balanced",
  timezone: "UTC",
  enable_confidence_check: true,
  enable_word_spelling: true,
  enable_audio_spelling: false,
  show_pictures_in_questions: false,
};

export const getUserPreferences = (): Promise<UserPreferences> =>
  apiClient.get<UserPreferences>("/user-preferences");

export const updateUserPreferences = (payload: UserPreferences): Promise<UserPreferences> =>
  apiClient.put<UserPreferences>("/user-preferences", payload);

export const detectDeviceTimezone = (): string | null => {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return timezone || null;
};

export const syncDetectedDeviceTimezone = async (
  preferences: UserPreferences,
  detectedTimezone: string | null = detectDeviceTimezone(),
): Promise<UserPreferences> => {
  if (!detectedTimezone || detectedTimezone === preferences.timezone) {
    return preferences;
  }

  return apiClient.put<UserPreferences>("/user-preferences", {
    timezone: detectedTimezone,
  });
};
