"use client";

import { useParams } from "next/navigation";
import { KnowledgeEntryDetailPage } from "@/components/knowledge-entry-detail-page";

export default function PhraseEntryPage() {
  const params = useParams<{ entryId: string }>();

  return <KnowledgeEntryDetailPage entryType="phrase" entryId={params.entryId} />;
}
