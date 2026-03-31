# Learner Voice Playback and Audio Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add learner-facing word/phrase/definition/example playback plus real audio review prompts with same-day distractors, adjacent-frequency fallback, and relearn handoff into the canonical detail page.

**Architecture:** Extend learner-facing backend entry/review contracts with normalized voice payloads and deterministic MCQ distractor sourcing, then build one authenticated audio playback helper in the learner frontend that is reused by detail pages, learner tiles, and review cards. Keep routing canonical by sending relearn/lookup into the existing learner detail routes with review return context instead of building a second embedded detail UI.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js App Router, React 19, TypeScript, Jest, pytest, Playwright

---

### Task 1: Add failing backend tests for learner voice payloads and deterministic review distractors

**Files:**
- Modify: `backend/tests/test_words.py`
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`

- [ ] **Step 1: Write the failing learner voice payload test in `backend/tests/test_words.py`**

```python
async def test_get_word_enrichment_groups_voice_assets_for_entry_meanings_and_examples(
    self,
    client: AsyncClient,
    override_get_db,
):
    user = User(id=uuid.uuid4(), email="voice@example.com", password_hash="x")
    word = Word(
        id=uuid.uuid4(),
        word="bank",
        language="en",
        frequency_rank=20,
        phonetic="/bæŋk/",
    )
    meaning = Meaning(
        id=uuid.uuid4(),
        word_id=word.id,
        definition="The land alongside a river.",
        order_index=0,
    )
    example = MeaningExample(
        id=uuid.uuid4(),
        meaning_id=meaning.id,
        sentence="We sat on the river bank.",
        order_index=0,
    )

    entry_us = LexiconVoiceAsset(
        id=uuid.uuid4(),
        word_id=word.id,
        storage_policy_id=uuid.uuid4(),
        content_scope="word",
        locale="en_us",
        voice_role="female",
        provider="test",
        family="default",
        voice_id="voice-us-word",
        profile_key="default",
        audio_format="mp3",
        relative_path="word_bank/word/en_us/female-word.mp3",
        status="ready",
    )
    entry_uk = LexiconVoiceAsset(
        id=uuid.uuid4(),
        word_id=word.id,
        storage_policy_id=uuid.uuid4(),
        content_scope="word",
        locale="en_gb",
        voice_role="female",
        provider="test",
        family="default",
        voice_id="voice-uk-word",
        profile_key="default",
        audio_format="mp3",
        relative_path="word_bank/word/en_gb/female-word.mp3",
        status="ready",
    )
    definition_us = LexiconVoiceAsset(
        id=uuid.uuid4(),
        meaning_id=meaning.id,
        storage_policy_id=uuid.uuid4(),
        content_scope="definition",
        locale="en_us",
        voice_role="female",
        provider="test",
        family="default",
        voice_id="voice-us-definition",
        profile_key="default",
        audio_format="mp3",
        relative_path="word_bank/definition/en_us/female-definition.mp3",
        status="ready",
    )
    example_us = LexiconVoiceAsset(
        id=uuid.uuid4(),
        meaning_example_id=example.id,
        storage_policy_id=uuid.uuid4(),
        content_scope="example",
        locale="en_us",
        voice_role="female",
        provider="test",
        family="default",
        voice_id="voice-us-example",
        profile_key="default",
        audio_format="mp3",
        relative_path="word_bank/example/en_us/female-example.mp3",
        status="ready",
    )

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    word_result = MagicMock()
    word_result.scalar_one_or_none.return_value = word
    meanings_result = MagicMock()
    meanings_result.scalars.return_value.all.return_value = [meaning]
    examples_result = MagicMock()
    examples_result.scalars.return_value.all.return_value = [example]
    relations_result = MagicMock()
    relations_result.scalars.return_value.all.return_value = []
    runs_result = MagicMock()
    runs_result.scalars.return_value.all.return_value = []
    voice_assets_result = MagicMock()
    voice_assets_result.scalars.return_value.all.return_value = [
        entry_us,
        entry_uk,
        definition_us,
        example_us,
    ]

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        user_result,
        word_result,
        meanings_result,
        examples_result,
        relations_result,
        runs_result,
        voice_assets_result,
    ]
    override_get_db(mock_db)

    response = await client.get(f"/api/words/{word.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["voice_targets"]["entry"]["locales"]["us"]["playback_url"].startswith("/api/words/voice-assets/")
    assert data["voice_targets"]["entry"]["locales"]["uk"]["playback_url"].startswith("/api/words/voice-assets/")
    assert data["voice_targets"]["meanings"][0]["voice"]["locales"]["us"]["relative_path"] == "word_bank/definition/en_us/female-definition.mp3"
    assert data["voice_targets"]["meanings"][0]["examples"][0]["voice"]["locales"]["us"]["relative_path"] == "word_bank/example/en_us/female-example.mp3"
```

- [ ] **Step 2: Run the targeted backend payload test and verify it fails for the missing learner voice grouping**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_words.py -q`

Expected: FAIL with a missing `voice_targets` field or equivalent contract mismatch.

- [ ] **Step 3: Write the failing same-day distractor tests in `backend/tests/test_review_service.py`**

```python
@pytest.mark.asyncio
async def test_build_card_prompt_prefers_same_day_due_definitions_before_frequency_fallback():
    service = ReviewService(AsyncMock())
    target_meaning_id = uuid.uuid4()

    service._fetch_same_day_definition_distractors = AsyncMock(
        return_value=[
            "A financial institution that stores money.",
            "A raised pile of snow.",
            "A large mass of cloud.",
        ]
    )
    service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[
        "A long narrow table.",
    ])

    prompt = await service._build_card_prompt(
        review_mode=ReviewService.REVIEW_MODE_MCQ,
        source_text="bank",
        definition="The land alongside a river.",
        sentence=None,
        is_phrase_entry=False,
        distractor_seed="review",
        meaning_id=target_meaning_id,
        index=6,
        alternative_definitions=None,
    )

    assert prompt["prompt_type"] == "audio_to_definition"
    labels = [option["label"] for option in prompt["options"]]
    assert "A financial institution that stores money." in labels
    assert "A long narrow table." not in labels
    service._fetch_same_day_definition_distractors.assert_awaited_once()
    service._fetch_adjacent_definition_distractors.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_card_prompt_uses_adjacent_frequency_distractors_when_same_day_pool_is_small():
    service = ReviewService(AsyncMock())
    target_meaning_id = uuid.uuid4()

    service._fetch_same_day_definition_distractors = AsyncMock(
        return_value=["A financial institution that stores money."]
    )
    service._fetch_adjacent_definition_distractors = AsyncMock(
        return_value=[
            "A raised pile of snow.",
            "A large mass of cloud.",
        ]
    )

    prompt = await service._build_card_prompt(
        review_mode=ReviewService.REVIEW_MODE_MCQ,
        source_text="bank",
        definition="The land alongside a river.",
        sentence=None,
        is_phrase_entry=False,
        distractor_seed="review",
        meaning_id=target_meaning_id,
        index=6,
        alternative_definitions=None,
    )

    labels = [option["label"] for option in prompt["options"]]
    assert "A financial institution that stores money." in labels
    assert "A raised pile of snow." in labels
    assert "A large mass of cloud." in labels
    service._fetch_adjacent_definition_distractors.assert_awaited_once()
```

- [ ] **Step 4: Run the targeted review service test and verify it fails against the current random distractor path**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_review_service.py -q`

Expected: FAIL because the same-day and adjacent-frequency helper flow does not exist yet.

- [ ] **Step 5: Write the failing review API contract test for audio prompt playback data in `backend/tests/test_review_api.py`**

```python
def test_get_due_queue_items_returns_audio_prompt_with_playback_url(client, override_get_db):
    review_item = {
        "item": SimpleNamespace(
            id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
        ),
        "word": "bank",
        "definition": "The land alongside a river.",
        "review_mode": "mcq",
        "prompt": {
            "mode": "mcq",
            "prompt_type": "audio_to_definition",
            "stem": "Listen, then choose the best matching definition.",
            "question": "bank",
            "options": [
                {"option_id": "A", "label": "The land alongside a river.", "is_correct": True},
                {"option_id": "B", "label": "A financial institution.", "is_correct": False},
                {"option_id": "C", "label": "A mass of cloud.", "is_correct": False},
                {"option_id": "D", "label": "A pile of snow.", "is_correct": False},
            ],
            "audio_state": "ready",
            "audio": {
                "preferred_playback_url": "/api/words/voice-assets/test-asset/content",
                "locales": {
                    "us": {"playback_url": "/api/words/voice-assets/test-asset/content"}
                },
            },
        },
        "source_entry_type": "word",
        "source_entry_id": str(uuid.uuid4()),
        "detail": None,
        "schedule_options": [],
    }
    ...
    assert response.json()[0]["prompt"]["audio"]["preferred_playback_url"] == "/api/words/voice-assets/test-asset/content"
```

- [ ] **Step 6: Run the targeted review API test and verify it fails**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_review_api.py -q`

Expected: FAIL because the prompt schema does not yet carry explicit audio playback data.

---

### Task 2: Implement backend learner voice grouping and review audio/distractor contracts

**Files:**
- Modify: `backend/app/api/words.py`
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/services/review.py`
- Test: `backend/tests/test_words.py`
- Test: `backend/tests/test_review_service.py`
- Test: `backend/tests/test_review_api.py`

- [ ] **Step 1: Add learner voice response models in `backend/app/api/words.py`**

```python
class LearnerVoiceVariantResponse(BaseModel):
    playback_url: str
    relative_path: str
    locale: str
    voice_role: str
    audio_format: str
    status: str


class LearnerVoiceTargetResponse(BaseModel):
    preferred_locale: str | None = None
    preferred_playback_url: str | None = None
    locales: dict[str, LearnerVoiceVariantResponse] = {}


class LearnerMeaningVoiceResponse(BaseModel):
    meaning_id: str
    voice: LearnerVoiceTargetResponse | None = None
    examples: list[dict[str, Any]] = []
```

- [ ] **Step 2: Implement grouped learner voice serialization in `backend/app/api/words.py`**

```python
def _normalize_learner_locale(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"en_us", "us"}:
        return "us"
    if lowered in {"en_gb", "uk"}:
        return "uk"
    if lowered in {"en_au", "au"}:
        return "au"
    return lowered


def _voice_variant_response(asset: LexiconVoiceAsset) -> LearnerVoiceVariantResponse:
    return LearnerVoiceVariantResponse(
        playback_url=build_voice_asset_playback_url(asset),
        relative_path=asset.relative_path,
        locale=asset.locale,
        voice_role=asset.voice_role,
        audio_format=asset.audio_format,
        status=asset.status,
    )


def _group_learner_voice_targets(assets: list[LexiconVoiceAsset]) -> dict[str, Any]:
    entry_locales: dict[str, LearnerVoiceVariantResponse] = {}
    meaning_targets: dict[str, dict[str, Any]] = defaultdict(lambda: {"voice": None, "examples": {}})

    for asset in assets:
        locale_key = _normalize_learner_locale(asset.locale)
        if locale_key is None:
            continue
        variant = _voice_variant_response(asset)
        if asset.content_scope == "word" and asset.word_id:
            entry_locales.setdefault(locale_key, variant)
        elif asset.content_scope == "definition" and asset.meaning_id:
            bucket = meaning_targets[str(asset.meaning_id)]
            voice = bucket.get("voice") or {"locales": {}}
            voice["locales"].setdefault(locale_key, variant.model_dump())
            bucket["voice"] = voice
        elif asset.content_scope == "example" and asset.meaning_example_id and asset.meaning_id:
            bucket = meaning_targets[str(asset.meaning_id)]
            example_voice = bucket["examples"].setdefault(str(asset.meaning_example_id), {"locales": {}})
            example_voice["locales"].setdefault(locale_key, variant.model_dump())

    return {
        "entry": _finalize_voice_target(entry_locales),
        "meanings": _finalize_meaning_targets(meaning_targets),
    }
```

- [ ] **Step 3: Attach the grouped learner voice payload to the word detail response**

```python
return WordEnrichmentDetailResponse(
    ...,
    voice_assets=[_voice_asset_response(asset) for asset in voice_assets],
    voice_targets=_group_learner_voice_targets(voice_assets),
)
```

- [ ] **Step 4: Add explicit audio fields to review prompt schemas in `backend/app/api/reviews.py`**

```python
class ReviewPromptAudioVariant(BaseModel):
    playback_url: str
    locale: str
    relative_path: str | None = None


class ReviewPromptAudioPayload(BaseModel):
    preferred_playback_url: str | None = None
    preferred_locale: str | None = None
    locales: dict[str, ReviewPromptAudioVariant] = {}


class ReviewPrompt(BaseModel):
    ...
    audio: ReviewPromptAudioPayload | None = None
```

- [ ] **Step 5: Replace random global distractor helpers in `backend/app/services/review.py`**

```python
async def _fetch_same_day_definition_distractors(
    self,
    *,
    user_id: uuid.UUID,
    target_meaning_id: uuid.UUID,
    limit: int,
) -> list[str]:
    ...


async def _fetch_adjacent_definition_distractors(
    self,
    *,
    target_meaning_id: uuid.UUID,
    target_entry_type: str,
    limit: int,
) -> list[str]:
    ...


async def _fetch_same_day_entry_distractors(
    self,
    *,
    user_id: uuid.UUID,
    target_entry_id: uuid.UUID,
    target_entry_type: str,
    limit: int,
) -> list[str]:
    ...


async def _fetch_adjacent_entry_distractors(
    self,
    *,
    target_entry_id: uuid.UUID,
    target_entry_type: str,
    limit: int,
) -> list[str]:
    ...
```

- [ ] **Step 6: Thread user/entry context through `_build_card_prompt` and build explicit audio prompt payloads**

```python
prompt = await self._build_mandated_prompt(
    ...,
    audio=self._build_prompt_audio_payload(entry_voice_assets),
)
```

- [ ] **Step 7: Run the backend test files until they pass**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_words.py backend/tests/test_review_service.py backend/tests/test_review_api.py -q`

Expected: PASS with the new learner voice and review contract coverage.

- [ ] **Step 8: Commit the backend contract slice**

```bash
git add backend/app/api/words.py backend/app/api/reviews.py backend/app/services/review.py backend/tests/test_words.py backend/tests/test_review_service.py backend/tests/test_review_api.py
git commit -m "feat(backend): add learner voice payloads and review audio prompts"
```

---

### Task 3: Add the learner audio helper and detail-page/tile playback with persistent US/UK switching

**Files:**
- Create: `frontend/src/lib/learner-audio.ts`
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/components/knowledge-map-range-detail.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-map-range-detail.test.tsx`
- Modify: `frontend/src/lib/__tests__/knowledge-map-client.test.ts`

- [ ] **Step 1: Write the failing frontend tests for detail-page audio controls**

```tsx
it("renders US/UK accent controls and main meaning/example play buttons", async () => {
  mockedGetKnowledgeMapEntryDetail.mockResolvedValue({
    entry_type: "word",
    entry_id: "word-1",
    display_text: "bank",
    browse_rank: 20,
    status: "learning",
    pronunciation: "/bæŋk/",
    translation: "bank",
    primary_definition: "The land alongside a river.",
    meanings: [
      {
        id: "meaning-1",
        definition: "The land alongside a river.",
        translations: [],
        examples: [{ id: "example-1", sentence: "We sat on the river bank." }],
        voice: {
          preferred_locale: "us",
          preferred_playback_url: "/api/words/voice-assets/meaning-us/content",
          locales: {
            us: { playback_url: "/api/words/voice-assets/meaning-us/content", locale: "en_us", relative_path: "..." },
          },
        },
      },
    ],
    voice_targets: {
      entry: {
        preferred_locale: "us",
        preferred_playback_url: "/api/words/voice-assets/entry-us/content",
        locales: {
          us: { playback_url: "/api/words/voice-assets/entry-us/content", locale: "en_us", relative_path: "..." },
          uk: { playback_url: "/api/words/voice-assets/entry-uk/content", locale: "en_gb", relative_path: "..." },
        },
      },
      meanings: [],
    },
  } as any)

  render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />)

  expect(await screen.findByRole("button", { name: /us accent/i })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /uk accent/i })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /play word audio/i })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /play definition audio/i })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /play example audio/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the detail-page test and verify it fails**

