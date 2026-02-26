# Full Rebuild Plan — Words-Codex v2

**Status**: IN_PROGRESS
**Date**: 2026-02-26
**Approach**: Vertical slices — each phase delivers a working feature top-to-bottom (models + API + frontend + tests)
**Stack**: FastAPI + SQLAlchemy 2.0 + PostgreSQL 15 + Redis 7 + Celery + Next.js 16 + React 19 + TypeScript + Tailwind CSS 4

---

## Phase 0: Project Foundation

**Goal**: Runnable skeleton — `docker-compose up` gives you a working backend + frontend with health checks.

### Deliverables
- `docker-compose.yml` (from reference, with Postgres, Redis, backend, frontend)
- Backend skeleton: FastAPI app, Pydantic settings (from `config.reference.py`), DB connection, Alembic setup
- Frontend skeleton: Next.js 16 App Router, Tailwind CSS 4, API client, Zustand store shell
- Shared: `.env.example`, `scripts/init-db.sql`
- CI: GitHub Actions — lint + test on push
- Rate limiting middleware (FastAPI, from day one — lesson learned)
- Structured logging (JSON in prod, readable in dev)
- Documentation structure (`docs/` folders + README)

### Models
None yet — just the DB connection and Alembic config.

### Endpoints
- `GET /api/health` — backend health check (DB + Redis connectivity)

### Frontend
- App shell with layout, Zustand provider, API client configured
- Health check page (confirms backend connectivity)

### Tests
- Backend: health endpoint, config loading, DB connection
- Frontend: app renders, API client configured

### Acceptance Criteria
- `docker-compose up -d` starts all services
- `curl localhost:8000/api/health` returns `{"status": "ok"}`
- `localhost:3000` renders the app shell
- `alembic upgrade head` runs without error
- CI pipeline passes

### Risks
- LOW: Docker networking between services

---

## Phase 1: Auth + Core Vocabulary Models

**Goal**: Users can register, log in, and browse/search words with their meanings.

### Deliverables
- JWT auth with refresh tokens (register, login, refresh, me, logout)
- Core vocabulary models + migrations
- Word search and lookup endpoints
- Frontend auth flow (login, register, protected routes)
- Frontend word search page

### Models
- `users` — email, password_hash, role, tier, settings, is_active
- `words` — word, language, phonetic, frequency_rank, word_forms
- `meanings` — word_id, definition, part_of_speech, example_sentence, order_index
- `translations` — meaning_id, language, translation

### Endpoints
- `POST /api/auth/register` — create account
- `POST /api/auth/login` — get JWT + refresh token
- `POST /api/auth/refresh` — refresh JWT
- `GET /api/auth/me` — current user profile
- `POST /api/auth/logout` — invalidate refresh token
- `GET /api/words/search?q=` — search words (prefix match + full-text)
- `GET /api/words/{id}` — word detail with all meanings
- `GET /api/words/{id}/meanings` — meanings for a word
- `POST /api/words/lookup` — lookup word, auto-create from Dictionary API if not found

### Frontend
- Login / Register pages
- Auth context (Zustand store, JWT in httpOnly cookie or memory)
- Protected route wrapper
- Word search page with results
- Word detail page (meanings, translations, phonetic)

### Tests
- Backend: auth flow (register → login → refresh → me), password hashing, JWT expiry, word CRUD, search, Dictionary API integration (mocked)
- Frontend: auth forms, protected routes, search UI

### Acceptance Criteria
- User can register, log in, search for "bank", see multiple meanings
- JWT refresh works transparently
- Invalid credentials return proper errors
- Word lookup auto-fetches from Dictionary API when not in DB

### Dependencies
- Phase 0 (infrastructure)

### Risks
- LOW: Dictionary API rate limits (free tier)
- MEDIUM: JWT refresh token storage strategy (httpOnly cookie vs memory)

---

## Phase 2: Word Lists + ePub Import

