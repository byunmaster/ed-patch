"""자막 반각(합성 타일)·말줄임표 바닥 점 회귀 — **원본 없이 돈다**(글꼴은 레포 안 Neo둥근모·Galmuri)."""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "..", "..", "..", "shared"))

import font  # noqa: E402
import patch_title as P  # noqa: E402
import patch_ui as U  # noqa: E402


class TestCaptionHalf(unittest.TestCase):
    def test_sjis_index_는_sjis_of_index_의_역이다(self):
        for idx in (0, 35, 94, 1865, 3000, 7000, 7805):
            self.assertEqual(P.sjis_index(font.sjis_of_index(idx)), idx)
        # cp932 에만 있는 글자(전각 하이픈)도 얻는다 — EUC 경로(`jis_index`)는 못 얻는다
        self.assertEqual(font.sjis_of_index(P.sjis_index("－".encode("cp932"))), "－".encode("cp932"))

    def test_말줄임표_점은_글자_아랫줄에_있다(self):
        """마스터 2026-10-08 — 한국식 바닥. 점의 행이 온점(.)의 행과 같고 가운데 줄이 아니다."""
        from PIL import ImageFont

        ft = ImageFont.truetype(P.NEODGM, 16, layout_engine=ImageFont.Layout.BASIC)
        ell = P.ellipsis_bits(ft)
        rows = [r for r in range(16) if ell[r].any()]
        dot = P._neo_bits(".", ft, 8)
        dot_rows = [r for r in range(16) if dot[r].any()]
        self.assertEqual(rows, dot_rows)
        self.assertGreaterEqual(min(rows), 10)

    def test_본편_말줄임표_점은_반각_온점과_같은_모양_같은_행이다(self):
        """마스터 11-15(규칙 1-3) — 점 크기·모양이 마침표와 같다(세로 2px · 8·9행)."""
        g = U.ellipsis_glyph()
        rows = [g[r * 2 : r * 2 + 2] for r in range(11)]
        ink = [i for i, r in enumerate(rows) if any(r)]
        period = U.bake_ascii(".")["."]
        period_rows = [i for i, b in enumerate(period) if b]
        self.assertEqual(ink, period_rows)  # 온점과 같은 행(8·9)
        self.assertEqual(rows[8], rows[9])  # 점 하나가 세로 2px
        self.assertEqual(period[8], 0b01000000)  # 원판 ！ 점과 같은 1×2(열 1) — 마스터 11-16 「원판 ?! 에 맞춰」

    def test_반각_진행은_공백_부호_8px_나머지_16px(self):
        from PIL import ImageFont

        c = P.Composer.__new__(P.Composer)
        c.ft = ImageFont.truetype(P.NEODGM, 16, layout_engine=ImageFont.Layout.BASIC)
        c.ell = P.ellipsis_bits(c.ft)
        c.cache = {}
        c.orig = bytes(32 * 8000)  # 전각 로마자 글리프는 이 시험에 필요 없다
        self.assertEqual(c.unit(" ")[0], 8)
        self.assertEqual(c.unit(",")[0], 8)
        self.assertEqual(c.unit("가")[0], 16)
        self.assertEqual(c.unit("…")[0], 16)
        # 줄을 가운데에 놓고 16px 로 자른다 — 폭 8px 인 줄은 가운데 한 칸 안에 든다
        tiles = c.tiles("가 가", 4, None)
        self.assertEqual(len(tiles), 4)


if __name__ == "__main__":
    unittest.main()