Run: `pnpm --dir frontend test -- --runInBand src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: FAIL because the controls and grouped voice fields do not exist yet.

- [ ] **Step 3: Write the failing tile/range test for quick accent switching and playback**

```tsx
it("shows quick play and US/UK switching on the active learner tile", async () => {
  ...
  expect(await screen.findByRole("button", { name: /play bank audio/i })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /switch to uk accent/i })).toBeInTheDocument()
})
```

- [ ] **Step 4: Run the tile/range test and verify it fails**

Run: `pnpm --dir frontend test -- --runInBand src/components/__tests__/knowledge-map-range-detail.test.tsx`

Expected: FAIL because quick playback and accent toggle are not rendered yet.

- [ ] **Step 5: Create `frontend/src/lib/learner-audio.ts` with the shared authenticated playback helper**

```ts
import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";

export function useLearnerAudio() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlsRef = useRef(new Map<string, string>());
  const [loadingUrl, setLoadingUrl] = useState<string | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      for (const url of objectUrlsRef.current.values()) {
        URL.revokeObjectURL(url);
      }
    };
  }, []);

  const play = async (playbackUrl: string) => {
    setLoadingUrl(playbackUrl);
    let objectUrl = objectUrlsRef.current.get(playbackUrl);
    if (!objectUrl) {
      const response = await apiClient.getBlob(playbackUrl);
      objectUrl = URL.createObjectURL(response);
      objectUrlsRef.current.set(playbackUrl, objectUrl);
    }
    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    audioRef.current.src = objectUrl;
    await audioRef.current.play();
    setPlayingUrl(playbackUrl);
    setLoadingUrl(null);
  };

  return { play, loadingUrl, playingUrl };
}
```

- [ ] **Step 6: Extend `frontend/src/lib/knowledge-map-client.ts` with learner voice types**

```ts
export type LearnerVoiceVariant = {
  playback_url: string;
  locale: string;
  relative_path?: string | null;
};

