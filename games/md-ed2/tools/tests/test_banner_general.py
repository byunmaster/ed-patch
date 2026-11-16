"""입장 배너 일반 꼴(띄어쓰기, 마스터 11-09) — 성 붙임 · 홀수 칸은 왼쪽 올림 · 가운데최근접 판정."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banners
import typeset_audit


class BannerGeneral(unittest.TestCase):
    def test_general_forms(self):
        self.assertEqual(banners.kr_general("ルディアの町"), "루디아 마을")
        self.assertEqual(banners.kr_general("ルディアの城"), "루디아성")  # 성은 붙임
        self.assertEqual(banners.kr_general("岬の洞窟"), "곶의 동굴")
        # 정본 전체 원문엔 없고 앞말 + 접미로 만든다
        self.assertEqual(banners.kr_general("エルアスタの町"), "엘아스타 마을")

    def test_nearest_gate(self):
        self.assertTrue(typeset_audit.not_nearest(-11, 8))  # 한 칸 옮기면 +5
        self.assertFalse(typeset_audit.not_nearest(5, 8))
        self.assertTrue(typeset_audit.not_nearest(6, 6))  # 같은 거리면 왼쪽
        self.assertFalse(typeset_audit.not_nearest(-6, 6))


if __name__ == "__main__":
    unittest.main()
