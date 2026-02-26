# Words-Codex — Vocabulary Learning Platform

## What This App Is

A context-aware English vocabulary learning app. Users import ePub books, extract vocabulary, and learn word meanings through spaced repetition. The key differentiator: learning happens at the **meaning level**, not the word level — because "bank" (river) and "bank" (financial) are different things to learn.

### Target Users
Migrants and practical English learners who need everyday + work vocabulary.

### Core Learning Loop
1. **Import** — Upload ePub → extract text → NLP processing → vocabulary list
2. **Select** — User picks which words/meanings to learn from the list
3. **Learn** — Concept-first learning with WordNet synsets (Recognition / Usage / Listening dimensions)
4. **Review** — SM-2 spaced repetition with interleaved card types (flashcard, cloze, listening, concept)
5. **Track** — Per-meaning mastery tracking, learning statistics

## Architecture

Monorepo with 3 apps + shared infrastructure:

```
words-codex/
├── backend/          # FastAPI + SQLAlchemy + PostgreSQL
├── frontend/         # Next.js (learner app, port 3000)
├── admin-frontend/   # Next.js (admin app, port 3001)
├── e2e/              # Playwright E2E tests
├── docker-compose.yml
└── scripts/
```

### Tech Stack
- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL 15, Redis 7, Alembic
- **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4
- **NLP**: spaCy (backend only — see lessons learned)
- **AI**: Multi-provider LLM (Anthropic/OpenAI/Gemini), TTS (MiniMax/ElevenLabs/Google/Azure), Image (Leonardo/DALL-E/Replicate)
- **Task Queue**: Celery + Redis (replaces DB polling)
- **State Management**: Zustand (replaces sessionStorage)
- **Testing**: pytest, Jest, Playwright
- **CI/CD**: GitHub Actions
- **Infra**: Docker Compose

## Key Features

### Implemented in Prototype (carry forward)
- SM-2 spaced repetition with multi-meaning support
- Concept-first learning via WordNet synsets with R/U/L mastery dimensions
- ePub import pipeline: hash → cache check → parse → NLP → enhance → review → create list
- Import recovery: resume interrupted imports
- Interleaved review queue: meanings + concepts + listening cards
- Lexicon pipeline: WordNet + Dictionary API + Datamuse + LLM enrichment + curation queue
- AI story/podcast generation with multi-provider TTS/LLM/image
- Admin system: RBAC (user/admin/superadmin), audit logging, content curation
- Multi-language translations cached per meaning
- Hybrid frequency ranking: COCA → wordfreq → Datamuse fallback

### Backend API Surface (~60 endpoints)
- `/api/auth/*` — JWT auth with refresh tokens
- `/api/words/*` — Search, lookup, auto-lemmatize
- `/api/learning/*` — Queue management, concept learning
- `/api/review/*` — Due items, submit reviews, stats
- `/api/word-lists/*` — Import, create, manage, bulk operations
- `/api/listening/concepts/*` — Listening practice items
- `/api/stories/*` — AI story generation, audio, podcasts
- `/api/audio/*`, `/api/images/*` — Media generation
- `/api/nlp/*` — Lemmatize, phrases, enhance
- `/api/admin/*` — Dashboard, users, content, audit, settings

### Database Schema (22 models)
Core: User, Word, Meaning, Translation, MeaningExample, MeaningPhrase
Learning: UserMeaning (SM-2 fields), ReviewHistory, WordList, WordListItem
Concepts: Synset, SynsetLemma, SynsetEdge, ConceptNode, ConceptExpression, UserSynsetMastery
Media: AudioCache, ImageCache, Story, StoryVersion, PodcastVersion
Admin: AuditLog, AppSetting, LexiconImportJob, LexiconCurationItem, LexiconEnrichmentJob

## Development Environment

```bash
# Start everything
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head

# Backend tests (dedicated test DB)
docker-compose -f docker-compose.test.yml run --rm test pytest -q

# Frontend tests
docker-compose exec frontend sh -lc "npm test -- --runInBand"

# E2E tests
docker-compose --profile tests run --rm playwright npx playwright test
```

### Environment Config
Copy `.env.example` (265 lines) → `.env`. Key sections: database, Redis, JWT, LLM API keys, TTS providers, image providers, storage backend.

## What to Keep in a Rebuild

### Keep (proven, well-designed)
- SM-2 spaced repetition algorithm (`spaced_repetition.py` — 91 lines, clean)
- Multi-provider abstractions (TTS, LLM, image — easy to swap providers)
- Concept/synset learning model (R/U/L mastery dimensions)
- Review interleaving logic (meanings + concepts + listening)
- Docker Compose setup (well-structured with profiles)
- Hybrid frequency ranking (COCA → wordfreq → Datamuse)
- Content hash-based ePub caching (SHA-256 dedup)
- Lexicon enrichment pipeline concept (WordNet → API → LLM → curation)
- Pydantic schema validation patterns
- RBAC + audit logging approach

