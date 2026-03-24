import { apiClient } from "@/lib/api-client";

export type UserPreferences = {
  accent_preference: "us" | "uk" | "au";
  translation_locale: string;
  knowledge_view_preference: "cards" | "tags" | "list";
  show_translations_by_default: boolean;
};

export const getUserPreferences = (): Promise<UserPreferences> =>
  apiClient.get<UserPreferences>("/user-preferences");

export const updateUserPreferences = (payload: UserPreferences): Promise<UserPreferences> =>
  apiClient.put<UserPreferences>("/user-preferences", payload);
