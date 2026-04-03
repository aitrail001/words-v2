import type { ImportJob } from "@/lib/imports-client";

const FILE_EXT_RE = /\.(epub|pdf|mobi|azw3)\s*$/i;
const PDFDRIVE_RE = /\(\s*pdfdrive(?:\.com)?\s*\)/gi;
const MULTISPACE_RE = /\s{2,}/g;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeImportTitle(rawValue: string | null | undefined): string {
  return (rawValue ?? "")
    .replace(PDFDRIVE_RE, " ")
    .replace(FILE_EXT_RE, "")
    .replace(MULTISPACE_RE, " ")
    .trim()
    .replace(/[._\-\s]+$/, "")
    .trim();
}

function stripTrailingAuthor(title: string, author: string | null | undefined): string {
  const normalizedAuthor = normalizeImportTitle(author);
  if (!normalizedAuthor) {
    return title;
  }

  const authorSuffixRe = new RegExp(`\\s+by\\s+${escapeRegExp(normalizedAuthor)}$`, "i");
  return title.replace(authorSuffixRe, "").trim();
}

export function getImportDisplayTitle(job: Pick<ImportJob, "source_title" | "source_author" | "source_filename">): string {
  const normalizedTitle = stripTrailingAuthor(normalizeImportTitle(job.source_title), job.source_author);
  if (normalizedTitle) {
    return normalizedTitle;
  }

  const normalizedFilename = stripTrailingAuthor(normalizeImportTitle(job.source_filename), job.source_author);
  return normalizedFilename || "Untitled EPUB";
}
