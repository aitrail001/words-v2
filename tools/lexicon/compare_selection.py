from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import json

from tools.lexicon.enrich import read_snapshot_inputs


def compare_selection_artifacts(snapshot_dir: Path, rerank_file: Path, *, output_path: Path | None = None) -> dict[str, Any]:
    lexemes, senses = read_snapshot_inputs(snapshot_dir)
    lemma_by_id = {lexeme.lexeme_id: lexeme.lemma for lexeme in lexemes}
    deterministic_by_lexeme: dict[str, list[str]] = defaultdict(list)
    for sense in sorted(senses, key=lambda item: (item.lexeme_id, item.sense_order)):
        if sense.wn_synset_id:
            deterministic_by_lexeme[sense.lexeme_id].append(sense.wn_synset_id)

    reranks = [json.loads(line) for line in rerank_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    changes: list[dict[str, Any]] = []
    compared = 0
    for row in reranks:
        lexeme_id = str(row.get('lexeme_id') or '')
        reranked = [str(item) for item in row.get('selected_wn_synset_ids') or []]
        deterministic = deterministic_by_lexeme.get(lexeme_id, [])
        if not lexeme_id or not deterministic:
            continue
        compared += 1
        if reranked != deterministic:
            changes.append({
                'lexeme_id': lexeme_id,
                'lemma': lemma_by_id.get(lexeme_id, row.get('lemma') or lexeme_id),
                'deterministic_wn_synset_ids': deterministic,
                'reranked_wn_synset_ids': reranked,
                'added_wn_synset_ids': [item for item in reranked if item not in deterministic],
                'dropped_wn_synset_ids': [item for item in deterministic if item not in reranked],
            })

    payload = {
        'compared_lexeme_count': compared,
        'changed_lexeme_count': len(changes),
        'changes': changes,
    }
    if output_path is not None:
        output_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return payload
