"""지명 배너 판별 — 화자 이름(「폴티아 병사」)과 섞이지 않는다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import banner


class PlaceBanner(unittest.TestCase):
    def test_region_banner_is_detected(self):
        self.assertTrue(banner.is_place_banner("폴티아　루데라 관문"))
        self.assertTrue(banner.is_place_banner("메나트−챠놈　쌍룡곡 관문"))
        self.assertTrue(banner.is_place_banner("메나트　네갈섬　테그라"))

    def test_speaker_names_are_not_banners(self):
        self.assertFalse(banner.is_place_banner("폴티아 병사"))  # 반각 공백 — 화자 이름
        self.assertFalse(banner.is_place_banner("우돌 입국계원"))
        self.assertFalse(banner.is_place_banner("후우　깜짝 놀랐어."))

    def test_multiline_is_not_banner(self):
        self.assertFalse(banner.is_place_banner("폴티아　루데라\n관문"))

    def test_normalize_makes_space_half_width(self):
        self.assertEqual(banner.normalize("폴티아　루데라 관문"), "폴티아 루데라 관문")


if __name__ == "__main__":
    unittest.main()
