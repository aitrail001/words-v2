# App Description — Words-Codex

## Vision

A vocabulary learning app that treats words as containers of multiple meanings, and teaches each meaning in the context where the user encountered it. Built for people learning English as a practical skill (migrants, professionals), not as an academic exercise.

## How It Works (User Journey)

### 1. Import Vocabulary from Reading

The user uploads an ePub book. The system:
1. Calculates SHA-256 hash of the file
2. Checks if this book was already processed (cache hit → skip to step 6)
3. Extracts text and metadata (title, author, chapters)
4. Runs NLP: tokenization → lemmatization → frequency counting → phrase detection
5. Caches processed results on backend (keyed by content hash)
6. Presents vocabulary list: words sorted by frequency, with part-of-speech tags

The user reviews the list, selects words they want to learn, and creates a "word list" (e.g., "Pride and Prejudice — Chapter 1-5").

### 2. Word Lookup and Meaning Selection

When a word is looked up:
1. Backend checks local database first
2. If not found: fetches from Dictionary API (dictionaryapi.dev)
3. Enriches with WordNet synsets, Datamuse frequency data
4. Stores all meanings with definitions, examples, part of speech
5. User sees all meanings and selects which ones to learn

Each meaning is a separate learning item. "Run" (to move quickly) and "run" (a sequence) are tracked independently.

### 3. Concept-First Learning

Words are grouped into concepts via WordNet synsets. A "concept pack" contains:
- **Core**: The primary lemmas for this concept (e.g., "happy", "glad", "joyful")
- **Contrast**: Similar but distinct concepts (e.g., "happy" vs "content" vs "ecstatic")
- **Phrases**: Common collocations and idioms (e.g., "happy-go-lucky", "glad tidings")

Learning is tracked across three dimensions:
- **Recognition (R)**: Can you understand this concept when you encounter it?
- **Usage (U)**: Can you produce this concept in your own speech/writing?
- **Listening (L)**: Can you recognize this concept in spoken English?

### 4. Spaced Repetition Review

The review system uses SM-2 algorithm with interleaved card types:
- **Word → Definition**: See word, recall meaning
- **Definition → Word**: See definition, recall word
- **Fill in the Blank**: Complete a sentence with the right word
- **Listening**: Hear the word/sentence, identify the meaning
- **Concept Review**: Review a synset with its lemmas and contrasts

Cards from different types are shuffled together. Due dates are calculated per-meaning using SM-2 (ease factor, interval, repetitions). Mastery = interval > 21 days with quality ≥ 3.

### 5. AI-Enhanced Learning

- **TTS**: Generate pronunciation audio for words, definitions, example sentences
- **Images**: Generate visual aids for word meanings (AI-generated illustrations)
- **Stories**: Generate short stories using the user's vocabulary words
- **Podcasts**: Generate podcast-style dialogues using vocabulary in context

All AI features use multi-provider abstractions (can swap between OpenAI, Anthropic, Google, etc.).

### 6. Admin Tools

Admin panel for content management:
- User management (roles, tiers)
- Lexicon curation (review not-found words, approve/reject)
- Synset quality tools (check concept pack completeness)
- Media generation jobs (batch TTS/image generation)
- Audit log (who did what, when)
- System settings (feature flags, provider config)

## Data Model (Conceptual)

```
User
 ├── has many WordLists (from ePub imports)
 │    └── has many WordListItems (words in context)
 ├── has many UserMeanings (learning queue)
 │    ├── SM-2 fields (ease_factor, interval, next_review)
 │    └── linked to Meaning
 └── has many UserSynsetMastery (concept progress)
      └── R/U/L dimension scores

Word
 ├── has many Meanings
 │    ├── definition, part_of_speech, examples
 │    ├── has many Translations (per language)
 │    └── linked to Synset (WordNet concept)
 └── frequency_rank, phonetic, word_forms

Synset (WordNet concept)
 ├── has many SynsetLemmas (words expressing this concept)
 ├── has many SynsetEdges (hypernym, hyponym, etc.)
 └── has ConceptNode
      ├── has many ConceptExpressions
      └── has many ConceptRelations
```

## API Design

RESTful, versioned at `/api/v1/` (prototype used `/api/`).

### Authentication
- JWT with refresh tokens
- Roles: user, admin, superadmin
- Tiers: free, premium

### Key Endpoints
| Area | Endpoints | Purpose |
|------|-----------|---------|
| Auth | `/auth/register`, `/auth/login`, `/auth/refresh` | User management |
| Words | `/words/search`, `/words/{id}`, `/words/{id}/meanings` | Vocabulary lookup |
| Learning | `/learning/queue`, `/learning/add`, `/learning/{id}` | Learning queue |
| Review | `/review/due`, `/review/submit`, `/review/stats` | Spaced repetition |
| Concepts | `/concepts/next`, `/concepts/{id}/start`, `/concepts/{id}` | Concept learning |
| Listening | `/listening/{synset_id}/items`, `/listening/submit` | Listening practice |
| Word Lists | `/word-lists/import`, `/word-lists/`, `/word-lists/{id}` | List management |
| Stories | `/stories/generate`, `/stories/`, `/stories/{id}` | AI stories |
| Media | `/audio/generate`, `/images/generate` | TTS and images |
| Admin | `/admin/dashboard`, `/admin/users`, `/admin/content` | Administration |

### Background Jobs (via Celery)
- Word list import (large ePub vocabularies)
- Lexicon enrichment (LLM-based enhancement)
- Media generation (batch TTS/image)
- Synset rebuilding (concept pack assembly)

## External Dependencies

### APIs
- **Dictionary API** (dictionaryapi.dev) — Free, no key needed. Word definitions and phonetics.
- **Datamuse API** — Free, no key needed. Word frequency and relationships.
- **WordNet** (via NLTK) — Local. Synsets, lemmas, relationships.
- **wordfreq** — Local Python library. Zipf frequency scores.

### AI Providers (all optional, multi-provider)
- **LLM**: Anthropic Claude, OpenAI GPT, Google Gemini
- **TTS**: MiniMax, ElevenLabs, Google Cloud TTS, Azure Speech
- **Image**: Leonardo.ai, Replicate (FLUX), OpenAI DALL-E

### Infrastructure
- PostgreSQL 15 — Primary database
- Redis 7 — Cache + Celery broker
- S3-compatible storage — Media files (audio, images, ePubs)