export type LearnerVoiceTarget = {
  preferred_locale?: string | null;
  preferred_playback_url?: string | null;
  locales: Record<string, LearnerVoiceVariant>;
};
```

- [ ] **Step 7: Implement persistent US/UK switching and playback in `KnowledgeEntryDetailPage`**

```tsx
const QUICK_ACCENTS: Array<"us" | "uk"> = ["us", "uk"];

function resolvePreferredVoiceTarget(target: LearnerVoiceTarget | null | undefined, accent: "us" | "uk" | "au") {
  if (!target) return null;
  return (
    target.locales[accent] ??
    target.locales[accent === "us" ? "uk" : "us"] ??
    Object.values(target.locales)[0] ??
    null
  );
}
```

- [ ] **Step 8: Implement quick playback in `knowledge-map-range-detail.tsx`**

```tsx
<button
  type="button"
  aria-label={`Play ${activeEntry.display_text} audio`}
  onClick={() => void play(resolvedVoice.playback_url)}
>
  Play
</button>
```

- [ ] **Step 9: Run the frontend unit tests until they pass**

Run: `pnpm --dir frontend test -- --runInBand src/components/__tests__/knowledge-entry-detail-page.test.tsx src/components/__tests__/knowledge-map-range-detail.test.tsx src/lib/__tests__/knowledge-map-client.test.ts`

Expected: PASS with new learner voice UI coverage.

- [ ] **Step 10: Commit the learner audio UI slice**

```bash
git add frontend/src/lib/learner-audio.ts frontend/src/lib/knowledge-map-client.ts frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/components/knowledge-map-range-detail.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx frontend/src/components/__tests__/knowledge-map-range-detail.test.tsx frontend/src/lib/__tests__/knowledge-map-client.test.ts
git commit -m "feat(frontend): add learner detail and tile voice playback"
```

---

### Task 4: Replace the dummy review audio UI and route relearn into the full detail page

**Files:**
- Modify: `frontend/src/app/review/page.tsx`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/app/word/[entryId]/page.tsx`
- Modify: `frontend/src/app/phrase/[entryId]/page.tsx`

