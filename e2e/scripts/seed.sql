-- Seed deterministic vocabulary used by Playwright E2E tests.
WITH upsert_word AS (
  INSERT INTO words (id, word, language, phonetic, frequency_rank, created_at)
  VALUES (
    '11111111-1111-1111-1111-111111111111'::uuid,
    'resilience',
    'en',
    NULL,
    2500,
    now()
  )
  ON CONFLICT (word, language)
  DO UPDATE SET frequency_rank = EXCLUDED.frequency_rank
  RETURNING id
)
INSERT INTO meanings (id, word_id, definition, part_of_speech, example_sentence, order_index, source, created_at)
SELECT
  '22222222-2222-2222-2222-222222222222'::uuid,
  upsert_word.id,
  'The capacity to recover quickly from difficulties.',
  'noun',
  'Resilience helps teams adapt to change.',
  0,
  'e2e-seed',
  now()
FROM upsert_word
ON CONFLICT (id)
DO UPDATE SET
  word_id = EXCLUDED.word_id,
  definition = EXCLUDED.definition,
  part_of_speech = EXCLUDED.part_of_speech,
  example_sentence = EXCLUDED.example_sentence,
  order_index = EXCLUDED.order_index,
  source = EXCLUDED.source;