**Goal**: Users can upload an ePub, extract vocabulary, review the word list, and save it.

### Deliverables
- Celery worker setup with Redis broker
- ePub parsing on backend (ebooklib + spaCy NLP)
- Content hash deduplication (SHA-256)
- Chunked processing for large imports (>500 words = background job)
- Word list CRUD
- Frontend import flow with real progress (WebSocket/SSE)

### Models
- `books` — content_hash (unique), title, author, language, word_count, file_path
- `book_caches` — book_id, processing_version, processed_data (JSON)
- `word_lists` — user_id, name, description, source_type, book_id
- `word_list_items` — word_list_id, word_id, context_sentence, frequency_count, variation_data
- `word_list_import_jobs` — user_id, book_id, status, progress fields, error tracking

### Endpoints
- `POST /api/word-lists/import` — upload ePub, start import
- `GET /api/word-lists/import/{job_id}` — job status + progress
- `GET /api/word-lists/` — user's word lists
- `GET /api/word-lists/{id}` — word list detail with items
- `POST /api/word-lists/{id}/items` — add words to list
- `DELETE /api/word-lists/{id}/items/{item_id}` — remove word from list
- `DELETE /api/word-lists/{id}` — delete word list
- `GET /api/nlp/lemmatize` — lemmatize text (spaCy)

### Frontend
- ePub upload page (drag & drop)
- Import progress (real-time via SSE, not polling — lesson learned)
- Word list review page (frequency-sorted, select/deselect words)
- Word list management page (list of lists)
- Zustand store for import state (not sessionStorage — lesson learned)

### Tests
- Backend: ePub parsing, NLP pipeline, content hash dedup, chunked processing, Celery task execution, import job state machine
- Frontend: upload flow, progress display, word selection

### Acceptance Criteria
- Upload a real ePub → see extracted vocabulary sorted by frequency
- Re-upload same ePub → cache hit, instant results
- Large import (>500 words) runs as background job with real progress
- Import can be interrupted and resumed
- Word list saved with context sentences

### Dependencies
- Phase 1 (auth + words)

### Risks
- MEDIUM: spaCy model size in Docker image (~500MB)
- MEDIUM: Large ePub memory usage (lesson learned — chunk processing)
- LOW: ePub format variations (ebooklib handles most)

---

## Phase 3: SM-2 Review System

**Goal**: Users can add meanings to their learning queue and review them with spaced repetition.

### Deliverables
- SM-2 algorithm integration (from `spaced_repetition.py`)
- Learning queue management
- Review session with interleaved card types
- Review statistics

### Models
- `user_meanings` — user_id, meaning_id, SM-2 fields (ease_factor, interval_days, repetitions, next_review), status, review_count, correct_count
- `review_history` — user_id, meaning_id, quality (0-5), review_type, response_time_ms

### Endpoints
- `POST /api/learning/add` — add meaning(s) to learning queue
- `GET /api/learning/queue` — user's learning queue (with filters)
- `DELETE /api/learning/{id}` — remove from queue
- `GET /api/review/due` — due items for review (sorted, limited)
- `POST /api/review/submit` — submit review (quality 0-5), returns SM-2 result
- `GET /api/review/stats` — review statistics (streak, mastery counts, due counts)
- `GET /api/review/history` — review history with filters

### Frontend
- "Add to learning" button on word detail / word list pages
- Learning queue page (all items, status filters)
- Review session page:
  - Card types: word→definition, definition→word, fill-in-the-blank
  - Show/reveal interaction
  - Quality rating (0-5 or simplified)
  - Session summary (cards reviewed, accuracy)
- Dashboard with review stats (due today, streak, mastery progress)

### Tests
- Backend: SM-2 calculations (edge cases: first review, reset on fail, mastery threshold), queue operations, due item sorting, review submission, stats aggregation
- Frontend: review session flow, card interactions, stats display

