"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";

type ReviewCard = {
  id: string;
  word_id: string;
  meaning_id: string;
  card_type: string;
};

type ReviewSession = {
  id: string;
  user_id: string;
  started_at: string;
  completed_at: string | null;
  cards_reviewed: number;
};

export default function ReviewPage() {
  const router = useRouter();
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [cards, setCards] = useState<ReviewCard[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);

  const startReview = async () => {
    setLoading(true);
    try {
      const newSession = await apiClient.post<ReviewSession>("/reviews/sessions");
      setSession(newSession);

      const dueCards = await apiClient.get<ReviewCard[]>("/reviews/due");
      setCards(dueCards);
      setCurrentIndex(0);
    } catch (error) {
      console.error("Failed to start review:", error);
    } finally {
      setLoading(false);
    }
  };

  const submitRating = async (quality: number) => {
    if (!session || currentIndex >= cards.length) return;

    const card = cards[currentIndex];
    setLoading(true);

    try {
      await apiClient.post(`/reviews/cards/${card.id}/submit`, {
        quality,
        time_spent_ms: 5000,
      });

      if (currentIndex + 1 < cards.length) {
        setCurrentIndex(currentIndex + 1);
      } else {
        // All cards reviewed, complete session
        await apiClient.post(`/reviews/sessions/${session.id}/complete`);
        setCompleted(true);
      }
    } catch (error) {
      console.error("Failed to submit review:", error);
    } finally {
      setLoading(false);
    }
  };

  if (completed) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-bold">Session Complete!</h2>
        <p className="text-gray-600">You reviewed {cards.length} cards.</p>
        <button
          onClick={() => router.push("/")}
          className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Back to Home
        </button>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-bold">Review Session</h2>
        <button
          onClick={startReview}
          disabled={loading}
          className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Starting..." : "Start Review"}
        </button>
      </div>
    );
  }

  if (cards.length === 0) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-bold">No Cards Due</h2>
        <p className="text-gray-600">You have no cards to review right now.</p>
        <button
          onClick={() => router.push("/")}
          className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Back to Home
        </button>
      </div>
    );
  }

  const currentCard = cards[currentIndex];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Review Session</h2>
        <span className="text-sm text-gray-500">
          Card {currentIndex + 1} of {cards.length}
        </span>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <p className="mb-4 text-lg">Card ID: {currentCard.id}</p>
        <p className="text-sm text-gray-500">Type: {currentCard.card_type}</p>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-700">How well did you know this?</p>
        <div className="flex gap-2">
          {[0, 1, 2, 3, 4, 5].map((quality) => (
            <button
              key={quality}
              onClick={() => submitRating(quality)}
              disabled={loading}
              className="flex-1 rounded-md border border-gray-300 px-4 py-2 hover:bg-gray-100 disabled:opacity-50"
            >
              {quality}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-500">0 = Didn't know, 5 = Perfect recall</p>
      </div>
    </div>
  );
}
