import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nir2_demo import age_eligible, indicators, shortest_times, interval_union_eligible, group_date_state
from datetime import date


class DemoTests(unittest.TestCase):
    def test_partial_bounds_rule_out_but_cannot_confirm(self):
        self.assertFalse(age_eligible(12, None, 10))
        self.assertFalse(age_eligible(7, 10, None))
        self.assertIsNone(age_eligible(7, None, 10))
        for bound in [float('nan'), float('inf'), -1, True]:
            with self.assertRaises(ValueError):
                age_eligible(8, bound, None)

    def test_unknown_age_bounds_apply_to_known_locations_only(self):
        programs = [{'id': 1, 'site': 'S', 'min_age': 7, 'max_age': 17},
                    {'id': 2, 'site': 'S', 'min_age': None, 'max_age': None},
                    {'id': 3, 'site': 'T', 'min_age': None, 'max_age': None},
                    {'id': 4, 'site': 'NO_LOCATION', 'min_age': None, 'max_age': None}]
        result = indicators(programs, {'S': 5, 'T': 10}, 8, 10)
        self.assertEqual((result['sites'], result['sites_possible_known_locations']), (1, 2))

    def test_multiple_profiles_and_invalid_costs(self):
        programs = [{'id': 1, 'site': 'S', 'profiles': ['music', 'art'], 'min_age': 7, 'max_age': 17}]
        self.assertEqual(indicators(programs, {'S': 5}, 8, 10)['profiles'], 2)
        self.assertIn('"art": 5', indicators(programs, {'S': 5}, 8, 10)['nearest_by_profile_json'])
        with self.assertRaises(ValueError):
            indicators([{**programs[0], 'profiles': 'art'}], {'S': 5}, 8, 10)
        for threshold in [float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                indicators(programs, {'S': 5}, 8, threshold)
        for cost in [float('nan'), -1]:
            with self.assertRaises(ValueError):
                indicators(programs, {'S': cost}, 8, 10)

    def test_reversed_dates_are_errors_not_expired_groups(self):
        with self.assertRaises(ValueError):
            group_date_state({'lesson_start': '2027-01-01', 'lesson_end': '2026-01-01'}, date(2026, 10, 20))

    def test_unknown_profile_does_not_remove_known_age_site(self):
        programs = [{'id': 1, 'site': 'S', 'profile': None, 'min_age': 7, 'max_age': 17}]
        metric = indicators(programs, {'S': 5}, 8, 10)
        self.assertEqual(metric['sites'], 1)
        self.assertEqual(metric['profiles'], 0)
        self.assertEqual(metric['reachable_known_age_programs_unknown_profile'], 1)
        self.assertEqual(metric['nearest_status'], 'computed_in_supplied_graph')

    def test_group_union_does_not_bridge_age_gap(self):
        self.assertFalse(interval_union_eligible(11, [(7, 9), (13, 17)]))
        self.assertTrue(interval_union_eligible(14, [(7, 9), (13, 17)]))
        self.assertIsNone(interval_union_eligible(11, [(7, 9), (None, None)]))
        self.assertIsNone(interval_union_eligible(11, []))

    def test_group_dates_do_not_promote_unknown_to_active(self):
        snapshot = date(2026, 10, 20)
        self.assertEqual(group_date_state({'lesson_start': '2024-09-01', 'lesson_end': '2025-05-23'}, snapshot),
                         'ended_before_snapshot')
        self.assertEqual(group_date_state({'lesson_start': '2026-09-01', 'lesson_end': ''}, snapshot),
                         'incomplete_dates_unknown_activity')
        self.assertEqual(group_date_state({'lesson_start': '2026-09-01', 'lesson_end': '2027-05-31'}, snapshot),
                         'date_interval_covers_snapshot')

    def test_age_boundaries_and_unknown(self):
        self.assertTrue(age_eligible(7, '7.0', '10.0'))
        self.assertTrue(age_eligible(10, 7, 10))
        self.assertFalse(age_eligible(11, 7, 10))
        self.assertIsNone(age_eligible(8, None, 10))
        with self.assertRaises(ValueError):
            age_eligible(8, 10, 7)

    def test_shortest_path_and_directed_unreachability(self):
        result = shortest_times([('A', 'B', 9), ('A', 'C', 2), ('C', 'B', 3)], 'A')
        self.assertEqual(result['B'], 5)
        self.assertNotIn('A', shortest_times([('A', 'B', 9)], 'B'))
        with self.assertRaises(ValueError):
            shortest_times([('A', 'B', -1)], 'A')

    def test_duplicate_programs_do_not_duplicate_sites(self):
        programs = [{'id': i, 'site': 'S', 'profile': 'music', 'min_age': 7, 'max_age': 17} for i in [1, 2]]
        metric = indicators(programs, {'S': 10}, 8, 10)
        self.assertEqual((metric['programs'], metric['sites'], metric['profiles']), (2, 1, 1))
        self.assertEqual(indicators(programs, {}, 8, 10)['nearest_minutes'], None)
        self.assertEqual(indicators(programs, {}, 8, 10)['nearest_status'], 'no_route_in_supplied_graph')

    def test_budget_monotonicity_and_age_not_monotone_by_construction(self):
        programs = [{'id': 1, 'site': 'S', 'profile': 'music', 'min_age': 7, 'max_age': 10}]
        small = indicators(programs, {'S': 12}, 8, 10)
        large = indicators(programs, {'S': 12}, 8, 20)
        self.assertLessEqual(small['sites'], large['sites'])
        self.assertEqual(large['sites'], 1)
        self.assertEqual(indicators(programs, {'S': 12}, 14, 20)['sites'], 0)

    def test_unknown_age_not_zero_or_eligible(self):
        programs = [{'id': 1, 'site': 'S', 'profile': 'music', 'min_age': None, 'max_age': None}]
        metric = indicators(programs, {'S': 1}, 8, 10)
        self.assertEqual(metric['sites'], 0)
        self.assertEqual(metric['reachable_unknown_age_programs'], 1)


if __name__ == '__main__':
    unittest.main()
