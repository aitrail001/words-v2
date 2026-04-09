# Database Schema Reference — Words-Codex Prototype

Complete schema from the prototype's 22 SQLAlchemy models and 37 Alembic migrations.

---

## Core Vocabulary

### `words`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word | String(255) | NOT NULL, unique with language |
| language | String(10) | default='en' |
| phonetic | String(255) | nullable |
| phonetic_source | String(50) | nullable |
| phonetic_confidence | Float | nullable |
| phonetic_enrichment_run_id | UUID | FK→lexicon_enrichment_runs, SET NULL |
| frequency_rank | Integer | nullable, indexed |
| word_forms | JSON | nullable (inflections) |
| source | String(50) | nullable |
| source_ref | String(100) | nullable |
| created_at | DateTime | default=now |

Indexes: word, frequency_rank
Unique: (word, language)
Relations: meanings (1:N), word_list_items (1:N), relations (1:N)

### `meanings`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word_id | UUID | FK→words, CASCADE |
| definition | Text | NOT NULL |
| part_of_speech | String(50) | nullable |
| example_sentence | Text | nullable |
| order_index | Integer | default=0 |
| source | String(50) | nullable |
| source_ref | String(100) | nullable |
| created_at | DateTime | default=now |

Relations: translations (1:N), user_meanings (1:N), examples (1:N), phrase_links (M:N)

### `translations`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| meaning_id | UUID | FK→meanings, CASCADE |
| language | String(10) | NOT NULL |
| translation | Text | NOT NULL |

Unique: (meaning_id, language)

---

## Lexicon Enrichment

### `meaning_examples`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| meaning_id | UUID | FK→meanings, CASCADE |
| sentence | Text | NOT NULL |
| order_index | Integer | default=0 |
| source | String(50) | nullable |
| confidence | Float | nullable |
| enrichment_run_id | UUID | FK→lexicon_enrichment_runs, SET NULL |
| created_at | DateTime | default=now |

Unique: (meaning_id, sentence)

### `meaning_phrases`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| meaning_id | UUID | FK→meanings, CASCADE |
| phrase_id | UUID | FK→phrases, CASCADE |
| order_index | Integer | default=0 |
| source | String(50) | nullable |
| confidence | Float | nullable |
| enrichment_run_id | UUID | FK→lexicon_enrichment_runs, SET NULL |
| created_at | DateTime | default=now |

Unique: (meaning_id, phrase_id)

### `word_relations`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word_id | UUID | FK→words, CASCADE |
| meaning_id | UUID | FK→meanings, nullable, CASCADE |
| relation_type | String(50) | NOT NULL, indexed |
| related_word | String(255) | NOT NULL |
| related_word_id | UUID | FK→words, SET NULL |
| source | String(50) | nullable |
| confidence | Float | nullable |
| enrichment_run_id | UUID | FK→lexicon_enrichment_runs, SET NULL |
| created_at | DateTime | default=now |

Unique: (word_id, meaning_id, relation_type, related_word)

### `lexicon_enrichment_jobs`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word_id | UUID | FK→words, CASCADE |
| phase | String(20) | default='phase1' |
| status | String(20) | default='pending', indexed |
| priority | Integer | default=100, indexed |
| attempt_count | Integer | default=0 |
| max_attempts | Integer | default=3 |
| next_retry_at | DateTime | nullable |
| last_error | Text | nullable |
| started_at | DateTime | nullable |
| completed_at | DateTime | nullable |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

Unique: (word_id, phase)

### `lexicon_enrichment_runs`
Immutable record of each LLM enrichment attempt.

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| enrichment_job_id | UUID | FK→lexicon_enrichment_jobs, CASCADE |
| generator_provider | String(50) | nullable |
| generator_model | String(100) | nullable |
| validator_provider | String(50) | nullable |
| validator_model | String(100) | nullable |
| prompt_version | String(50) | nullable |
| prompt_hash | String(128) | nullable |
| generator_output | JSON | nullable |
| validator_output | JSON | nullable |
| verdict | String(20) | nullable |
| confidence | Float | nullable |
| token_input | Integer | nullable |
| token_output | Integer | nullable |
| estimated_cost | Float | nullable |
| created_at | DateTime | default=now |