- [ ] **Step 1: Write the failing review-page tests for real audio replay and relearn handoff**

```tsx
it("plays and replays audio_to_definition prompts from prompt audio payload", async () => {
  mockGet.mockResolvedValue([
    {
      id: "state-audio",
      queue_item_id: "state-audio",
      word: "bank",
      definition: "The land alongside a river.",
      review_mode: "mcq",
      prompt: {
        mode: "mcq",
        prompt_type: "audio_to_definition",
        stem: "Listen, then choose the best matching definition.",
        question: "bank",
        options: [
          { option_id: "A", label: "The land alongside a river.", is_correct: true },
          { option_id: "B", label: "A financial institution.", is_correct: false },
          { option_id: "C", label: "A mass of cloud.", is_correct: false },
          { option_id: "D", label: "A pile of snow.", is_correct: false },
        ],
        audio_state: "ready",
        audio: {
          preferred_playback_url: "/api/words/voice-assets/audio-1/content",
          locales: {
            us: { playback_url: "/api/words/voice-assets/audio-1/content", locale: "en_us" },
          },
        },
      },
      detail: { entry_type: "word", entry_id: "word-1", display_text: "bank", meanings: [], audio_state: "ready" },
      schedule_options: [],
    },
  ] as never)

  render(<ReviewPage />)
  fireEvent.click(await screen.findByRole("button", { name: /start review/i }))

  expect(await screen.findByRole("button", { name: /play audio/i })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: /play again/i })).toBeInTheDocument()
})


it("offers open detail page on relearn and preserves return to review", async () => {
  ...
  expect(await screen.findByRole("link", { name: /open full word details/i })).toHaveAttribute(
    "href",
    expect.stringContaining("/word/word-4?return_to=review"),
  )
})
```

