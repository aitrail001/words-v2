"use client";

import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api-client";

type WordResult = {
  id: string;
  word: string;
  language: string;
  frequency_rank: number | null;
};

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<WordResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await apiClient.get<WordResult[]>(`/words/search?q=${query}`);
        setResults(data);
        setSearched(true);
      } catch (err) {
        console.error("Search failed:", err);
        setResults([]);
        setSearched(true);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 font-medium">Search Words</h3>
        <input
          type="text"
          placeholder="Search words..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2"
        />
        {loading && <p className="mt-2 text-sm text-gray-500">Searching...</p>}
        {searched && results.length === 0 && (
          <p className="mt-2 text-sm text-gray-500">No words found</p>
        )}
        {results.length > 0 && (
          <ul className="mt-4 space-y-2">
            {results.map((word) => (
              <li key={word.id} className="rounded border border-gray-200 p-2">
                <span className="font-medium">{word.word}</span>
                {word.frequency_rank && (
                  <span className="ml-2 text-sm text-gray-500">
                    (rank: {word.frequency_rank})
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
