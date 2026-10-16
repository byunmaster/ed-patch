"""시스템 카드 안내문 — 칸 수·후킹 크기·빈 자리 안에 드는지(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import syscard


class SysCard(unittest.TestCase):
    def test_메시지는_두_줄_14칸이고_원본_칸_수_안이다(self):
        for mi, (msg, n) in enumerate(zip(syscard.MESSAGES, syscard.MSG_LEN, strict=True)):
            cs = syscard.cells_of(msg, mi)
            self.assertEqual(len(cs), 28)
            self.assertLessEqual(2 * len(cs) + 2, n)

    def test_글리프_표와_후킹이_빈_자리에_든다(self):
        specs, idx = syscard.glyph_set()
        hook = syscard.hook_code(syscard.BASE + syscard.HOOK_OFF)
        self.assertLessEqual(syscard.HOOK_OFF + len(hook) + 24 * len(specs), syscard.FREE_END)
        self.assertLess(len(specs), 0xE0 - syscard.TRAIL0)  # 트레일 바이트 범위

    def test_조각은_24바이트이고_공백은_반각이다(self):
        specs, _ = syscard.glyph_set()
        self.assertTrue(all(len(sp) == 24 for sp in specs))
        a, wa = syscard.render("가나")
        b, wb = syscard.render("가 나")
        self.assertEqual(wb - wa, syscard.SPACE_ADV)  # 공백 = 8px(칸 16px 의 절반)
        self.assertEqual(wa, 2 * syscard.HANGUL_ADV)  # 한글은 붙여 쓴다


if __name__ == "__main__":
    unittest.main()
