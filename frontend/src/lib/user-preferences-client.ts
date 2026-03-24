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
};

export const getUserPreferences = (): Promise<UserPreferences> =>
  apiClient.get<UserPreferences>("/user-preferences");

export const updateUserPreferences = (payload: UserPreferences): Promise<UserPreferences> =>
  apiClient.put<UserPreferences>("/user-preferences", payload);
