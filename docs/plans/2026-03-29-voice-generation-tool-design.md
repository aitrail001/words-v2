# Voice Generation Tool Design

**Date:** 2026-03-29
**Scope:** Offline lexicon voice generation from reviewed `approved.jsonl`, DB metadata storage, backend read API, and admin inspection.

## Goals

1. Keep `approved.jsonl` as the canonical reviewed text artifact.
2. Generate derived audio in batch without coupling it back into the reviewed JSONL.
3. Support multiple locales and both male/female variants for each content unit.
4. Keep provider, family, and concrete voice IDs configurable with sane defaults.
5. Persist stable storage metadata in DB so the backend can serve or redirect audio consistently across local and object storage backends.
6. Keep learner frontend unchanged in this slice while making backend/admin inspection ready for the next playback/review task.

## Core Decisions

### 1. Voice Is A Separate Derived Artifact Layer

The voice tool reads reviewed `approved.jsonl` rows and emits:

- audio files in a deterministic directory tree
- `voice_manifest.jsonl` success rows
- `voice_errors.jsonl` failed rows
- `voice_plan.jsonl` planned work units

This keeps text review and media generation decoupled. Voice can be regenerated independently when provider defaults, voices, or profiles change.

### 2. Generate Both Male And Female Variants

For each supported locale and content unit, the tool generates both `female` and `male` variants. Playback policy is not hardcoded into the generation step. Future learner/review UI can alternate or prefer voices without regeneration.

### 3. Provider-Agnostic Contract, Google First

The generation contract carries `provider`, `family`, `voice_id`, codec, and profile settings. The first implementation uses Google Cloud Text-to-Speech with default family `neural2`, but the same manifest and DB model can support:

- Google `chirp3`
- Azure voices
- AWS Polly voices

later without changing the artifact or DB contract.

### 4. Backend API Is The Stable Playback Boundary

The DB stores storage metadata, not final public URLs. The backend returns a stable `playback_url` pointing to a backend endpoint. That endpoint either:

- streams a local file, or
- redirects to a remote object URL when `storage_base` is an HTTP(S) base.

This avoids leaking storage layout choices to clients and works for both local and remote storage.

## Work Unit Model

Each planned audio unit is keyed by:

- `entry_id`
- `word`
- `source_reference`
- `content_scope`: `word`, `definition`, `example`
- `sense_id` and `meaning_index` for meaning/example units
- `example_index` for example units
- `locale`
- `voice_role`
- `provider`
- `family`
- `voice_id`
- `profile_key`
- `audio_format`
- `source_text_hash`

The planned output path is deterministic from those fields.

## Default Voice Config

Initial defaults:

- `google/neural2/en-US/female`: `en-US-Neural2-C`
- `google/neural2/en-US/male`: `en-US-Neural2-D`
- `google/neural2/en-GB/female`: `en-GB-Neural2-F`
- `google/neural2/en-GB/male`: `en-GB-Neural2-B`

The CLI exposes override files for voice maps and profile settings so these defaults are operational defaults, not schema assumptions.

## Profile Model

Profiles are keyed by content type:

- `word`
- `definition`
- `example`

Each profile stores:

- `speaking_rate`
- `pitch_semitones`
- `lead_ms`
- `tail_ms`
- `effects_profile_id`

For this slice, `speaking_rate`, `pitch_semitones`, and `effects_profile_id` affect synthesis. `lead_ms` and `tail_ms` are stored as playback metadata for future client/review consumption; the tool does not post-process audio to inject silence.

## Codec Decision

Default format: `mp3`

Reason:

- lowest-friction browser/device support
- simple operational path for the first slice

The CLI also supports `ogg_opus` so the batch contract is ready for later bandwidth optimization.

## Retry, Concurrency, And Flush Semantics

The generator uses a bounded worker pool and processes completions out of order. Each completed unit immediately:

- writes its audio file
- appends one row to `voice_manifest.jsonl`, or
- appends one row to `voice_errors.jsonl`

One failed or slow unit does not block unrelated units. Reruns can skip existing output files and focus naturally on missing or failed units.

## DB Schema

Add a normalized `lexicon.lexicon_voice_assets` table with nullable foreign keys to exactly one of:

- `words`
- `meanings`
- `meaning_examples`

Stored fields include:

- content identity
- locale/voice role/provider/family/voice ID
- synthesis settings
- storage metadata
- source text and text hash
- status/error/generated timestamp

This keeps the storage boundary explicit and queryable without stuffing media state into word JSON.

## Backend Read Surface

Extend existing word enrichment/admin inspector responses with flat `voice_assets` arrays. Each row includes:

- content scope linkage
- provider/family/voice config
- storage metadata
- backend `playback_url`

Learner frontend remains unchanged in this slice.

## Admin Impact

Admin UI adapts only in the DB inspector:

- show total stored voice assets for a word
- show each voice asset’s scope, locale, role, profile, status, and playback URL

No change to current learner routes or review UI in this slice.
