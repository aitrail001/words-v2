#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import Json


WORD_POLICY_ID = "6c19a4f5-5970-4d94-8af8-728e4433c200"
DEFINITION_POLICY_ID = "f1ecf376-96d1-4212-b235-fd3963e2f2bb"
REPO_ROOT = Path(__file__).resolve().parents[3]
VOICE_ROOT = REPO_ROOT / "data/lexicon/voice"
CONTAINER_VOICE_ROOT = Path("/app/data/lexicon/voice")
WORDS_SNAPSHOT_PATH = (
    REPO_ROOT
    / "data/lexicon/snapshots/words-40000-20260323-main-wordfreq-live-target30k/reviewed/approved.jsonl"
)
PHRASES_SNAPSHOT_PATH = (
    REPO_ROOT
    / "data/lexicon/snapshots/phrases-7488-20260323-reviewed-phrasals-idioms-v1/reviewed/approved.jsonl"
)


@dataclass(frozen=True)
class Scenario:
    key: str
    prompt_type: str
    entry_type: str
    entry_id: str
    target_id: str
    display_text: str
    normalized_form: str
    definition: str
    sentence: str | None
    part_of_speech: str
    browse_rank: int
    bucket_start: int
    phrase_kind: str | None = None
    phonetic: str | None = None
    phonetics: dict | None = None
    usage_note: str | None = None
    register: str = "neutral"
    collocations: list[str] | None = None
    synonyms: list[str] | None = None
    antonyms: list[str] | None = None
    grammar_patterns: list[str] | None = None
    cefr_level: str | None = None
    compiled_payload: dict | None = None
    with_audio: bool = False
    audio_relative_path: str | None = None


@dataclass(frozen=True)
class ResolvedScenario:
    scenario: Scenario
    resolved_entry_id: str
    resolved_target_id: str


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    prompt_type: str
    entry_type: str
    entry_id: str
    target_id: str
    snapshot_word: str
    browse_rank: int
    bucket_start: int
    with_audio: bool = False
    audio_relative_path: str | None = None


SCENARIO_SPECS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec("confidence-check", "confidence_check", "word", "81000000-0000-0000-0000-000000000001", "82000000-0000-0000-0000-000000000001", "persistence", 3101, 3101, with_audio=True, audio_relative_path="words-40000-20260323-main-wordfreq-live-target30k/lx_persistence/word/en_us/female-word-0d2a4d0e13a3.mp3"),
    ScenarioSpec("sentence-gap", "sentence_gap", "word", "81000000-0000-0000-0000-000000000011", "82000000-0000-0000-0000-000000000011", "barely", 3102, 3101),
    ScenarioSpec("collocation", "collocation_check", "phrase", "81000000-0000-0000-0000-000000000002", "82000000-0000-0000-0000-000000000002", "jump the gun", 3103, 3101),
    ScenarioSpec("situation", "situation_matching", "word", "81000000-0000-0000-0000-000000000003", "82000000-0000-0000-0000-000000000003", "resilience", 3104, 3101),
    ScenarioSpec("entry-to-definition", "entry_to_definition", "word", "81000000-0000-0000-0000-000000000004", "82000000-0000-0000-0000-000000000004", "meticulous", 3105, 3101),
    ScenarioSpec("audio-to-definition", "audio_to_definition", "phrase", "81000000-0000-0000-0000-000000000005", "82000000-0000-0000-0000-000000000005", "as it is", 3106, 3101, with_audio=True, audio_relative_path="phrases-7488-20260323-reviewed-phrasals-idioms-v1/ph_as_it_is_eb09baab/word/en_us/female-word-f5c9477a85fc.mp3"),
    ScenarioSpec("typed-recall", "typed_recall", "word", "81000000-0000-0000-0000-000000000006", "82000000-0000-0000-0000-000000000006", "candid", 3107, 3101),
    ScenarioSpec("speak-recall", "speak_recall", "word", "81000000-0000-0000-0000-000000000010", "82000000-0000-0000-0000-000000000010", "candidate", 3108, 3101, with_audio=True, audio_relative_path="words-40000-20260323-main-wordfreq-live-target30k/lx_candidate/word/en_us/female-word-dda18a0e21ae.mp3"),
    ScenarioSpec("definition-to-entry", "definition_to_entry", "phrase", "81000000-0000-0000-0000-000000000009", "82000000-0000-0000-0000-000000000009", "by and large", 3109, 3101),
)