### Acceptance Criteria
- Add "bank (financial)" to queue → appears in due items after interval
- Review with quality 5 → interval increases, ease factor adjusts
- Review with quality 1 → resets to interval 1
- Interleaved card types in review session
- Stats show accurate due counts and mastery progress

### Dependencies
- Phase 1 (auth + words/meanings)

### Risks
- LOW: SM-2 algorithm is proven (91 lines, well-tested)
- MEDIUM: Review session UX (card type transitions, keyboard shortcuts)

---

## Phase 4: Concept Learning (Synsets + R/U/L)

**Goal**: Words are grouped into concepts via WordNet synsets. Users learn concepts with Recognition/Usage/Listening dimensions.

### Deliverables
- WordNet synset integration (NLTK)
- Concept pack assembly (core lemmas, contrasts, phrases)
- R/U/L mastery tracking per concept
- Concept review cards

### Models
- `synsets` — wn_synset (unique), pos, gloss, difficulty_score, path_order
- `synset_lemmas` — synset_id, word_id, lemma_text, lemma_rank, is_anchor
- `synset_edges` — from_synset_id, to_synset_id, relation_type, weight
- `synset_cluster_packs` — synset_id, version, core_json, contrast_json, phrases_json
- `concept_nodes` — synset_id, concept_key, canonical_label, definitions, difficulty
- `concept_expressions` — concept_id, word_id, expression_text, is_primary
- `user_synset_mastery` — user_id, synset_id, SM-2 fields + recognition_score, usage_score, listening_score

