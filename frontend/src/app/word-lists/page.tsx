import { WordListsManager } from "@/components/word-lists-manager";

type WordListsPageProps = {
  searchParams?: Promise<{ list?: string | string[] }>;
};

export default async function WordListsPage({ searchParams }: WordListsPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const initialWordListId = Array.isArray(resolvedSearchParams.list)
    ? resolvedSearchParams.list[0] ?? null
    : resolvedSearchParams.list ?? null;

  return <WordListsManager initialWordListId={initialWordListId} />;
}
