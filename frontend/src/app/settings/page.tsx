"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  DEFAULT_USER_PREFERENCES,
  getUserPreferences,
  SUPPORTED_TRANSLATION_LOCALES,
  TRANSLATION_LANGUAGE_LABELS,
  type TranslationLocale,
  updateUserPreferences,
  type UserPreferences,
} from "@/lib/user-preferences-client";

type AccentPreference = UserPreferences["accent_preference"];
type ViewPreference = UserPreferences["knowledge_view_preference"];

function accentButtonClass(active: boolean): string {
  return active
    ? "bg-[#38c7dd] text-white"
    : "bg-[#efedf7] text-[#7a6794]";
}

function viewButtonClass(active: boolean): string {
  return active
    ? "bg-[#38c7dd] text-white"
    : "bg-[#efedf7] text-[#7a6794]";
}

export default function SettingsPage() {
  const [preferences, setPreferences] = useState<UserPreferences>(DEFAULT_USER_PREFERENCES);

  useEffect(() => {
    let active = true;

    getUserPreferences()
      .then((response) => {
        if (active) {
          setPreferences(response);
        }
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, []);

  const persistPreferences = async (nextPreferences: UserPreferences) => {
    setPreferences(nextPreferences);
    try {
      const response = await updateUserPreferences(nextPreferences);
      setPreferences(response);
    } catch {
      setPreferences(nextPreferences);
    }
  };

  const updateAccent = (accent: AccentPreference) =>
    void persistPreferences({ ...preferences, accent_preference: accent });

  const updateTranslationLocale = (translationLocale: string) =>
    void persistPreferences({ ...preferences, translation_locale: translationLocale as TranslationLocale });

  const updateView = (view: ViewPreference) =>
    void persistPreferences({ ...preferences, knowledge_view_preference: view });

  const updateReviewDepthPreset = (reviewDepthPreset: UserPreferences["review_depth_preset"]) =>
    void persistPreferences({ ...preferences, review_depth_preset: reviewDepthPreset });

  const updateShowTranslations = (showTranslationsByDefault: boolean) =>
    void persistPreferences({
      ...preferences,
      show_translations_by_default: showTranslationsByDefault,
    });

  const updateReviewToggle = <K extends keyof Pick<
    UserPreferences,
    | "enable_confidence_check"
    | "enable_word_spelling"
    | "enable_audio_spelling"
    | "show_pictures_in_questions"
  >>(
    key: K,
  ) =>
    void persistPreferences({
      ...preferences,
      [key]: !preferences[key],
    });

  return (
    <div className="mx-auto max-w-[46rem] pb-10 text-[#482060]">
      <section className="relative overflow-hidden rounded-[0.95rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(245,240,252,0.95))] px-4 py-4 shadow-[0_16px_30px_rgba(84,46,135,0.12)]">
        <div className="absolute left-0 top-0 h-full w-3 bg-[linear-gradient(180deg,#8a35ff,#3cc8de)]" />
        <div className="relative space-y-4">
          <div className="flex items-center justify-between">
            <Link href="/" className="text-2xl font-semibold text-[#6f42aa]">
              ←
            </Link>
            <h1 className="text-[1.9rem] font-semibold tracking-tight text-[#52277e]">Settings</h1>
            <span className="w-6" />
          </div>
          <p className="pl-1 text-sm leading-6 text-[#6f6386]">
            Personalize how learner cards sound, translate, and appear across the app.
          </p>
        </div>
      </section>

      <div className="mt-3 space-y-3 rounded-[0.95rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.90),rgba(246,241,252,0.93))] px-3 py-3 shadow-[0_12px_28px_rgba(84,46,135,0.10)]">
      <section className="space-y-5 rounded-[0.9rem] bg-white/94 px-4 py-4 shadow-[0_8px_18px_rgba(84,46,135,0.06)]">
        <h2 className="text-[2rem] font-semibold text-[#1bb9d4]">Learning</h2>
        <div className="space-y-4 text-lg font-semibold text-[#543971]">
          <div className="flex items-center justify-between">
            <span>English Level</span>
            <span>Fluent</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span>Preferred Accent</span>
            <div className="flex items-center gap-2">
              {([
                ["uk", "UK Accent"],
                ["us", "US Accent"],
                ["au", "AU Accent"],
              ] as const).map(([accent, label]) => (
                <button
                  key={accent}
                  type="button"
                  aria-label={label}
                  onClick={() => updateAccent(accent)}
                  className={`rounded-[0.7rem] px-3 py-2 text-sm font-semibold ${accentButtonClass(preferences.accent_preference === accent)}`}
                >
                  {accent.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span>Daily Goal</span>
            <span>30 mins/day</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Reminders</span>
            <span>08:30, 12:00</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Monthly Progress Report</span>
            <div className="rounded-[0.7rem] bg-[#efedf7] px-4 py-2 text-[#7a6794]">On</div>
          </div>
        </div>
      </section>

      <section className="space-y-5 rounded-[0.9rem] bg-white/94 px-4 py-4 shadow-[0_8px_18px_rgba(84,46,135,0.06)]">
        <h2 className="text-[2rem] font-semibold text-[#1bb9d4]">Translation</h2>
        <div className="space-y-4 text-lg font-semibold text-[#543971]">
          <div className="flex items-center justify-between">
            <label htmlFor="translation-language">Language</label>
            <select
              id="translation-language"
              value={preferences.translation_locale}
              onChange={(event) => updateTranslationLocale(event.target.value)}
              className="rounded-[0.7rem] bg-transparent text-right outline-none"
            >
              {SUPPORTED_TRANSLATION_LOCALES.map((locale) => (
                <option key={locale} value={locale}>
                  {TRANSLATION_LANGUAGE_LABELS[locale]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center justify-between">
            <span>Translate UI</span>
            <div className="rounded-[0.7rem] bg-[#efedf7] px-4 py-2 text-[#7a6794]">Off / On</div>
          </div>
          <div className="flex items-center justify-between">
            <span>Show Translations By Default</span>
            <button
              type="button"
              aria-label="Show translations by default"
              onClick={() => updateShowTranslations(!preferences.show_translations_by_default)}
              className={`rounded-[0.7rem] px-4 py-2 ${
                preferences.show_translations_by_default
                  ? "bg-[#38c7dd] text-white"
                  : "bg-[#efedf7] text-[#7a6794]"
              }`}
            >
              {preferences.show_translations_by_default ? "On" : "Off"}
            </button>
          </div>
        </div>
      </section>

      <section className="space-y-5 rounded-[0.9rem] bg-white/94 px-4 py-4 shadow-[0_8px_18px_rgba(84,46,135,0.06)]">
        <h2 className="text-[2rem] font-semibold text-[#1bb9d4]">Review Cards</h2>
        <div className="space-y-4 text-lg font-semibold text-[#543971]">
          <div className="flex items-center justify-between gap-2">
            <span>Review Depth</span>
            <div className="flex items-center gap-2">
              {([
                ["gentle", "Gentle"],
                ["balanced", "Balanced"],
                ["deep", "Deep"],
              ] as const).map(([preset, label]) => (
                <button
                  key={preset}
                  type="button"
                  aria-label={`${label} review depth`}
                  onClick={() => updateReviewDepthPreset(preset)}
                  className={`rounded-[0.7rem] px-3 py-2 text-sm font-semibold ${
                    preferences.review_depth_preset === preset
                      ? "bg-[#38c7dd] text-white"
                      : "bg-[#efedf7] text-[#7a6794]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span>Confidence Check</span>
            <button
              type="button"
              aria-label="Confidence check"
              onClick={() => updateReviewToggle("enable_confidence_check")}
              className={`rounded-[0.7rem] px-4 py-2 ${
                preferences.enable_confidence_check
                  ? "bg-[#38c7dd] text-white"
                  : "bg-[#efedf7] text-[#7a6794]"
              }`}
            >
              {preferences.enable_confidence_check ? "On" : "Off"}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span>Word Spelling</span>
            <button
              type="button"
              aria-label="Word spelling"
              onClick={() => updateReviewToggle("enable_word_spelling")}
              className={`rounded-[0.7rem] px-4 py-2 ${
                preferences.enable_word_spelling
                  ? "bg-[#38c7dd] text-white"
                  : "bg-[#efedf7] text-[#7a6794]"
              }`}
            >
              {preferences.enable_word_spelling ? "On" : "Off"}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span>Audio Spelling</span>
            <button
              type="button"
              aria-label="Audio spelling"
              onClick={() => updateReviewToggle("enable_audio_spelling")}
              className={`rounded-[0.7rem] px-4 py-2 ${
                preferences.enable_audio_spelling
                  ? "bg-[#38c7dd] text-white"
                  : "bg-[#efedf7] text-[#7a6794]"
              }`}
            >
              {preferences.enable_audio_spelling ? "On" : "Off"}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span>Pictures In Questions</span>
            <button
              type="button"
              aria-label="Pictures in questions"
              onClick={() => updateReviewToggle("show_pictures_in_questions")}
              className={`rounded-[0.7rem] px-4 py-2 ${
                preferences.show_pictures_in_questions
                  ? "bg-[#38c7dd] text-white"
                  : "bg-[#efedf7] text-[#7a6794]"
              }`}
            >
              {preferences.show_pictures_in_questions ? "On" : "Off"}
            </button>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span>Knowledge View</span>
            <div className="flex items-center gap-2">
              {([
                ["cards", "Cards View"],
                ["list", "List View"],
                ["tags", "Tags View"],
              ] as const).map(([view, label]) => (
                <button
                  key={view}
                  type="button"
                  aria-label={label}
                  onClick={() => updateView(view)}
                  className={`rounded-[0.7rem] px-3 py-2 text-sm font-semibold ${viewButtonClass(preferences.knowledge_view_preference === view)}`}
                >
                  {view === "cards" ? "Aa" : view === "list" ? "aa" : "AA"}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span>Challenge Types</span>
            <span>Change</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Word Examples</span>
            <span>Change</span>
          </div>
        </div>
      </section>

      <section className="space-y-5 rounded-[0.9rem] bg-white/94 px-4 py-4 shadow-[0_8px_18px_rgba(84,46,135,0.06)]">
        <h2 className="text-[2rem] font-semibold text-[#1bb9d4]">Data/Storage</h2>
        <div className="space-y-4 text-lg font-semibold text-[#543971]">
          <div className="flex items-center justify-between">
            <span>Video Background</span>
            <div className="rounded-[0.7rem] bg-[#38c7dd] px-4 py-2 text-white">On</div>
          </div>
          <div className="flex items-center justify-between">
            <span>Clear Cache</span>
            <button type="button" className="rounded-[0.7rem] bg-[#efedf7] px-4 py-2 text-[#7a6794]">
              Clear
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}
