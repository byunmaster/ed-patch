"""HUD 상태 라벨(C4·방어) — **원본 없이** 돈다. 일본어가 프레임에 남지 않게 지킨다(2026-10-09 「まもる」)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hud_status


class HudStatus(unittest.TestCase):
    def test_프레임마다_한글_라벨이_있고_글자는_타일을_받는다(self):
        for kr, orig in hud_status.FRAMES:
            self.assertEqual(len(bytes.fromhex(orig)), 2 * hud_status.FRAME_WORDS, kr)
            for c in kr:
                self.assertIn(c, hud_status.TILE_OF, f"{kr}: {c} 에 타일이 없다")

    def test_타일은_겹치지_않는다(self):
        ts = list(hud_status.TILE_OF.values())
        self.assertEqual(len(ts), len(set(ts)))

    def test_타일_원본_자리가_있다(self):
        for t in hud_status.TILE_OF.values():
            hud_status.TILE_SRC(t)  # 모르는 번호면 예외

    def test_도안이_글자_열둘과_같다(self):
        self.assertEqual(sorted(hud_status.load()), sorted(hud_status.chars()))

    def test_프레임_워드는_팔레트를_살리고_남는_칸은_빈_칸(self):
        orig = bytes.fromhex(hud_status.FRAMES[6][1])  # 방어 프레임 — 노랑 팔레트(0x0C)
        w = hud_status.frame_words("방어", orig)
        self.assertEqual(len(w), 2 * hud_status.FRAME_WORDS)
        self.assertEqual(w[1] & 0x0C, 0x0C)
        self.assertEqual(w[4:6], b"\x27\x00")

    def test_원본_타일_번호는_한글_라벨_뒤_프레임에_안_남는다(self):
        for kr, orig in hud_status.FRAMES:
            w = hud_status.frame_words(kr, bytes.fromhex(orig))
            n = len(kr)
            self.assertEqual(w[2 * n :], b"\x27\x00" * (hud_status.FRAME_WORDS - n))


if __name__ == "__main__":
    unittest.main()
