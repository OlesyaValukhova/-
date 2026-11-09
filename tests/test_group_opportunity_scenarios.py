import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd


class GroupScenarioTests(unittest.TestCase):
    def test_strict_scenario_counts_programs_once_and_requires_visible_group_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pd.DataFrame([[5, 5]], index=[0], columns=['a', 'b']).to_csv(root / 'matrix.csv')
            pd.DataFrame([{'program_id': 1, 'location_id': 'a', 'payment_label': 'free'},
                          {'program_id': 2, 'location_id': 'b', 'payment_label': 'paid'}]).to_csv(root / 'links.csv', index=False)
            cards = root / 'cards'
            cards.mkdir()
            group = {'is_age_limit': True, 'min_age': 6, 'max_age': 10,
                     'lesson_start': '2026-09-01', 'lesson_end': '2026-12-01'}
            for item_id, groups in [(1, [group, group]), (2, [{**group, 'is_age_limit': False}])]:
                (cards / f'{item_id}-detail.json').write_text(json.dumps({
                    'id': item_id, 'min_age': 6, 'max_age': 10, 'groups': groups,
                    'payment': item_id, 'directivity': {'display_name': 'art'}}), encoding='utf-8')
            script = Path(__file__).resolve().parents[1] / 'src' / 'compare_group_opportunity_scenarios.py'
            subprocess.run([sys.executable, str(script), '--matrix', str(root / 'matrix.csv'),
                            '--links', str(root / 'links.csv'), '--details', str(cards),
                            '--as-of', '2026-11-09', '--output', str(root / 'out')],
                           check=True, capture_output=True, text=True)
            df = pd.read_csv(root / 'out' / 'summary.csv')
            rows = df[(df.age == 7) & (df.threshold_minutes == 10) & (df.category_kind == 'all')]
            results = dict(zip(rows.scenario, rows.median_reachable_programs))
            self.assertEqual(results, {'programme_age': 2.0, 'programme_and_group_intervals': 1.0})


if __name__ == '__main__':
    unittest.main()
