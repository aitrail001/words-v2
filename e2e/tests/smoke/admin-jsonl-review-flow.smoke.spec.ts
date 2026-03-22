import { expect, test } from "@playwright/test";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { injectAdminToken, registerAdminViaApi } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

const buildCompiledWordRow = (runId: string, word: string) => ({
  schema_version: "1.1.0",
  entry_id: `word:${word}:${runId}`,
  entry_type: "word",
  normalized_form: word,
  source_provenance: [{ source: "e2e-smoke", run_id: runId }],
  entity_category: "general",
  word,
  part_of_speech: ["noun"],
  cefr_level: "B1",
  frequency_rank: 100,
  phonetics: {
    us: { ipa: `/${word}/`, confidence: 0.99 },
    uk: { ipa: `/${word}/`, confidence: 0.98 },
    au: { ipa: `/${word}/`, confidence: 0.97 },
  },
  forms: {
    plural_forms: [`${word}s`],
    verb_forms: {},
    comparative: null,
    superlative: null,
    derivations: [],
  },
  senses: [
    {
      sense_id: `sense-${runId}-1`,
      definition: `a learner-facing definition for ${word}`,
      examples: [{ sentence: `The ${word} is visible.`, difficulty: "easy" }],
      translations: {
        "zh-Hans": { definition: `${word} 的定义`, usage_note: "常见义项", examples: [`这个${word}很明显。`] },
        es: { definition: `definicion de ${word}`, usage_note: "uso comun", examples: [`El ${word} es visible.`] },
        ar: { definition: `تعريف ${word}`, usage_note: "معنى شائع", examples: [`هذا ${word} واضح.`] },
        "pt-BR": { definition: `definicao de ${word}`, usage_note: "uso comum", examples: [`O ${word} esta visivel.`] },
        ja: { definition: `${word} の定義`, usage_note: "よくある意味", examples: [`その${word}が見える。`] },
      },
    },
  ],
  confusable_words: [],
  generated_at: "2026-03-21T00:00:00Z",
  snapshot_id: `snapshot-${runId}`,
});

const buildCompiledPhraseRow = (runId: string, phrase: string) => ({
  schema_version: "1.1.0",
  entry_id: `phrase:${runId}`,
  entry_type: "phrase",
  normalized_form: phrase,
  source_provenance: [{ source: "e2e-smoke", run_id: runId }],
  entity_category: "general",
  word: phrase,
  part_of_speech: ["idiom"],
  cefr_level: "B1",
  frequency_rank: 5000,
  forms: {
    plural_forms: [],
    verb_forms: {},
    comparative: null,
    superlative: null,
    derivations: [],
  },
  senses: [
    {
      sense_id: `phrase-sense-${runId}`,
      definition: `an idiomatic meaning for ${phrase}`,
      examples: [{ sentence: `${phrase}!`, difficulty: "easy" }],
    },
  ],
  confusable_words: [],
  generated_at: "2026-03-21T00:00:00Z",
  display_form: phrase,
  phrase_kind: "idiom",
  snapshot_id: `snapshot-${runId}`,
});

const buildCompiledWarningPhraseRow = (runId: string, phrase: string) => ({
  ...buildCompiledPhraseRow(runId, phrase),
  source_provenance: [],
  senses: [
    {
      sense_id: `phrase-sense-${runId}`,
      definition: `an idiomatic meaning for ${phrase}`,
      examples: [],
    },
  ],
});

