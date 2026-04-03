import { ImportJobDetailPage } from "@/components/import-job-detail-page";

type ImportJobDetailRouteProps = {
  params: Promise<{ jobId: string }>;
};

export default async function ImportJobDetailRoute({ params }: ImportJobDetailRouteProps) {
  const resolvedParams = await params;
  return <ImportJobDetailPage jobId={resolvedParams.jobId} />;
}