- [ ] **Step 2: Run the review-page tests and verify they fail**

Run: `pnpm --dir frontend test -- --runInBand src/app/review/__tests__/page.test.tsx`

Expected: FAIL because replay and full-detail handoff do not exist yet.

- [ ] **Step 3: Replace the dummy `Play audio` button in `frontend/src/app/review/page.tsx` with the shared audio helper**

```tsx
const { play, loadingUrl, playingUrl } = useLearnerAudio();
const promptAudioUrl = prompt?.audio?.preferred_playback_url ?? null;

{prompt?.prompt_type === "audio_to_definition" && promptAudioUrl ? (
  <div className="mb-4 flex justify-center gap-3">
    <button
      type="button"
      onClick={() => void play(promptAudioUrl)}
      className="rounded-full bg-cyan-500 px-5 py-4 text-sm font-semibold text-white"
    >
      {loadingUrl === promptAudioUrl ? "Loading..." : "Play audio"}
    </button>
    <button
      type="button"
      onClick={() => void play(promptAudioUrl)}
      className="rounded-full border border-cyan-300 px-5 py-4 text-sm font-semibold text-cyan-700"
    >
      Play again
    </button>
  </div>
) : null}
```

- [ ] **Step 4: Replace the stripped relearn dead-end with full-detail handoff**

