"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";

type DueQueueItem = {
  item_id?: string;
  id?: string;
  card_type?: string;
  prompt?: {
    word?: string;
    definition?: string;
  };
  word?: string;
  definition?: string;
  meaning?: {
    definition?: string;
    word?: string | { word?: string };
  };
};

const getPromptWord = (item: DueQueueItem): string => {
  if (item.prompt?.word) return item.prompt.word;
  if (item.word) return item.word;
  if (typeof item.meaning?.word === "string") return item.meaning.word;
  if (item.meaning?.word && typeof item.meaning.word === "object" && item.meaning.word.word) {
    return item.meaning.word.word;
  }
  return "Unknown word";
};

const getPromptDefinition = (item: DueQueueItem): string => {
  if (item.prompt?.definition) return item.prompt.definition;
  if (item.definition) return item.definition;
  if (item.meaning?.definition) return item.meaning.definition;
  return "No definition available.";
};

export default function ReviewPage() {
  const router = useRouter();
  const [started, setStarted] = useState(false);
  const [cards, setCards] = useState<DueQueueItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);

  const startReview = async () => {
    setLoading(true);
    try {
      const dueCards = await apiClient.get<DueQueueItem[]>("/reviews/queue/due");
      setCards(dueCards);
      setCurrentIndex(0);
      setCompleted(false);
      setStarted(true);
    } catch (error) {
      console.error("Failed to start review:", error);
    } finally {
      setLoading(false);
    }
  };

  const submitRating = async (quality: number) => {
    if (currentIndex >= cards.length) return;

    const card = cards[currentIndex];
    const itemId = card.item_id ?? card.id;
    if (!itemId) return;
    setLoading(true);

    try {
      await apiClient.post(`/reviews/queue/${itemId}/submit`, {
        quality,
        time_spent_ms: 5000,
      });

      if (currentIndex + 1 < cards.length) {
        setCurrentIndex(currentIndex + 1);
      } else {
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

  if (!started) {
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
  const promptWord = getPromptWord(currentCard);
  const promptDefinition = getPromptDefinition(currentCard);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Review Session</h2>
        <span className="text-sm text-gray-500">
          Card {currentIndex + 1} of {cards.length}
        </span>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <p className="mb-2 text-2xl font-semibold">{promptWord}</p>
        <p className="mb-4 text-base text-gray-700">{promptDefinition}</p>
        <p className="text-sm text-gray-500">Type: {currentCard.card_type ?? "review"}</p>
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
