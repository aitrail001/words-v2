"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  getUserPreferences,
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
  const [preferences, setPreferences] = useState<UserPreferences>({
    accent_preference: "us",
    translation_locale: "zh-Hans",
    knowledge_view_preference: "cards",
  });

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
    void persistPreferences({ ...preferences, translation_locale: translationLocale });

  const updateView = (view: ViewPreference) =>
    void persistPreferences({ ...preferences, knowledge_view_preference: view });

  return (
    <div className="mx-auto max-w-[27rem] space-y-5 pb-10 text-[#482060]">
      <section className="rounded-[2rem] bg-white/92 px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div className="flex items-center justify-between">
          <Link href="/" className="text-2xl font-semibold text-[#6f42aa]">
            ←
          </Link>
          <h1 className="text-[2rem] font-semibold tracking-tight text-[#52277e]">Settings</h1>
          <span className="w-6" />
        </div>
      </section>

      <section className="space-y-5 rounded-[2rem] bg-white/94 px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
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

      <section className="space-y-5 rounded-[2rem] bg-white/94 px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <h2 className="text-[2rem] font-semibold text-[#1bb9d4]">Translation</h2>
        <div className="space-y-4 text-lg font-semibold text-[#543971]">
          <div className="flex items-center justify-between">
            <label htmlFor="translation-language">Language</label>
            <select
              id="translation-language"
              value={preferences.translation_locale === "zh-Hans" ? "Chinese" : preferences.translation_locale === "es" ? "Spanish" : preferences.translation_locale}
              onChange={(event) =>
                updateTranslationLocale(
                  event.target.value === "Chinese"
                    ? "zh-Hans"
                    : event.target.value === "Spanish"
                      ? "es"
                      : event.target.value,
                )
              }
              className="rounded-[0.7rem] bg-transparent text-right outline-none"
            >
              <option>Chinese</option>
              <option>Spanish</option>
              <option>Japanese</option>
            </select>
          </div>
          <div className="flex items-center justify-between">
            <span>Translate UI</span>
            <div className="rounded-[0.7rem] bg-[#efedf7] px-4 py-2 text-[#7a6794]">Off / On</div>
          </div>
          <div className="flex items-center justify-between">
            <span>Translate Review Cards</span>
            <div className="rounded-[0.7rem] bg-[#38c7dd] px-4 py-2 text-white">On</div>
          </div>
        </div>
      </section>

      <section className="space-y-5 rounded-[2rem] bg-white/94 px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <h2 className="text-[2rem] font-semibold text-[#1bb9d4]">Review Cards</h2>
        <div className="space-y-4 text-lg font-semibold text-[#543971]">
          <div className="flex items-center justify-between">
            <span>Sound Effects</span>
            <div className="rounded-[0.7rem] bg-[#38c7dd] px-4 py-2 text-white">On</div>
          </div>
          <div className="flex items-center justify-between">
            <span>Hard Word Alert</span>
            <div className="rounded-[0.7rem] bg-[#38c7dd] px-4 py-2 text-white">On</div>
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

      <section className="space-y-5 rounded-[2rem] bg-white/94 px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
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
  );
}
