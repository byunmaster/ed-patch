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

    def test_줄은_화면_가운데에서_4px_안이고_끝_말줄임은_계산에서_뺀다(self):
        # 줄 가운데 맞춤(마스터 10-22) — 이상값(`x0_for`)과 실제 시작 x 의 차가 4px 이내
        for mi, msg in enumerate(syscard.MESSAGES):
            for r, line in enumerate(msg):
                self.assertLessEqual(abs(syscard.X0[mi][r] - syscard.x0_for(mi, r, line)), 4, (mi, r, line))
        # 끝 「…」「.」「,」 는 가운데 계산에서 빠진다: 같은 앞부분이면 이상 시작 x 가 같다
        self.assertEqual(syscard.x0_for(0, 0, "가나다……"), syscard.x0_for(0, 0, "가나다"))

    def test_반각_영문_뒤_한글은_2px_벌어진다(self):
        a, wa = syscard.render("RAM에")
        b, wb = syscard.render("RAM 에")
        self.assertEqual(wa - (syscard.NARROW_ADV * 3 + syscard.HANGUL_ADV), syscard.GAP_LATIN_HANGUL)
        self.assertEqual(wb - (syscard.NARROW_ADV * 3 + syscard.SPACE_ADV + syscard.HANGUL_ADV), 0)  # 공백 뒤엔 벌리지 않는다

    def test_말줄임은_한국식_바닥이다(self):
        import font

        g = font.glyph("…")
        rows = [int.from_bytes(g[2 * y : 2 * y + 2], "big") for y in range(12)]
        self.assertEqual([y for y, v in enumerate(rows) if v], [font.ELLIPSIS_FLOOR_ROW])  # 점 셋이 마침표 행 하나에만
        self.assertEqual(rows[font.ELLIPSIS_FLOOR_ROW], sum(0x8000 >> c for c in font.ELLIPSIS_FLOOR_COLS))

    def test_조각은_24바이트이고_공백은_반각이다(self):
        specs, _ = syscard.glyph_set()
        self.assertTrue(all(len(sp) == 24 for sp in specs))
        a, wa = syscard.render("가나")
        b, wb = syscard.render("가 나")
        self.assertEqual(wb - wa, syscard.SPACE_ADV)  # 공백 = 8px(칸 16px 의 절반)
        self.assertEqual(wa, 2 * syscard.HANGUL_ADV)  # 한글은 붙여 쓴다


if __name__ == "__main__":
    unittest.main()