```tsx
const detailHref = revealState?.detail
  ? `${revealState.detail.entry_type === "word" ? "/word" : "/phrase"}/${revealState.detail.entry_id}?return_to=review`
  : null;

{detailHref ? (
  <Link
    href={detailHref}
    className="block w-full rounded-md border border-slate-300 px-4 py-2 text-center text-slate-800"
  >
    Open full word details
  </Link>
) : null}
```

- [ ] **Step 5: Add review return affordance in `KnowledgeEntryDetailPage`**

```tsx
const searchParams = typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
const launchedFromReview = searchParams?.get("return_to") === "review";
...
{launchedFromReview ? (
  <button
    type="button"
    onClick={() => router.push("/review")}
    className="rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white"
  >
    Back to review
  </button>
) : null}
```

- [ ] **Step 6: Run the review frontend tests until they pass**

Run: `pnpm --dir frontend test -- --runInBand src/app/review/__tests__/page.test.tsx src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS with audio replay and relearn handoff coverage.

- [ ] **Step 7: Commit the review frontend slice**

```bash
git add frontend/src/app/review/page.tsx frontend/src/app/review/__tests__/page.test.tsx frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/app/word/[entryId]/page.tsx frontend/src/app/phrase/[entryId]/page.tsx
git commit -m "feat(frontend): add learner audio review and detail handoff"
```

---

### Task 5: Add E2E coverage, update project status, and run full verification

**Files:**
- Modify: `e2e/tests/smoke/user-knowledge-map.smoke.spec.ts`
- Modify: `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts`
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Add a learner detail playback smoke in `e2e/tests/smoke/user-knowledge-map.smoke.spec.ts`**

```ts
test("user can open learner detail and see accent/audio controls", async ({ page }) => {
  await seedKnowledgeMapFixture();
  await page.goto("/word/word-bank");
  await expect(page.getByRole("button", { name: /us accent/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /uk accent/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /play word audio/i })).toBeVisible();
});
```

- [ ] **Step 2: Add a review audio smoke in `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts`**

```ts
test("audio_to_definition uses four choices and exposes relearn detail handoff", async ({ page }) => {
  await seedReviewAudioPromptFixture();
  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();
  await expect(page.getByRole("button", { name: /play audio/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /^A /i })).toBeVisible();
  await expect(page.getByRole("button", { name: /^B /i })).toBeVisible();
  await expect(page.getByRole("button", { name: /^C /i })).toBeVisible();
  await expect(page.getByRole("button", { name: /^D /i })).toBeVisible();
});
```

- [ ] **Step 3: Run the targeted E2E smokes locally**

Run: `pnpm --dir e2e test -- tests/smoke/user-knowledge-map.smoke.spec.ts tests/smoke/user-review-prompt-families.smoke.spec.ts --project=chromium`

Expected: PASS.

- [ ] **Step 4: Update `docs/status/project-status.md` with fresh evidence**

```md
| Review + learner voice playback | DONE | Learner detail playback + audio review + deterministic distractors | Learner detail pages now play entry/definition/example audio with persisted US/UK switching, review audio prompts now replay real entry audio with same-day MCQ distractors and adjacent-frequency fallback, and relearn routes into the canonical detail page with return-to-review flow. | `backend/app/api/words.py`, `backend/app/services/review.py`, `frontend/src/components/knowledge-entry-detail-page.tsx`, `frontend/src/app/review/page.tsx`, `backend/tests/test_words.py`, `backend/tests/test_review_service.py`, `frontend/src/app/review/__tests__/page.test.tsx`, `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts` | Maintain and widen phrase/voice coverage only with stable fixtures |
```

- [ ] **Step 5: Run the full verification set for this slice**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_words.py backend/tests/test_review_service.py backend/tests/test_review_api.py -q`

Expected: PASS

Run: `pnpm --dir frontend test -- --runInBand src/components/__tests__/knowledge-entry-detail-page.test.tsx src/components/__tests__/knowledge-map-range-detail.test.tsx src/app/review/__tests__/page.test.tsx`

Expected: PASS

Run: `pnpm --dir frontend exec eslint src/components/knowledge-entry-detail-page.tsx src/components/knowledge-map-range-detail.tsx src/app/review/page.tsx src/lib/learner-audio.ts --max-warnings=0`

Expected: PASS

Run: `pnpm --dir e2e test -- tests/smoke/user-knowledge-map.smoke.spec.ts tests/smoke/user-review-prompt-families.smoke.spec.ts --project=chromium`

Expected: PASS

- [ ] **Step 6: Commit docs and verification updates**

```bash
git add e2e/tests/smoke/user-knowledge-map.smoke.spec.ts e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts docs/status/project-status.md
git commit -m "test(e2e): cover learner voice playback and audio review"
```