### `lexicon_curation_items`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word | String(255) | NOT NULL, indexed |
| language | String(10) | default='en' |
| reason | String(50) | default='not_found', indexed |
| status | String(20) | default='pending', indexed |
| import_job_id | UUID | FK→lexicon_import_jobs, SET NULL |
| word_id | UUID | FK→words, SET NULL |
| frequency_rank | Integer | nullable |
| resolution_note | Text | nullable |
| payload | JSON | nullable |
| created_by | UUID | FK→users, SET NULL |
| reviewed_by | UUID | FK→users, SET NULL |
| reviewed_at | DateTime | nullable |
| created_at | DateTime | default=now |

Unique: (word, language, reason, status)

---

## Phrases

### `phrases`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| phrase | String(255) | NOT NULL, unique |
| language | String(10) | default='en' |
| phrase_type | String(20) | nullable (idiom, phrasal_verb, collocation) |
| created_at | DateTime | default=now |

### `phrase_meanings`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| phrase_id | UUID | FK→phrases, CASCADE |
| definition | Text | NOT NULL |
| example_sentence | Text | nullable |
| order_index | Integer | default=0 |
| created_at | DateTime | default=now |

---

## Users & Learning

### `users`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| email | String(255) | NOT NULL, unique |
| password_hash | String(255) | NOT NULL |
| first_language | String(10) | default='en' |
| settings | JSON | default={} |
| role | String(20) | default='user' (user/admin/superadmin) |
| tier | String(20) | default='free' (free/premium) |
| is_active | Boolean | default=True |
| disabled_at | DateTime | nullable |
| disabled_by_id | UUID | FK→users, SET NULL |
| last_login_at | DateTime | nullable |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

### `user_meanings` (SM-2 learning queue)
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| meaning_id | UUID | FK→meanings, CASCADE |
| status | String(20) | default='learning' |
| notes | Text | nullable |
| ease_factor | Float | default=2.5 |
| interval_days | Integer | default=0 |
| repetitions | Integer | default=0 |
| next_review | DateTime | nullable |
| last_reviewed | DateTime | nullable |
| review_count | Integer | default=0 |
| correct_count | Integer | default=0 |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

Unique: (user_id, meaning_id)

### `review_history`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| meaning_id | UUID | FK→meanings, CASCADE |
| quality | Integer | NOT NULL (0-5) |
| review_type | String(20) | default='word_to_definition' |
| response_time_ms | Integer | nullable |
| reviewed_at | DateTime | default=now |

### `user_phrases` (SM-2 for phrases)
Same SM-2 fields as user_meanings but with phrase_id instead of meaning_id.
Unique: (user_id, phrase_id)

---

## Word Lists & Import

### `word_lists`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| name | String(255) | NOT NULL |
| description | Text | nullable |
| source_type | String(50) | nullable (epub, article, manual) |
| source_reference | Text | nullable |
| book_id | UUID | FK→books, SET NULL |
| created_at | DateTime | default=now |

### `word_list_items`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word_list_id | UUID | FK→word_lists, CASCADE |
| word_id | UUID | FK→words, CASCADE |
| context_sentence | Text | nullable |
| frequency_count | Integer | default=1 |
| variation_data | JSON | nullable |
| added_at | DateTime | default=now |

Unique: (word_list_id, word_id)

### `phrase_list_items`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word_list_id | UUID | FK→word_lists, CASCADE |
| phrase_id | UUID | FK→phrases, CASCADE |
| context_sentence | Text | nullable |
| frequency_count | Integer | default=1 |
| added_at | DateTime | default=now |

Unique: (word_list_id, phrase_id)

### `word_list_import_jobs`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| book_id | UUID | FK→books, SET NULL |
| word_list_id | UUID | FK→word_lists, SET NULL |
| status | String(20) | default='queued', indexed |
| list_name | String(255) | NOT NULL |
| list_description | Text | nullable |
| total_items | Integer | default=0 |
| processed_items | Integer | default=0 |
| created_count | Integer | default=0 |
| skipped_count | Integer | default=0 |
| not_found_count | Integer | default=0 |
| not_found_words | JSON | nullable |
| error_count | Integer | default=0 |
| error_message | Text | nullable |
| created_at | DateTime | default=now |
| started_at | DateTime | nullable |
| completed_at | DateTime | nullable |

---

## Concepts & Synsets

