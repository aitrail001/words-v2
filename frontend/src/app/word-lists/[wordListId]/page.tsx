import { WordListDetailPage } from "@/components/word-list-detail-page";

type WordListDetailRouteProps = {
  params: Promise<{ wordListId: string }>;
};

export default async function WordListDetailRoute({ params }: WordListDetailRouteProps) {
  const resolvedParams = await params;
  return <WordListDetailPage wordListId={resolvedParams.wordListId} />;
}
