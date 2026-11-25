import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_place_fields as P


class BannerCenter(unittest.TestCase):
    def test_even_lengths_are_exact(self):
        for n in range(2, 17, 2):
            self.assertEqual(P.banner_skew(n), 0)

    def test_odd_is_half_half_cell(self):
        self.assertEqual(P.banner_skew(11), 3)  # 반각 한 칸 쏠림 = 3px ≤ 6px

    def test_overflow_and_catch(self):
        self.assertIsNone(P.banner_skew(18))
        d = {"/x": b"\x00" * 4 + b"\x88\x40" * 9 + b"\x00"}  # 18B — 틀 폭 초과
        _w, bad = P.banner_check([("/x", 4, 24, "가", "/x 헤더 0x4")], d)
        self.assertEqual(len(bad), 1)


if __name__ == "__main__":
    unittest.main()