### `synsets`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| wn_synset | String(100) | NOT NULL, unique |
| pos | String(20) | nullable, indexed |
| gloss | Text | nullable |
| difficulty_score | Float | nullable |
| path_order | Integer | nullable, indexed |
| active | Boolean | default=True |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

### `synset_lemmas`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| synset_id | UUID | FK→synsets, CASCADE |
| word_id | UUID | FK→words, SET NULL |
| lemma_text | String(255) | NOT NULL, indexed |
| lemma_rank | Integer | default=0 |
| is_anchor | Boolean | default=False |
| created_at | DateTime | default=now |

Unique: (synset_id, lemma_text)

### `synset_edges`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| from_synset_id | UUID | FK→synsets, CASCADE |
| to_synset_id | UUID | FK→synsets, CASCADE |
| relation_type | String(50) | NOT NULL, indexed |
| weight | Float | default=1.0 |
| created_at | DateTime | default=now |

Unique: (from_synset_id, to_synset_id, relation_type)

### `synset_cluster_packs`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| synset_id | UUID | FK→synsets, CASCADE |
| version | String(50) | default='v1' |
| core_json | JSON | NOT NULL |
| contrast_json | JSON | nullable |
| phrases_json | JSON | nullable |
| metadata_json | JSON | nullable |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

Unique: (synset_id, version)

### `user_synset_mastery` (R/U/L dimensions)
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| synset_id | UUID | FK→synsets, CASCADE |
| status | String(20) | default='learning' |
| ease_factor | Float | default=2.5 |
| interval_days | Integer | default=0 |
| repetitions | Integer | default=0 |
| next_review | DateTime | nullable |
| last_reviewed | DateTime | nullable |
| review_count | Integer | default=0 |
| correct_count | Integer | default=0 |
| recognition_score | Float | default=0.0 |
| usage_score | Float | default=0.0 |
| listening_score | Float | default=0.0 |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

Unique: (user_id, synset_id)

### `concept_nodes`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| synset_id | UUID | FK→synsets, SET NULL |
| concept_key | String(255) | NOT NULL, unique |
| concept_type | String(30) | default='wordnet_synset' |
| language | String(10) | default='en' |
| canonical_label | String(255) | NOT NULL |
| definition_simple | Text | nullable |
| definition_full | Text | nullable |
| difficulty_level | Float | nullable |
| frequency_score | Float | nullable |
| formality | String(20) | nullable |
| usage_mode | String(20) | nullable |
| region_tags | JSON | nullable |
| metadata_json | JSON | nullable |
| active | Boolean | default=True |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

### `concept_expressions`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| concept_id | UUID | FK→concept_nodes, CASCADE |
| word_id | UUID | FK→words, SET NULL |
| phrase_id | UUID | FK→phrases, SET NULL |
| expression_text | String(255) | NOT NULL |
| expression_type | String(30) | default='word' |
| part_of_speech | String(20) | nullable |
| pronunciation | String(255) | nullable |
| is_primary | Boolean | default=False |
| register | String(20) | nullable |
| usage_mode | String(20) | nullable |
| frequency_score | Float | nullable |
| metadata_json | JSON | nullable |
| created_at | DateTime | default=now |

Unique: (concept_id, expression_text, expression_type)

### `concept_relations`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| from_concept_id | UUID | FK→concept_nodes, CASCADE |
| to_concept_id | UUID | FK→concept_nodes, CASCADE |
| relation_type | String(50) | NOT NULL |
| weight | Float | default=1.0 |
| source | String(50) | nullable |
| metadata_json | JSON | nullable |
| created_at | DateTime | default=now |

Unique: (from_concept_id, to_concept_id, relation_type)

### `concept_embeddings`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| concept_id | UUID | FK→concept_nodes, SET NULL |
| expression_id | UUID | FK→concept_expressions, SET NULL |
| embedding_model | String(100) | NOT NULL |
| embedding_vector | JSON | NOT NULL |
| created_at | DateTime | default=now |

### `user_concept_exposures`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| concept_id | UUID | FK→concept_nodes, CASCADE |
| channel | String(30) | NOT NULL (reading, review, story, listening) |
| context_type | String(30) | nullable |
| score | Float | nullable |
| metadata_json | JSON | nullable |
| created_at | DateTime | default=now |

---

## Concept Listening