def choose_primary_phonetic(phonetics: dict | None) -> str | None:
    if not phonetics:
        return None
    for locale in ("us", "uk", "au"):
        candidate = phonetics.get(locale, {}).get("ipa")
        if candidate:
            return candidate
    for value in phonetics.values():
        candidate = value.get("ipa")
        if candidate:
            return candidate
    return None


def load_snapshot_entries(path: Path) -> dict[str, dict]:
    if not path.exists():
        raise FileNotFoundError(f"Expected approved snapshot at {path}")
    entries: dict[str, dict] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            entries[row["word"]] = row
    return entries


def build_scenarios() -> tuple[Scenario, ...]:
    word_rows = load_snapshot_entries(WORDS_SNAPSHOT_PATH)
    phrase_rows = load_snapshot_entries(PHRASES_SNAPSHOT_PATH)
    scenarios: list[Scenario] = []
    for spec in SCENARIO_SPECS:
        row = word_rows[spec.snapshot_word] if spec.entry_type == "word" else phrase_rows[spec.snapshot_word]
        sense = row["senses"][0]
        examples = sense.get("examples", [])
        sentence = examples[0]["sentence"] if examples else None
        phonetics = row.get("phonetics") or None
        scenarios.append(
            Scenario(
                key=spec.key,
                prompt_type=spec.prompt_type,
                entry_type=spec.entry_type,
                entry_id=spec.entry_id,
                target_id=spec.target_id,
                display_text=row.get("display_form") or row["word"],
                normalized_form=row.get("normalized_form") or row["word"].lower(),
                definition=sense["definition"],
                sentence=sentence,
                part_of_speech=sense["pos"],
                browse_rank=spec.browse_rank,
                bucket_start=spec.bucket_start,
                phrase_kind=row.get("phrase_kind"),
                phonetic=choose_primary_phonetic(phonetics),
                phonetics=phonetics,
                usage_note=sense.get("usage_note"),
                register=sense.get("register") or "neutral",
                collocations=sense.get("collocations") or [],
                synonyms=sense.get("synonyms") or [],
                antonyms=sense.get("antonyms") or [],
                grammar_patterns=sense.get("grammar_patterns") or [],
                cefr_level=row.get("cefr_level"),
                compiled_payload=row if spec.entry_type == "phrase" else None,
                with_audio=spec.with_audio,
                audio_relative_path=spec.audio_relative_path,
            )
        )
    return tuple(scenarios)


SCENARIOS: tuple[Scenario, ...] = build_scenarios()


def connection_candidates() -> list[str]:
    explicit = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    if explicit:
        return [explicit.replace("+asyncpg", "")]
    return [
        "postgresql://vocabapp:change_this_password_in_production@localhost:5432/vocabapp_dev",
        "postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev",
    ]


def connect():
    last_error: Exception | None = None
    for candidate in connection_candidates():
        try:
            return psycopg2.connect(candidate)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Unable to connect to Postgres using known local URLs: {last_error}") from last_error


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_audio_fixture_file() -> None:
    for scenario in SCENARIOS:
        if not scenario.with_audio or not scenario.audio_relative_path:
            continue
        target = VOICE_ROOT / scenario.audio_relative_path
        if not target.exists():
            raise FileNotFoundError(f"Expected real voice asset at {target}")


