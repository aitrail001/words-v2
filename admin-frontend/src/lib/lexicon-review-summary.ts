type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function firstString(values: unknown): string | null {
  return Array.isArray(values) ? values.map(asString).find((value) => value !== null) ?? null : null;
}

function firstExample(values: unknown): string | null {
  if (!Array.isArray(values)) return null;
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const sentence = asString((value as JsonRecord).sentence);
      if (sentence) return sentence;
    }
  }
  return null;
}

function countFormVariants(forms: unknown): number {
  const record = asRecord(forms);
  if (!record) return 0;
  let count = 0;
  for (const value of Object.values(record)) {
    if (Array.isArray(value)) {
      count += value.filter((item) => typeof item === "string" && item.trim()).length;
      continue;
    }
    if (value && typeof value === "object") {
      count += Object.values(value as JsonRecord).filter((item) => typeof item === "string" && item.trim()).length;
    }
  }
  return count;
}

export type DerivedReviewSummary = {
  senseCount: number;
  formVariantCount: number;
  confusableCount: number;
  provenanceSources: string[];
  primaryDefinition: string | null;
  primaryExample: string | null;
  phraseKind: string | null;
};

export function deriveReviewSummary(compiledPayload: Record<string, unknown>): DerivedReviewSummary {
  const payload = asRecord(compiledPayload) ?? {};
  const senses = Array.isArray(payload.senses) ? payload.senses.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
  const firstSense = senses[0] ?? null;
  const provenance = Array.isArray(payload.source_provenance)
    ? payload.source_provenance
        .map(asRecord)
        .filter((value): value is JsonRecord => value !== null)
        .map((value) => asString(value.source))
        .filter((value): value is string => value !== null)
    : [];

  return {
    senseCount: senses.length,
    formVariantCount: countFormVariants(payload.forms),
    confusableCount: Array.isArray(payload.confusable_words) ? payload.confusable_words.length : 0,
    provenanceSources: provenance,
    primaryDefinition: firstSense ? asString(firstSense.definition) : null,
    primaryExample: firstSense ? firstExample(firstSense.examples) : null,
    phraseKind: asString(payload.phrase_kind),
  };
}

export function derivePhraseDetails(entryType: string, payload: Record<string, unknown>): {
  phraseKind: string | null;
  definition: string | null;
  example: string | null;
  spanishDefinition: string | null;
} | null {
  if (entryType !== "phrase") return null;
  const record = asRecord(payload);
  const senses = Array.isArray(record?.senses) ? record.senses : [];
  const firstSense = asRecord(senses[0]);
  if (!firstSense) return null;

  const translations = asRecord(firstSense.translations);
  const spanish = asRecord(translations?.es);

  return {
    phraseKind: asString(record?.phrase_kind),
    definition: asString(firstSense.definition),
    example: firstExample(firstSense.examples),
    spanishDefinition: asString(spanish?.definition),
  };
}
