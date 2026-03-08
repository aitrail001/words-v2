# Lexicon Sense Selection Rubric

Use this rubric for both deterministic selector tuning and optional LLM rerank evaluation.

## Core learner-priority rules

1. Prefer broad, everyday meanings over niche or specialized meanings.
2. Prefer meanings a learner is likely to meet early in general reading/listening.
3. Prefer grounded WordNet senses tied to the queried lemma, not distant alias-like synsets.
4. Prefer practical general-use noun/adjective/verb senses over technical, sports-only, legal-only, geographic, or body-part-only tails.
5. Keep diversity soft: allow multiple senses from the same POS when they are genuinely strong, but avoid weak same-POS tails crowding out better mixed-POS senses.

## Common demotions

- specialized sports/game/tournament senses
- technical/scientific/mechanical senses
- obscure geographic/land-use senses
- body-part-only adjective readings
- low-value control/obedience/punishment tails
- alias-like synsets whose canonical label is far from the queried lemma

## Comparison use

When comparing deterministic selection against LLM rerank, judge whether the reranked set improves:
- everydayness
- general learner utility
- groundedness to the queried lemma
- mixed-POS usefulness when appropriate
- tail-sense suppression
