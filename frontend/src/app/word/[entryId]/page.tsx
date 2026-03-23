"use client";

import { useParams } from "next/navigation";
import { KnowledgeEntryDetailPage } from "@/components/knowledge-entry-detail-page";

export default function WordEntryPage() {
  const params = useParams<{ entryId: string }>();

  return <KnowledgeEntryDetailPage entryType="word" entryId={params.entryId} />;
}