### `concept_listening_items`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| synset_id | UUID | FK→synsets, CASCADE |
| audio_url | String(500) | NOT NULL |
| transcript | Text | NOT NULL |
| difficulty | String(20) | default='medium' |
| item_type | String(30) | default='sentence' |
| metadata_json | JSON | nullable |
| active | Boolean | default=True |
| created_at | DateTime | default=now |

### `user_concept_listening_reviews`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| listening_item_id | UUID | FK→concept_listening_items, CASCADE |
| synset_id | UUID | FK→synsets, CASCADE |
| quality | Integer | NOT NULL (0-5) |
| response_time_ms | Integer | nullable |
| reviewed_at | DateTime | default=now |

---

## Books & Media

### `books`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| content_hash | String(64) | NOT NULL, unique (SHA-256) |
| title | String(500) | nullable |
| author | String(500) | nullable |
| language | String(10) | default='en' |
| word_count | Integer | nullable |
| file_path | String(500) | nullable |
| uploaded_by | UUID | FK→users, SET NULL |
| created_at | DateTime | default=now |

### `book_caches`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| book_id | UUID | FK→books, CASCADE |
| processing_version | String(50) | default='v1' |
| processed_data | JSON | NOT NULL |
| created_at | DateTime | default=now |

### `audio_cache`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word | String(255) | nullable |
| word_context | String(500) | nullable |
| definition | Text | nullable |
| example | Text | nullable |
| audio_type | String(20) | NOT NULL |
| provider | String(50) | NOT NULL |
| voice_id | String(100) | nullable |
| file_path | String(500) | NOT NULL |
| created_at | DateTime | default=now |

### `image_cache`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| word | String(255) | NOT NULL |
| meaning_id | UUID | FK→meanings, SET NULL |
| provider | String(50) | NOT NULL |
| style | String(50) | NOT NULL |
| prompt | Text | nullable |
| file_path | String(500) | NOT NULL |
| created_at | DateTime | default=now |

### `media_generation_jobs`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| job_type | String(30) | NOT NULL (audio, image) |
| status | String(20) | default='pending' |
| priority | Integer | default=100 |
| params | JSON | NOT NULL |
| result | JSON | nullable |
| error_message | Text | nullable |
| created_by | UUID | FK→users, SET NULL |
| created_at | DateTime | default=now |
| started_at | DateTime | nullable |
| completed_at | DateTime | nullable |

---

## Stories

### `stories`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE |
| title | String(500) | NOT NULL |
| content | Text | NOT NULL |
| cefr_level | String(10) | nullable |
| vocabulary_words | JSON | NOT NULL |
| llm_provider | String(50) | nullable |
| audio_path | String(500) | nullable |
| cover_image_path | String(500) | nullable |
| podcast_transcript | Text | nullable |
| podcast_audio_path | String(500) | nullable |
| podcast_hosts | JSON | nullable |
| podcast_segments | JSON | nullable |
| created_at | DateTime | default=now |

### `story_versions`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| story_id | UUID | FK→stories, CASCADE |
| version_number | Integer | NOT NULL |
| content | Text | NOT NULL |
| audio_path | String(500) | nullable |
| segments | JSON | nullable |
| created_at | DateTime | default=now |

Unique: (story_id, version_number)

### `podcast_versions`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| story_id | UUID | FK→stories, CASCADE |
| version_number | Integer | NOT NULL |
| transcript | Text | NOT NULL |
| audio_path | String(500) | nullable |
| hosts | JSON | nullable |
| segments | JSON | nullable |
| created_at | DateTime | default=now |

Unique: (story_id, version_number)

### `podcast_settings`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK→users, CASCADE, unique |
| host_count | Integer | default=2 |
| host_voices | JSON | nullable |
| style | String(50) | default='conversational' |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

---

## Admin

### `audit_log`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| action | String(50) | NOT NULL, indexed |
| resource_type | String(50) | NOT NULL, indexed |
| resource_id | String(255) | nullable |
| user_id | UUID | FK→users, SET NULL |
| changes | JSON | nullable |
| ip_address | String(45) | nullable |
| created_at | DateTime | default=now, indexed |

### `app_settings`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| category | String(50) | NOT NULL |
| key | String(100) | NOT NULL |
| value | Text | nullable |
| value_type | String(20) | default='string' |
| description | Text | nullable |
| updated_by | UUID | FK→users, SET NULL |
| created_at | DateTime | default=now |
| updated_at | DateTime | default=now, onupdate |

Unique: (category, key)