### Rethink / Replace
- Client-side NLP → backend only (spaCy)
- Database job polling → Celery + Redis
- sessionStorage state → Zustand
- Generic retry logic → operation-aware policies
- Single import path → chunked/streaming for large imports
- Hardcoded credentials → env-based auth
- No CI/CD → GitHub Actions
- Local file storage → S3 from day one
- No rate limiting → FastAPI middleware from day one

## Rebuild Priorities (Suggested Order)
1. Core schema + auth + basic CRUD (words, meanings, users)
2. SM-2 spaced repetition + review system
3. ePub import pipeline (backend NLP only, Celery jobs)
4. Concept learning (synsets, R/U/L dimensions)
5. AI integrations (TTS, LLM, image generation)
6. Admin tools
7. Story/podcast generation

## Test Counts (Prototype Reference)
- Backend: 416 passed (38 test files)
- Frontend: 419 tests (33 suites)
- Admin: 45 tests (6 suites)
- E2E: 7 Playwright tests
- Total: ~880 tests

## Development Process (MANDATORY)

Every implementation task — no matter how "simple" — MUST follow this checklist in order. No exceptions. No rationalizing. Skipping steps is how the prototype accumulated tech debt.

### Pre-Implementation Checklist

Before writing ANY code:

1. **Invoke relevant skills** — Check if any skill applies (TDD, python-patterns, frontend-patterns, security-review, etc.). Even 1% chance = invoke it. This is non-negotiable.
2. **Reference the plan** — Confirm which phase/task you're implementing. If no plan exists, create one in `docs/plans/`.
3. **Write tests FIRST (TDD)** — Invoke the TDD skill. Write failing tests before implementation. RED → GREEN → REFACTOR. No exceptions.

### During Implementation

4. **Follow language-specific skills** — Python code: invoke `python-patterns`. Frontend code: invoke `frontend-patterns`. Both in same task: invoke both.
5. **Run tests after each change** — Confirm GREEN before moving on. Don't batch.
6. **Commit at logical checkpoints** — Don't wait until everything is done.

### Post-Implementation Checklist

7. **Run code review** — Invoke `code-reviewer` (and `python-review` / `security-review` as applicable). Fix CRITICAL and HIGH issues before proceeding.
8. **Verify coverage** — 80%+ target. Run coverage report.
9. **Update docs** — Update plan status, add lessons learned if any, create ADR if a decision was made.

### Skill Invocation Rules

These skills MUST be invoked for their respective contexts:

| Context | Required Skills |
|---------|----------------|
| Any Python code | `python-patterns` |
| Any frontend code | `frontend-patterns` |
| New feature / bug fix | `tdd-workflow` or `tdd` |
| Auth, user input, secrets, APIs | `security-review` |
| After writing code | `code-reviewer`, `python-review` or equivalent |
| Complex debugging | `systematic-debugging` |
| Before claiming "done" | `verification-before-completion` |

Forgetting to invoke a skill is a process failure. If you catch yourself writing code without having invoked the relevant skills, STOP, invoke them, and restart.

---

## Documentation Rules

All project documentation lives in `docs/`. See `docs/README.md` for full conventions.

### Required Documentation

When working on this project, you MUST:

1. **Before implementing a feature**: Write or reference a plan in `docs/plans/`
2. **When making architectural decisions**: Create an ADR in `docs/decisions/`
3. **When something goes wrong or a non-obvious fix is found**: Add a lesson in `docs/lessons/`
4. **After completing a phase**: Update the plan status and note any deviations

### Documentation Structure

```
docs/
├── README.md         # Documentation conventions (read this first)
├── plans/            # Implementation plans (YYYY-MM-DD-<topic>.md)
├── decisions/        # Architecture Decision Records (ADR-NNN-<topic>.md)
├── lessons/          # Lessons learned (YYYY-MM-DD-<topic>.md)
└── api/              # API docs (auto-generated + manual)
```

### Plan Status Tracking

Every plan file has a status header: `DRAFT` → `APPROVED` → `IN_PROGRESS` → `COMPLETED` or `SUPERSEDED`. Update it as work progresses. When a phase is done, add a completion note with any deviations from the original plan.

### Lessons Learned Protocol

Capture lessons immediately when they happen — don't wait until the end. Each lesson follows: What happened → Why → What to do → Files affected. The prototype lessons in `LESSONS_LEARNED.md` are the starting reference; new lessons go in `docs/lessons/`.

### ADR Protocol

Significant technical decisions get an ADR. "Significant" means: choosing between alternatives, deviating from the prototype approach, or introducing a new dependency/pattern. ADRs are never deleted — superseded ones link to their replacement.