def ensure_voice_policies(cur) -> tuple[str, str]:
    cur.execute(
        """
        INSERT INTO lexicon.lexicon_voice_storage_policies (
          id,
          policy_key,
          source_reference,
          content_scope,
          provider,
          family,
          locale,
          primary_storage_kind,
          primary_storage_base,
          fallback_storage_kind,
          fallback_storage_base,
          created_at
        )
        VALUES
          (%s::uuid, 'word_default', 'global', 'word', 'default', 'default', 'all', 'local', %s, 'local', %s, now()),
          (%s::uuid, 'definition_default', 'global', 'definition', 'default', 'default', 'all', 'local', '/tmp/voice', NULL, NULL, now())
        ON CONFLICT (policy_key)
        DO UPDATE SET
          primary_storage_kind = EXCLUDED.primary_storage_kind,
          primary_storage_base = EXCLUDED.primary_storage_base,
          fallback_storage_kind = EXCLUDED.fallback_storage_kind,
          fallback_storage_base = EXCLUDED.fallback_storage_base
        """,
        (WORD_POLICY_ID, str(CONTAINER_VOICE_ROOT), str(VOICE_ROOT), DEFINITION_POLICY_ID),
    )
    cur.execute(
        """
        SELECT policy_key, id::text
        FROM lexicon.lexicon_voice_storage_policies
        WHERE policy_key IN ('word_default', 'definition_default')
        """
    )
    policies = {policy_key: policy_id for policy_key, policy_id in cur.fetchall()}
    return (
        policies.get("word_default", WORD_POLICY_ID),
        policies.get("definition_default", DEFINITION_POLICY_ID),
    )
def upsert_word(cur, scenario: Scenario) -> ResolvedScenario:
    cur.execute(
        """
        INSERT INTO lexicon.words (id, word, language, phonetics, phonetic, frequency_rank, created_at)
        VALUES (%s::uuid, %s, 'en', %s::json, %s, %s, now())
        ON CONFLICT (word, language)
        DO UPDATE SET
          phonetics = EXCLUDED.phonetics,
          phonetic = EXCLUDED.phonetic,
          frequency_rank = EXCLUDED.frequency_rank
        RETURNING id::text
        """,
        (scenario.entry_id, scenario.display_text, Json(scenario.phonetics or {}), scenario.phonetic, scenario.browse_rank),
    )
    resolved_entry_id = cur.fetchone()[0]
    cur.execute("DELETE FROM lexicon.word_part_of_speech WHERE word_id = %s::uuid", (resolved_entry_id,))
    cur.execute(
        """
        INSERT INTO lexicon.word_part_of_speech (id, word_id, value, order_index, created_at)
        VALUES (%s::uuid, %s::uuid, %s, 0, now())
        """,
        (str(uuid.uuid4()), resolved_entry_id, scenario.part_of_speech),
    )
    cur.execute(
        """
        INSERT INTO lexicon.meanings (
          id, word_id, definition, part_of_speech, example_sentence, order_index, source, created_at
        )
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, 0, 'snapshot-approved-review-seed', now())
        ON CONFLICT (id)
        DO UPDATE SET
          word_id = EXCLUDED.word_id,
          definition = EXCLUDED.definition,
          part_of_speech = EXCLUDED.part_of_speech,
          example_sentence = EXCLUDED.example_sentence,
          order_index = EXCLUDED.order_index,
          source = EXCLUDED.source
        """,
        (scenario.target_id, resolved_entry_id, scenario.definition, scenario.part_of_speech, scenario.sentence),
    )
    if scenario.sentence:
        cur.execute(
            """
            INSERT INTO lexicon.meaning_examples (
              id, meaning_id, sentence, difficulty, order_index, source, created_at
            )
            VALUES (%s::uuid, %s::uuid, %s, 'B2', 0, 'snapshot-approved-review-seed', now())
            ON CONFLICT (meaning_id, sentence)
            DO UPDATE SET
              difficulty = EXCLUDED.difficulty,
              order_index = EXCLUDED.order_index,
              source = EXCLUDED.source
            """,
            (str(uuid.uuid4()), scenario.target_id, scenario.sentence),
        )
    return ResolvedScenario(
        scenario=scenario,
        resolved_entry_id=resolved_entry_id,
        resolved_target_id=scenario.target_id,
    )


