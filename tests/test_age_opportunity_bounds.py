import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd


class OpportunityBoundsTests(unittest.TestCase):
    def test_unknown_ages_do_not_become_confirmed_or_unique_sites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame([[5, 12], [20, 1]], index=[0, 1], columns=['a', 'b']).to_csv(root / 'matrix.csv')
            pd.DataFrame([
                {'program_id': 1, 'location_id': 'a', 'min_age': 6, 'max_age': 9, 'card_age_state': 'known_interval'},
                {'program_id': 2, 'location_id': 'a', 'min_age': '', 'max_age': '', 'card_age_state': 'card_not_yet_available'},
                {'program_id': 3, 'location_id': 'b', 'min_age': 10, 'max_age': 16, 'card_age_state': 'known_interval'},
            ]).to_csv(root / 'links.csv', index=False)
            script = Path(__file__).resolve().parents[1] / 'src' / 'calculate_age_opportunity_bounds.py'
            subprocess.run([sys.executable, str(script), '--matrix', str(root / 'matrix.csv'),
                            '--links', str(root / 'links.csv'), '--output', str(root / 'result')],
                           check=True, capture_output=True, text=True)
            result = pd.read_csv(root / 'result' / 'by-origin.csv')
            row = result[(result.age == 7) & (result.threshold_minutes == 10) & (result.origin_matrix_index == 0)].iloc[0]
            self.assertEqual(row.known_eligible_programs, 1)
            self.assertEqual(row.possibly_eligible_programs, 2)
            self.assertEqual(row.known_eligible_coordinates, 1)
            self.assertEqual(row.possibly_eligible_coordinates, 1)
            row = result[(result.age == 7) & (result.threshold_minutes == 10) & (result.origin_matrix_index == 1)].iloc[0]
            self.assertEqual(row.possibly_eligible_programs, 0)


if __name__ == '__main__':
    unittest.main()
