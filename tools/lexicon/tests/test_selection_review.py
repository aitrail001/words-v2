import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lexicon.selection_review import prepare_review, score_selection_risk


class SelectionReviewTests(unittest.TestCase):
    def _write_snapshot(self, snapshot_dir: Path) -> None:
        lexemes = [
            {
                'snapshot_id': 'snap-1',
                'lexeme_id': 'lx_run',
                'lemma': 'run',
                'language': 'en',
                'wordfreq_rank': 5000,
                'is_wordnet_backed': True,
                'source_refs': ['wordnet', 'wordfreq'],
                'created_at': '2026-03-08T00:00:00Z',
            },
            {
                'snapshot_id': 'snap-1',
                'lexeme_id': 'lx_bank',
                'lemma': 'bank',
                'language': 'en',
                'wordfreq_rank': 1200,
                'is_wordnet_backed': True,
                'source_refs': ['wordnet', 'wordfreq'],
                'created_at': '2026-03-08T00:00:00Z',
            },
            {
                'snapshot_id': 'snap-1',
                'lexeme_id': 'lx_case',
                'lemma': 'case',
                'language': 'en',
                'wordfreq_rank': 900,
                'is_wordnet_backed': True,
                'source_refs': ['wordnet', 'wordfreq'],
                'created_at': '2026-03-08T00:00:00Z',
            },
        ]
        senses = [
            {
                'snapshot_id': 'snap-1',
                'sense_id': 'sn_lx_run_1',
                'lexeme_id': 'lx_run',
                'wn_synset_id': 'run.v.01',
                'part_of_speech': 'verb',
                'canonical_gloss': 'move fast by using your legs',
                'selection_reason': 'selected canonical learner sense',
                'sense_order': 1,
                'is_high_polysemy': False,
                'created_at': '2026-03-08T00:00:00Z',
            },
            {
                'snapshot_id': 'snap-1',
                'sense_id': 'sn_lx_run_2',
                'lexeme_id': 'lx_run',
                'wn_synset_id': 'run.n.01',
                'part_of_speech': 'noun',
                'canonical_gloss': 'a period of running',
                'selection_reason': 'selected canonical learner sense',
                'sense_order': 2,
                'is_high_polysemy': False,
                'created_at': '2026-03-08T00:00:00Z',
            },
        ]
        for index in range(1, 7):
            senses.append(
                {
                    'snapshot_id': 'snap-1',
                    'sense_id': f'sn_lx_bank_{index}',
                    'lexeme_id': 'lx_bank',
                    'wn_synset_id': f'bank.n.0{index}',
                    'part_of_speech': 'noun',
                    'canonical_gloss': f'bank meaning {index}',
                    'selection_reason': 'selected canonical learner sense',
                    'sense_order': index,
                    'is_high_polysemy': True,
                    'created_at': '2026-03-08T00:00:00Z',
                }
            )
        for index in range(1, 5):
            senses.append(
                {
                    'snapshot_id': 'snap-1',
                    'sense_id': f'sn_lx_case_{index}',
                    'lexeme_id': 'lx_case',
                    'wn_synset_id': f'case.n.0{index}',
                    'part_of_speech': 'noun',
                    'canonical_gloss': f'case meaning {index}',
                    'selection_reason': 'selected canonical learner sense',
                    'sense_order': index,
                    'is_high_polysemy': True,
                    'created_at': '2026-03-08T00:00:00Z',
                }
            )
        (snapshot_dir / 'lexemes.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in lexemes), encoding='utf-8')
        (snapshot_dir / 'senses.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in senses), encoding='utf-8')

    def _sense_provider(self, lemma: str) -> list[dict[str, object]]:
        if lemma == 'run':
            return [
                {'query_lemma': 'run', 'wn_synset_id': 'run.v.01', 'part_of_speech': 'verb', 'canonical_gloss': 'move fast by using your legs', 'canonical_label': 'run', 'lemma_count': 20},
                {'query_lemma': 'run', 'wn_synset_id': 'run.n.01', 'part_of_speech': 'noun', 'canonical_gloss': 'a period of running', 'canonical_label': 'run', 'lemma_count': 10},
            ]
        if lemma == 'bank':
            return [
                {'query_lemma': 'bank', 'wn_synset_id': f'bank.n.{index:02d}', 'part_of_speech': 'noun', 'canonical_gloss': f'financial bank meaning {index}', 'canonical_label': 'bank', 'lemma_count': max(1, 20 - index)}
                for index in range(1, 13)
            ]
        if lemma == 'case':
            rows = [
                {'query_lemma': 'case', 'wn_synset_id': f'case.n.{index:02d}', 'part_of_speech': 'noun', 'canonical_gloss': f'general case meaning {index}', 'canonical_label': 'case', 'lemma_count': max(1, 18 - index)}
                for index in range(1, 11)
            ]
            rows.extend([
                {'query_lemma': 'case', 'wn_synset_id': 'case.v.01', 'part_of_speech': 'verb', 'canonical_gloss': 'look over with the intention to rob', 'canonical_label': 'case', 'lemma_count': 8},
                {'query_lemma': 'case', 'wn_synset_id': 'encase.v.01', 'part_of_speech': 'verb', 'canonical_gloss': 'enclose in a case', 'canonical_label': 'encase', 'lemma_count': 6},
            ])
            return rows
        raise AssertionError(f'unexpected lemma: {lemma}')

    def test_score_selection_risk_writes_selection_decisions_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            result = score_selection_risk(snapshot_dir, sense_provider=self._sense_provider, candidate_limit=8)

            self.assertTrue(result.output_path.exists())
            rows = [json.loads(line) for line in result.output_path.read_text(encoding='utf-8').splitlines() if line.strip()]
            self.assertEqual(len(rows), 3)
            by_lemma = {row['lemma']: row for row in rows}

            self.assertEqual(by_lemma['run']['schema_version'], 'lexicon_selection_decision.v1')
            self.assertEqual(by_lemma['run']['risk_band'], 'deterministic_only')
            self.assertFalse(by_lemma['run']['rerank_recommended'])
            self.assertFalse(by_lemma['run']['review_required'])
            self.assertEqual(by_lemma['bank']['risk_band'], 'rerank_recommended')
            self.assertTrue(by_lemma['bank']['rerank_recommended'])
            self.assertEqual(by_lemma['case']['risk_band'], 'rerank_and_review_candidate')
            self.assertEqual(by_lemma['bank']['candidate_pool_count'], 8)
            self.assertTrue(by_lemma['bank']['candidate_metadata'])
            self.assertIn('selection_risk_score', by_lemma['bank'])
            self.assertIn('selection_risk_reasons', by_lemma['bank'])
            self.assertIsInstance(by_lemma['bank'].get('generated_at'), str)
            self.assertTrue(by_lemma['bank'].get('generated_at'))
            self.assertIsInstance(by_lemma['bank'].get('generation_run_id'), str)
            self.assertTrue(by_lemma['bank'].get('generation_run_id'))

            first_candidate = by_lemma['bank']['candidate_metadata'][0]
            self.assertEqual(
                set(first_candidate),
                {
                    'wn_synset_id',
                    'part_of_speech',
                    'canonical_label',
                    'canonical_gloss',
                    'lemma_count',
                    'query_lemma',
                    'deterministic_score',
                    'deterministic_rank',
                    'deterministic_selected',
                    'rerank_exposed',
                    'rerank_selected',
                    'candidate_flags',
                },
            )

    def test_prepare_review_reranks_only_risky_words_and_auto_accepts_stable_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            decisions_result = score_selection_risk(snapshot_dir, sense_provider=self._sense_provider, candidate_limit=8)
            review_queue_output = snapshot_dir / 'review_queue.jsonl'

            def fake_run_rerank(snapshot_dir_arg, **kwargs):
                self.assertEqual(snapshot_dir_arg, snapshot_dir)
                self.assertEqual(set(kwargs['words']), {'bank', 'case'})
                output_path = Path(kwargs['output_path'])
                output_path.write_text('', encoding='utf-8')
                return type(
                    'FakeRerankRunResult',
                    (),
                    {
                        'output_path': output_path,
                        'rows': [
                            {
                                'lexeme_id': 'lx_bank',
                                'lemma': 'bank',
                                'candidate_wn_synset_ids': [f'bank.n.{index:02d}' for index in range(1, 9)],
                                'selected_wn_synset_ids': ['bank.n.01', 'bank.n.02', 'bank.n.03', 'bank.n.04', 'bank.n.05', 'bank.n.07'],
                            },
                            {
                                'lexeme_id': 'lx_case',
                                'lemma': 'case',
                                'candidate_wn_synset_ids': ['case.n.01', 'case.n.02', 'case.n.03', 'case.n.04', 'case.n.05', 'case.n.06', 'case.v.01', 'encase.v.01'],
                                'selected_wn_synset_ids': ['case.n.05', 'case.n.06', 'case.v.01', 'encase.v.01'],
                            },
                        ],
                    },
                )()

            with patch('tools.lexicon.selection_review.run_rerank', side_effect=fake_run_rerank):
                result = prepare_review(
                    snapshot_dir,
                    decisions_path=decisions_result.output_path,
                    review_queue_output=review_queue_output,
                    candidate_limit=8,
                    candidate_source='candidates',
                )

            by_lemma = {row['lemma']: row for row in result.rows}
            self.assertFalse(by_lemma['run']['rerank_applied'])
            self.assertTrue(by_lemma['bank']['rerank_applied'])
            self.assertTrue(by_lemma['bank']['auto_accepted'])
            self.assertFalse(by_lemma['bank']['review_required'])
            self.assertEqual(by_lemma['bank']['replacement_count'], 1)
            self.assertTrue(by_lemma['case']['rerank_applied'])
            self.assertFalse(by_lemma['case']['auto_accepted'])
            self.assertTrue(by_lemma['case']['review_required'])
            self.assertTrue(result.review_queue_output and result.review_queue_output.exists())
            review_rows = [json.loads(line) for line in review_queue_output.read_text(encoding='utf-8').splitlines() if line.strip()]
            self.assertEqual([row['lemma'] for row in review_rows], ['case'])

    def test_prepare_review_marks_high_frequency_substantial_changes_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            decisions_result = score_selection_risk(snapshot_dir, sense_provider=self._sense_provider, candidate_limit=8)
            review_queue_output = snapshot_dir / 'review_queue.jsonl'

            decision_rows = [
                row
                for row in (json.loads(line) for line in decisions_result.output_path.read_text(encoding='utf-8').splitlines() if line.strip())
                if row['lemma'] == 'bank'
            ]
            bank_only_decisions_path = snapshot_dir / 'selection_decisions.bank-only.jsonl'
            bank_only_decisions_path.write_text(''.join(json.dumps(row) + '\n' for row in decision_rows), encoding='utf-8')

            def fake_run_rerank(snapshot_dir_arg, **kwargs):
                self.assertEqual(snapshot_dir_arg, snapshot_dir)
                self.assertEqual(kwargs['words'], ['bank'])
                output_path = Path(kwargs['output_path'])
                output_path.write_text('', encoding='utf-8')
                return type(
                    'FakeRerankRunResult',
                    (),
                    {
                        'output_path': output_path,
                        'rows': [
                            {
                                'lexeme_id': 'lx_bank',
                                'lemma': 'bank',
                                'candidate_wn_synset_ids': [f'bank.n.{index:02d}' for index in range(1, 9)],
                                'selected_wn_synset_ids': ['bank.n.01', 'bank.n.02', 'bank.n.03', 'bank.n.04', 'bank.n.07', 'bank.n.08'],
                            },
                        ],
                    },
                )()

            with patch('tools.lexicon.selection_review.run_rerank', side_effect=fake_run_rerank):
                result = prepare_review(
                    snapshot_dir,
                    decisions_path=bank_only_decisions_path,
                    review_queue_output=review_queue_output,
                    candidate_limit=8,
                    candidate_source='candidates',
                )

            self.assertEqual(len(result.rows), 1)
            bank_row = result.rows[0]
            self.assertTrue(bank_row['rerank_applied'])
            self.assertEqual(bank_row['replacement_count'], 2)
            self.assertIn('high_frequency_substantial_change', bank_row['review_reasons'])
            self.assertFalse(bank_row['auto_accepted'])
            self.assertTrue(bank_row['review_required'])
            self.assertEqual([row['lemma'] for row in result.review_rows], ['bank'])
            review_rows = [json.loads(line) for line in review_queue_output.read_text(encoding='utf-8').splitlines() if line.strip()]
            self.assertEqual([row['lemma'] for row in review_rows], ['bank'])


if __name__ == '__main__':
    unittest.main()