def upsert_phrase(cur, scenario: Scenario) -> ResolvedScenario:
    cur.execute(
        """
        INSERT INTO lexicon.phrase_entries (
          id, phrase_text, normalized_form, phrase_kind, language, cefr_level, compiled_payload, created_at
        )
        VALUES (%s::uuid, %s, %s, %s, 'en', %s, %s::jsonb, now())
        ON CONFLICT (normalized_form, language)
        DO UPDATE SET
          phrase_text = EXCLUDED.phrase_text,
          phrase_kind = EXCLUDED.phrase_kind,
          cefr_level = EXCLUDED.cefr_level,
          compiled_payload = EXCLUDED.compiled_payload
        RETURNING id::text
        """,
        (
            scenario.entry_id,
            scenario.display_text,
            scenario.normalized_form,
            scenario.phrase_kind or "multiword_expression",
            scenario.cefr_level or "B2",
            Json(scenario.compiled_payload or {}),
        ),
    )
    resolved_entry_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO lexicon.phrase_senses (
          id, phrase_entry_id, definition, usage_note, part_of_speech, register, primary_domain,
          secondary_domains, grammar_patterns, synonyms, antonyms, collocations, order_index, created_at
        )
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, 'general', '[]'::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, 0, now())
        ON CONFLICT (phrase_entry_id, order_index)
        DO UPDATE SET
          definition = EXCLUDED.definition,
          part_of_speech = EXCLUDED.part_of_speech,
          register = EXCLUDED.register,
          primary_domain = EXCLUDED.primary_domain,
          secondary_domains = EXCLUDED.secondary_domains,
          grammar_patterns = EXCLUDED.grammar_patterns,
          synonyms = EXCLUDED.synonyms,
          antonyms = EXCLUDED.antonyms,
          collocations = EXCLUDED.collocations
        """,
        (
            scenario.target_id,
            resolved_entry_id,
            scenario.definition,
            scenario.usage_note,
            scenario.part_of_speech,
            scenario.register,
            Json(scenario.grammar_patterns or []),
            Json(scenario.synonyms or []),
            Json(scenario.antonyms or []),
            Json(scenario.collocations or []),
        ),
    )
    if scenario.sentence:
        cur.execute(
            """
            INSERT INTO lexicon.phrase_sense_examples (
              id, phrase_sense_id, sentence, difficulty, order_index, source, created_at
            )
            VALUES (%s::uuid, %s::uuid, %s, 'B2', 0, 'snapshot-approved-review-seed', now())
            ON CONFLICT (phrase_sense_id, sentence)
            DO UPDATE SET
              difficulty = EXCLUDED.difficulty,
              order_index = EXCLUDED.order_index,
              source = EXCLUDED.source
            """,
            (str(uuid.uuid4()), scenario.target_id, scenario.sentence),
        )
    return ResolvedScenario(
        scenario=scenario,
        resolved_entry_id=resolved_entry_id,
        resolved_target_id=scenario.target_id,
    )


def upsert_catalog_entry(cur, resolved: ResolvedScenario) -> None:
    scenario = resolved.scenario
    cur.execute(
        """
        INSERT INTO lexicon.learner_catalog_entries (
          id, entry_type, entry_id, display_text, normalized_form, browse_rank, bucket_start,
          cefr_level, primary_part_of_speech, phrase_kind, is_ranked, created_at
        )
        VALUES (gen_random_uuid(), %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (entry_type, entry_id)
        DO UPDATE SET
          display_text = EXCLUDED.display_text,
          normalized_form = EXCLUDED.normalized_form,
          browse_rank = EXCLUDED.browse_rank,
          bucket_start = EXCLUDED.bucket_start,
          cefr_level = EXCLUDED.cefr_level,
          primary_part_of_speech = EXCLUDED.primary_part_of_speech,
          phrase_kind = EXCLUDED.phrase_kind,
          is_ranked = EXCLUDED.is_ranked
        """,
        (
            scenario.entry_type,
            resolved.resolved_entry_id,
            scenario.display_text,
            scenario.normalized_form,
            scenario.browse_rank,
            scenario.bucket_start,
            scenario.cefr_level or "B2",
            scenario.part_of_speech if scenario.entry_type == "word" else None,
            scenario.phrase_kind if scenario.entry_type == "phrase" else None,
            scenario.entry_type == "word",
        ),
    )


def ensure_audio_asset(cur, word_policy_id: str, resolved_scenarios: list[ResolvedScenario]) -> None:
    ensure_audio_fixture_file()
    for resolved in resolved_scenarios:
        scenario = resolved.scenario
        if not scenario.with_audio or not scenario.audio_relative_path:
            continue
        asset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"review-scenario-audio:{scenario.entry_id}"))
        cur.execute(
            """
            INSERT INTO lexicon.lexicon_voice_assets (
              id, word_id, meaning_id, meaning_example_id, phrase_entry_id, phrase_sense_id, phrase_sense_example_id,
              storage_policy_id, content_scope, locale, voice_role, provider, family, voice_id, profile_key,
              audio_format, mime_type, relative_path, source_text, source_text_hash, status, created_at
            )
            VALUES (
              %s::uuid, %s::uuid, NULL, NULL, %s::uuid, NULL, NULL, %s::uuid, 'word', 'en_us', 'female',
              'default', 'default', 'fixture-voice', 'word', 'mp3', 'audio/mpeg',
              %s, %s, %s, 'generated', now()
            )
            ON CONFLICT (id)
            DO UPDATE SET
              word_id = EXCLUDED.word_id,
              meaning_id = EXCLUDED.meaning_id,
              meaning_example_id = EXCLUDED.meaning_example_id,
              phrase_entry_id = EXCLUDED.phrase_entry_id,
              phrase_sense_id = EXCLUDED.phrase_sense_id,
              phrase_sense_example_id = EXCLUDED.phrase_sense_example_id,
              storage_policy_id = EXCLUDED.storage_policy_id,
              content_scope = EXCLUDED.content_scope,
              locale = EXCLUDED.locale,
              voice_role = EXCLUDED.voice_role,
              provider = EXCLUDED.provider,
              family = EXCLUDED.family,
              voice_id = EXCLUDED.voice_id,
              profile_key = EXCLUDED.profile_key,
              relative_path = EXCLUDED.relative_path,
              source_text = EXCLUDED.source_text,
              source_text_hash = EXCLUDED.source_text_hash,
              audio_format = EXCLUDED.audio_format,
              mime_type = EXCLUDED.mime_type,
              status = EXCLUDED.status
            """,
            (
                asset_id,
                resolved.resolved_entry_id if scenario.entry_type == "word" else None,
                resolved.resolved_entry_id if scenario.entry_type == "phrase" else None,
                word_policy_id,
                scenario.audio_relative_path,
                scenario.display_text,
                sha256_text(scenario.display_text),
            ),
        )


def seed_catalog(cur) -> list[ResolvedScenario]:
    word_policy_id, _ = ensure_voice_policies(cur)
    resolved_scenarios: list[ResolvedScenario] = []
    for scenario in SCENARIOS:
        if scenario.entry_type == "word":
            resolved = upsert_word(cur, scenario)
        else:
            resolved = upsert_phrase(cur, scenario)
        upsert_catalog_entry(cur, resolved)
        resolved_scenarios.append(resolved)
    ensure_audio_asset(cur, word_policy_id, resolved_scenarios)
    return resolved_scenarios


def fetch_target_users(cur, emails: Iterable[str] | None, include_admin: bool) -> list[tuple[str, str]]:
    if emails:
        cur.execute(
            """
            SELECT id::text, email
            FROM users
            WHERE email = ANY(%s)
            ORDER BY email ASC
            """,
            (list(emails),),
        )
    elif include_admin:
        cur.execute("SELECT id::text, email FROM users ORDER BY email ASC")
    else:
        cur.execute(
            """
            SELECT id::text, email
            FROM users
            WHERE COALESCE(role, 'user') != 'admin'
            ORDER BY email ASC
            """
        )
    return cur.fetchall()


def seed_user_queue(cur, user_id: str, resolved_scenarios: Iterable[ResolvedScenario]) -> None:
    resolved_list = list(resolved_scenarios)
    cur.execute(
        """
        INSERT INTO user_preferences (
          id, user_id, accent_preference, translation_locale, knowledge_view_preference,
          review_depth_preset, enable_confidence_check, enable_word_spelling, enable_audio_spelling,
          show_pictures_in_questions
        )
        VALUES (%s::uuid, %s::uuid, 'us', 'es', 'cards', 'balanced', false, true, true, false)
        ON CONFLICT (user_id)
        DO UPDATE SET
          accent_preference = EXCLUDED.accent_preference,
          translation_locale = EXCLUDED.translation_locale,
          knowledge_view_preference = EXCLUDED.knowledge_view_preference,
          review_depth_preset = EXCLUDED.review_depth_preset,
          enable_confidence_check = EXCLUDED.enable_confidence_check,
          enable_word_spelling = EXCLUDED.enable_word_spelling,
          enable_audio_spelling = EXCLUDED.enable_audio_spelling,
          show_pictures_in_questions = EXCLUDED.show_pictures_in_questions,
          updated_at = now()
        """,
        (str(uuid.uuid4()), user_id),
    )
    cur.execute("DELETE FROM entry_review_states WHERE user_id = %s::uuid", (user_id,))
    for resolved in resolved_list:
        scenario = resolved.scenario
        cur.execute(
            """
            INSERT INTO learner_entry_statuses (id, user_id, entry_type, entry_id, status)
            VALUES (%s::uuid, %s::uuid, %s, %s::uuid, 'learning')
            ON CONFLICT (user_id, entry_type, entry_id)
            DO UPDATE SET status = EXCLUDED.status, updated_at = now()
            """,
            (str(uuid.uuid4()), user_id, scenario.entry_type, resolved.resolved_entry_id),
        )
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for offset, resolved in enumerate(resolved_list):
        scenario = resolved.scenario
        ts = base + timedelta(seconds=offset)
        cur.execute(
            """
            INSERT INTO entry_review_states (
              id, user_id, target_type, target_id, entry_type, entry_id, stability, difficulty,
              success_streak, lapse_count, exposure_count, times_remembered, last_prompt_type,
              last_submission_prompt_id, last_outcome, is_fragile, is_suspended, relearning,
              relearning_trigger, recheck_due_at, last_reviewed_at, next_due_at, created_at, updated_at
            )
            VALUES (
              %s::uuid, %s::uuid, %s, %s::uuid, %s, %s::uuid, 2.0, 0.45, 0, 0, 0, 0, NULL, %s,
              NULL, false, false, false, NULL, NULL, NULL, %s, %s, %s
            )
            """,
            (
                str(uuid.uuid4()),
                user_id,
                "meaning" if scenario.entry_type == "word" else "phrase_sense",
                resolved.resolved_target_id,
                scenario.entry_type,
                resolved.resolved_entry_id,
                f"manual_prompt_type:{scenario.prompt_type}",
                ts,
                ts,
                ts,
            ),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed deterministic review scenarios into the local DB.")
    parser.add_argument(
        "--email",
        action="append",
        default=[],
        help="Target one or more specific user emails. Defaults to all non-admin users.",
    )
    parser.add_argument(
        "--include-admin",
        action="store_true",
        help="Also seed admin users when no --email filter is provided.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            users = fetch_target_users(cur, args.email or None, args.include_admin)
            if not users:
                print("No matching users found. Nothing seeded.", file=sys.stderr)
                conn.rollback()
                return 1
            resolved_scenarios = seed_catalog(cur)
            for user_id, _email in users:
                seed_user_queue(cur, user_id, resolved_scenarios)
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("Seeded review scenarios for:")
    for _user_id, email in users:
        print(f"- {email}")
    print("")
    print("Queue order:")
    for index, scenario in enumerate(SCENARIOS, start=1):
        print(f"{index}. {scenario.prompt_type} -> {scenario.display_text}")
    print("")
    print("Notes:")
    print("- Existing entry_review_states were replaced for targeted users.")
    print("- User preferences were set to balanced depth, audio spelling on, confidence prompts off.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