### Endpoints
- `GET /api/concepts/next` — next concept to learn (based on user's word list + mastery)
- `POST /api/concepts/{id}/start` — begin learning a concept
- `GET /api/concepts/{id}` — concept detail (pack: core, contrast, phrases)
- `POST /api/concepts/{id}/review` — submit concept review (updates R/U/L scores)
- `GET /api/concepts/mastery` — user's concept mastery overview

### Frontend
- Concept learning page (shows core lemmas, contrasts, example usage)
- Concept review cards (integrated into review session from Phase 3)
- Mastery dashboard (R/U/L dimension visualization per concept)

### Tests
- Backend: WordNet integration, concept pack assembly, R/U/L score updates, concept ordering
- Frontend: concept learning UI, mastery visualization

### Acceptance Criteria
- Looking up "happy" shows the synset with "glad", "joyful" as related lemmas
- Concept pack includes contrasts ("happy" vs "content" vs "ecstatic")
- R/U/L scores update independently based on card type
- Concept cards interleave with meaning cards in review session

### Dependencies
- Phase 3 (review system)

### Risks
- MEDIUM: WordNet data quality (some synsets are sparse)
- MEDIUM: Concept pack assembly complexity (choosing good contrasts)
- LOW: NLTK WordNet download in Docker

---

## Phase 5: AI Integrations (TTS + Images + LLM)

**Goal**: Multi-provider AI for pronunciation audio, vocabulary images, and LLM-powered features.

### Deliverables
- Multi-provider TTS abstraction (adapter pattern)
- Multi-provider image generation abstraction
- Multi-provider LLM abstraction
- Media caching (don't regenerate existing audio/images)
- Celery tasks for async media generation

### Models
- `audio_cache` — word, audio_type, provider, voice_id, file_path
- `image_cache` — word, meaning_id, provider, style, prompt, file_path
- `media_generation_jobs` — job_type, status, priority, params, result

### Endpoints
- `POST /api/audio/generate` — generate TTS audio (word, definition, or example)
- `GET /api/audio/{id}` — serve cached audio file
- `POST /api/images/generate` — generate vocabulary image
- `GET /api/images/{id}` — serve cached image
- `GET /api/media/jobs` — media generation job status

### Frontend
- Audio playback button on word/meaning cards
- Image display on meaning cards
- Loading states for async generation
- Provider selection in settings (if premium)

### Tests
- Backend: provider abstractions (mocked), cache hit/miss, Celery task execution, file storage
- Frontend: audio playback, image display, loading states

### Acceptance Criteria
- Click play on "bank" → TTS audio plays (cached on second play)
- Image generated for "river bank" meaning → displayed on card
- Provider swap (e.g., Google TTS → Azure) works without code changes
- Failed generation retries with fallback provider

### Dependencies
- Phase 1 (words/meanings)
- Phase 0 (Celery setup from Phase 2)

### Risks
- HIGH: API costs (TTS + image generation at scale)
- MEDIUM: Provider API changes/downtime
- LOW: Audio file format compatibility

---

## Phase 6: Lexicon Enrichment Pipeline

**Goal**: Automated word enrichment: WordNet → Dictionary API → Datamuse → LLM → human curation.

### Deliverables
- Multi-stage enrichment pipeline (Celery tasks)
- Hybrid frequency ranking (COCA → wordfreq → Datamuse)
- Phrase detection and linking
- Curation queue for unresolved words
- LLM-based enrichment with generate-then-validate pattern

### Models
- `meaning_examples` — meaning_id, sentence, source, confidence
- `meaning_phrases` — meaning_id, phrase_id (M:N link)
- `word_relations` — word_id, meaning_id, relation_type, related_word, confidence
- `phrases` — phrase, language, phrase_type (idiom, phrasal_verb, collocation)
- `phrase_meanings` — phrase_id, definition, example_sentence
- `lexicon_enrichment_jobs` — word_id, phase, status, priority, retry tracking
- `lexicon_enrichment_runs` — job_id, provider/model info, outputs, verdict, cost tracking
- `lexicon_curation_items` — word, reason, status, resolution_note

### Endpoints
- `POST /api/lexicon/enrich/{word_id}` — trigger enrichment for a word
- `GET /api/lexicon/enrichment-status/{word_id}` — enrichment progress
- `GET /api/lexicon/curation-queue` — items needing human review
- `POST /api/lexicon/curation/{id}/resolve` — resolve a curation item
- `GET /api/words/{id}/relations` — word relations (synonyms, antonyms, etc.)
- `GET /api/words/{id}/phrases` — phrases containing this word

### Frontend
- Enriched word detail (examples, relations, phrases)
- Enrichment status indicator on words

### Tests
- Backend: enrichment pipeline stages, frequency ranking, phrase detection, curation workflow, LLM mocking
- Frontend: enriched word display

### Acceptance Criteria
- New word triggers enrichment: WordNet → Dictionary API → Datamuse → (optional) LLM
- Frequency rank populated via hybrid strategy
- Unknown words land in curation queue
- LLM enrichment tracked with cost/token metrics

### Dependencies
- Phase 1 (words/meanings)
- Phase 5 (LLM abstraction)

### Risks
- MEDIUM: LLM enrichment costs (batch carefully)
- MEDIUM: Data quality from automated enrichment
- LOW: External API rate limits

---

## Phase 7: Listening Practice

**Goal**: Users practice recognizing vocabulary in spoken English.

### Deliverables
- Listening items linked to synsets
- TTS-generated audio for listening exercises
- Listening review cards integrated into review session
- Listening score (L dimension) updates

### Models
- `concept_listening_items` — synset_id, audio_url, transcript, difficulty, item_type
- `user_concept_listening_reviews` — user_id, listening_item_id, synset_id, quality, response_time_ms

### Endpoints
- `GET /api/listening/concepts/{synset_id}/items` — listening items for a concept
- `POST /api/listening/submit` — submit listening review
- `GET /api/listening/due` — due listening items

### Frontend
- Listening practice page (play audio → identify meaning)
- Listening cards in review session (interleaved with other types)
- Listening score in mastery dashboard

### Tests
- Backend: listening item generation, review submission, L-score updates
- Frontend: audio playback, answer submission

### Acceptance Criteria
- Listening card plays audio → user identifies the meaning
- L-score updates independently from R and U scores
- Listening cards interleave with other review types

### Dependencies
- Phase 4 (concepts/synsets)
- Phase 5 (TTS)

### Risks
- LOW: Audio quality varies by TTS provider
- LOW: Difficulty calibration for listening items

---

## Phase 8: Stories + Podcasts

**Goal**: AI-generated stories and podcasts using the user's vocabulary words.

### Deliverables
- Story generation (LLM) with vocabulary word integration
- Story versioning
- Podcast generation (multi-voice TTS dialogue)
- Podcast settings (host count, voices, style)

### Models
- `stories` — user_id, title, content, cefr_level, vocabulary_words, audio/image paths
- `story_versions` — story_id, version_number, content, audio_path
- `podcast_versions` — story_id, version_number, transcript, audio_path, hosts, segments
- `podcast_settings` — user_id, host_count, host_voices, style

### Endpoints
- `POST /api/stories/generate` — generate story from vocabulary words
- `GET /api/stories/` — user's stories
- `GET /api/stories/{id}` — story detail with versions
- `POST /api/stories/{id}/podcast` — generate podcast from story
- `GET /api/stories/{id}/podcast/{version}` — podcast detail
- `PUT /api/stories/podcast-settings` — update podcast preferences

### Frontend
- Story generation page (select words, CEFR level, generate)
- Story reader (text + audio playback)
- Podcast player (segmented playback, transcript view)
- Podcast settings page

### Tests
- Backend: story generation (LLM mocked), podcast generation, versioning
- Frontend: story reader, podcast player

### Acceptance Criteria
- Select 5 vocabulary words → generate a story at B1 level
- Story uses all selected words in context
- Generate podcast from story → multi-voice audio with transcript
- Story/podcast versions tracked

### Dependencies
- Phase 5 (LLM + TTS)
- Phase 3 (learning queue — vocabulary word selection)

### Risks
- HIGH: LLM generation costs (stories are long prompts)
- MEDIUM: Multi-voice TTS synchronization
- MEDIUM: Story quality consistency

---

## Phase 9: Admin Panel

**Goal**: Admin frontend for user management, content curation, and system monitoring.

### Deliverables
- Admin frontend (Next.js on port 3001)
- RBAC enforcement (user/admin/superadmin)
- Audit logging on all admin actions
- Dashboard with system metrics
- Content curation tools

### Models
- `audit_log` — action, resource_type, resource_id, user_id, changes, ip_address
- `app_settings` — category, key, value, value_type, description

### Endpoints
- `GET /api/admin/dashboard` — system metrics (users, words, reviews, jobs)
- `GET /api/admin/users` — user list with filters
- `PUT /api/admin/users/{id}` — update user (role, tier, active status)
- `GET /api/admin/content/curation` — curation queue
- `POST /api/admin/content/curation/{id}` — resolve curation item
- `GET /api/admin/audit-log` — audit log with filters
- `GET /api/admin/settings` — app settings
- `PUT /api/admin/settings/{category}/{key}` — update setting
- `GET /api/admin/jobs` — background job monitoring

### Frontend (admin-frontend/)
- Admin login (same auth, role-gated)
- Dashboard (charts: users, reviews/day, active learners, job queue)
- User management table (search, filter, edit roles/tiers, disable)
- Content curation page (review not-found words, approve/reject)
- Audit log viewer (filterable, searchable)
- Settings page (feature flags, provider config)
- Job monitoring (Celery task status, retry failed jobs)

### Tests
- Backend: RBAC enforcement (user can't access admin endpoints), audit logging, settings CRUD
- Frontend: admin pages render, role-gated access

### Acceptance Criteria
- Admin can view dashboard, manage users, curate content
- All admin actions logged in audit log
- Regular users get 403 on admin endpoints
- Superadmin can manage other admins

### Dependencies
- Phase 1 (auth + RBAC)
- Phase 6 (curation queue)

### Risks
- LOW: RBAC is straightforward with middleware
- LOW: Admin frontend is simpler than learner frontend

---

## Phase 10: Polish + E2E + Production Readiness

**Goal**: End-to-end tests, performance optimization, and production hardening.

### Deliverables
- Playwright E2E tests (critical user flows)
- S3 storage integration (replace local file storage)
- Performance optimization (query analysis, caching, pagination)
- Error handling polish (user-friendly messages, proper HTTP codes)
- CI/CD pipeline finalization (lint → test → build → deploy)
- Operation-aware retry policies (lesson learned)
- Security hardening (OWASP checklist)

### E2E Test Flows
1. Register → login → search word → view meanings
2. Upload ePub → review vocabulary → create word list
3. Add words to queue → review session → check stats
4. Concept learning flow (start → review → mastery)
5. Generate story → read → generate podcast
6. Admin: login → dashboard → manage user → curate content
7. Full loop: import → learn → review → master

### Tests
- E2E: 7+ Playwright tests covering critical flows
- Performance: query benchmarks, load testing
- Security: auth bypass attempts, injection testing

### Acceptance Criteria
- All E2E tests pass in CI
- No N+1 queries on list endpoints
- S3 storage works for all media files
- Rate limiting enforced on all endpoints
- Error responses follow consistent format

### Dependencies
- All previous phases

### Risks
- MEDIUM: E2E test flakiness (Playwright timing)
- MEDIUM: S3 migration from local storage
- LOW: Performance issues (PostgreSQL handles this scale fine)

---

## Cross-Cutting Concerns (All Phases)

### Testing Strategy
- TDD: write tests first, implement to pass, refactor
- 80%+ coverage target per phase
- Backend: pytest + pytest-asyncio
- Frontend: Jest + React Testing Library
- E2E: Playwright (Phase 10)
- Dedicated test database with safety guards (lesson learned)

### Error Handling
- Consistent error response format: `{"detail": "message", "code": "ERROR_CODE"}`
- Pydantic validation at API boundary
- Operation-aware retry policies (lesson learned)
- Never retry non-idempotent POSTs automatically

### Security
- Environment-based credentials (no hardcoded secrets — lesson learned)
- bcrypt password hashing
- JWT with short expiry + refresh tokens
- RBAC middleware on admin endpoints
- Rate limiting from day one
- Input validation on all endpoints

### State Management
- Zustand stores (not sessionStorage — lesson learned)
- Backend is source of truth for all learning state
- Frontend can always recover by querying backend

### Background Jobs
- Celery + Redis (not DB polling — lesson learned)
- Progress via SSE/WebSocket (not polling)
- Dead letter queue for failed jobs
- Idempotency keys for retryable operations

---

## Phase Dependency Graph

```
Phase 0 (Foundation)
  └── Phase 1 (Auth + Words)
        ├── Phase 2 (Word Lists + Import)
        │     └── Phase 3 (SM-2 Review)
        │           └── Phase 4 (Concepts)
        │                 └── Phase 7 (Listening)
        ├── Phase 5 (AI Integrations)
        │     ├── Phase 6 (Lexicon Enrichment)
        │     ├── Phase 7 (Listening) ←── also needs Phase 4
        │     └── Phase 8 (Stories/Podcasts)
        └── Phase 9 (Admin) ←── also needs Phase 6
              └── Phase 10 (Polish + E2E) ←── needs all phases
```

## Parallelization Opportunities

After Phase 1 completes:
- Phase 2 (Import) and Phase 5 (AI) can run in parallel
- Phase 3 (Review) can start as soon as Phase 2 delivers word lists
- Phase 9 (Admin) can start backend work early, frontend after Phase 6

After Phase 4 completes:
- Phase 7 (Listening) and Phase 8 (Stories) can run in parallel
