from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audit_program_group_ages import group_eligibility


class GroupAgeTests(unittest.TestCase):
    def test_hidden_or_incomplete_age_interval_remains_unknown(self):
        self.assertIsNone(group_eligibility(7, {'is_age_limit': False, 'min_age': 8, 'max_age': 16}))
        self.assertIsNone(group_eligibility(7, {'min_age': 6, 'max_age': 8}))
        self.assertIsNone(group_eligibility(7, {'is_age_limit': True, 'min_age': 6, 'max_age': None}))
        self.assertFalse(group_eligibility(7, {'is_age_limit': True, 'min_age': 8, 'max_age': 16}))
        self.assertTrue(group_eligibility(7, {'is_age_limit': True, 'min_age': 6, 'max_age': 8}))


if __name__ == '__main__':
    unittest.main()