test("@smoke admin can review compiled JSONL directly and materialize sidecar outputs", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-jsonl-review-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const normalized = `jsonl${uniqueSuffix.replace(/[^0-9a-z]/gi, "").toLowerCase()}`;
  const phrase = `break a leg ${normalized}`;
  const hostRootDir = path.join(process.cwd(), "..", "backend", "tmp_e2e", "jsonl-review");
  const backendRootDir = `/app/tmp_e2e/jsonl-review`;
  const hostDir = path.join(hostRootDir, normalized);
  const backendDir = `${backendRootDir}/${normalized}`;
  const compiledHostPath = path.join(hostDir, "words.enriched.jsonl");
  const reviewedHostDir = path.join(hostDir, "reviewed");
  const decisionsHostPath = path.join(reviewedHostDir, "review.decisions.jsonl");
  const outputHostDir = reviewedHostDir;
  const compiledBackendPath = `${backendDir}/words.enriched.jsonl`;
  const decisionsBackendPath = `${backendDir}/reviewed/review.decisions.jsonl`;
  const outputBackendDir = `${backendDir}/reviewed`;

  await mkdir(hostDir, { recursive: true });
  await rm(outputHostDir, { recursive: true, force: true });
  await rm(compiledHostPath, { force: true });
  await rm(decisionsHostPath, { force: true });

  const compiledJsonl = [
    JSON.stringify(buildCompiledWordRow(uniqueSuffix, normalized)),
    JSON.stringify(buildCompiledWarningPhraseRow(uniqueSuffix, phrase)),
  ].join("\n") + "\n";
  await writeFile(compiledHostPath, compiledJsonl, "utf-8");

  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/lexicon/jsonl-review`);
  await expect(page.getByTestId("lexicon-jsonl-review-page")).toBeVisible();

  await page.getByLabel("Artifact path").fill(compiledBackendPath);
  await page.getByLabel("Decision ledger path").fill(decisionsBackendPath);
  await page.getByLabel("Output directory").fill(outputBackendDir);
  await page.getByRole("button", { name: "Load Artifact" }).click();

  await expect(page.getByText(`Loaded ${path.basename(compiledBackendPath)}`)).toBeVisible();
  await expect(page.getByText("Risk first")).toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(`^${normalized}\\b`) })).toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(`^${phrase}\\b`) })).toBeVisible();
  await expect(page.getByText("missing_source_provenance").first()).toBeVisible();
  await expect(page.getByText(new RegExp(`an idiomatic meaning for ${phrase}`)).first()).toBeVisible();

  await expect(page.getByRole("heading", { name: phrase })).toBeVisible();
  await page.getByTestId("jsonl-review-decision-reason").fill("regen from smoke");
  await page.getByTestId("jsonl-review-reject-button").click();
  await page.getByTestId("jsonl-review-confirm-rejected-button").click();
  await expect(page.getByText(/Saved phrase:.* as rejected\./)).toBeVisible();
  await expect(page.getByRole("heading", { name: normalized })).toBeVisible();

  await page.getByTestId("jsonl-review-decision-reason").fill("approved in jsonl smoke");
  await page.getByTestId("jsonl-review-approve-button").click();
  await page.getByTestId("jsonl-review-confirm-approved-button").click();
  await expect(page.getByText(new RegExp(`Saved word:${normalized}:${uniqueSuffix} as approved\\.`))).toBeVisible();

  await page.getByRole("button", { name: "Materialize Reviewed Outputs" }).click();
  await expect(page.getByText(`${outputBackendDir}/approved.jsonl`)).toBeVisible();
  await expect(page.getByText(`${outputBackendDir}/rejected.jsonl`)).toBeVisible();
  await expect(page.getByText(`${outputBackendDir}/regenerate.jsonl`)).toBeVisible();

  const decisionsLines = (await readFile(decisionsHostPath, "utf-8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { entry_id: string; decision: string; decision_reason: string | null });
  expect(decisionsLines).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        entry_id: `word:${normalized}:${uniqueSuffix}`,
        decision: "approved",
        decision_reason: "approved in jsonl smoke",
      }),
      expect.objectContaining({
        entry_id: `phrase:${uniqueSuffix}`,
        decision: "rejected",
        decision_reason: "regen from smoke",
      }),
    ]),
  );

  const approvedLines = (await readFile(path.join(outputHostDir, "approved.jsonl"), "utf-8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { entry_id: string });
  expect(approvedLines).toEqual([
    expect.objectContaining({ entry_id: `word:${normalized}:${uniqueSuffix}` }),
  ]);

  const regenerateLines = (await readFile(path.join(outputHostDir, "regenerate.jsonl"), "utf-8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { entry_id: string; decision_reason: string | null });
  expect(regenerateLines).toEqual([
    expect.objectContaining({ entry_id: `phrase:${uniqueSuffix}`, decision_reason: "regen from smoke" }),
  ]);

  await rm(compiledHostPath, { force: true });
  await rm(decisionsHostPath, { force: true });
  await rm(outputHostDir, { recursive: true, force: true });
  await rm(hostDir, { recursive: true, force: true });
});
