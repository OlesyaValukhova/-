import unittest
from make_citywide_b3_points_v32 import classify_count, classify_delta, classify_origin, project_utm36


class TestCitywideB3PointMap(unittest.TestCase):
    def test_count_breaks(self):
        self.assertEqual(classify_count(0), "0")
        self.assertEqual(classify_count(10), "1–10")
        self.assertEqual(classify_count(11), "11–30")
        self.assertEqual(classify_count(30), "11–30")
        self.assertEqual(classify_count(31), "31–60")
        self.assertEqual(classify_count(61), ">60")

    def test_delta_breaks(self):
        self.assertEqual(classify_delta(-20), "≤−20")
        self.assertEqual(classify_delta(-10), "−19…−10")
        self.assertEqual(classify_delta(-1), "−9…−1")
        self.assertEqual(classify_delta(0), "0")
        self.assertEqual(classify_delta(1), ">0")

    def test_uncovered_is_not_zero(self):
        self.assertEqual(
            classify_origin(False, None, None),
            ("нет покрытия", "нет покрытия", "нет покрытия", None),
        )

    def test_covered_missing_value_fails(self):
        with self.assertRaises(ValueError):
            classify_origin(True, 2, None)

    def test_projection_is_spb_utm36(self):
        x, y = project_utm36(30.284234, 59.940658)
        self.assertTrue(300000 < x < 400000)
        self.assertTrue(6600000 < y < 6700000)


if __name__ == "__main__":
    unittest.main()
