"""스태프롤 이름 한글화(마스터 10-16, 규칙 3-7) — 글리프 한도 · 줄 폭 · 영문 유지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ending as en


class StaffNames(unittest.TestCase):
    def test_이름은_한글_영문_기호뿐이다(self):
        for jp, ko in en.NAMES.items():
            for ch in ko:
                self.assertTrue("가" <= ch <= "힣" or ord(ch) < 0x80 or ch in "（）", (jp, ko, ch))

    def test_줄_폭이_시작_x124_에서_한계_안이다(self):
        """가장 앞 칸(`09` 없이)에서 시작해도 248px 안 — 길면 build 가 줄을 나눠 아래가 밀린다."""
        for jp, ko in en.NAMES.items():
            self.assertLessEqual(en.X0 + en._text_px(ko), en.LINE_LIMIT, (jp, ko))

    def test_영문_약칭은_그대로_둔다(self):
        for keep in ("J.D.K", "CD-AUDIO", "PSG", "ADPCM"):
            self.assertNotIn(keep, en.NAMES)


if __name__ == "__main__":
    unittest.main()
