"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { KnowledgeMapRangeDetail } from "@/components/knowledge-map-range-detail";

export default function KnowledgeMapRangePage() {
  const params = useParams<{ start?: string | string[] }>();
  const rawStart = Array.isArray(params?.start) ? params.start[0] : params?.start;
  const rangeStart = Number(rawStart);

  if (!Number.isInteger(rangeStart) || rangeStart <= 0) {
    return (
      <div className="mx-auto max-w-[46rem] rounded-[0.8rem] bg-[#f1f2f8] px-4 py-5 text-[#43235f]">
        <h2 className="text-[1.6rem] font-semibold tracking-tight text-[#502a7d]">
          Invalid Knowledge Range
        </h2>
        <p className="mt-2 text-sm leading-6 text-[#6b5d86]">
          This range link is not valid.
        </p>
        <Link href="/knowledge-map" className="mt-4 inline-flex text-sm font-semibold text-[#7c2cff]">
          Back to Full Knowledge Map
        </Link>
      </div>
    );
  }

  return <KnowledgeMapRangeDetail initialRangeStart={rangeStart} />;
}
