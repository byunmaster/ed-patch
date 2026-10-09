"""폰트 기하 계약 — 원본 없이 도는 회귀.

밟은 함정: **자리를 「폰트다워 보이는 밀도」로 찾으려다 한 밤을 태웠다**(후보 2,611건이
전부 그림이었다). 답은 코드에 있었다 — `ED3.EXE` 0x80018AB4 의 `코드×18 + 0x8009E170`.
그래서 여기서는 **그 상수들과 패킹**을 박는다. 하나라도 흔들리면 글자가 통째로 밀린다.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import font


class TestFontGeometry(unittest.TestCase):
    def test_constants(self):
        """디스어셈블로 읽은 값 — 바꾸려면 그 코드를 다시 읽어야 한다."""
        self.assertEqual(font.FONT_RAM, 0x8009E170)
        self.assertEqual(font.GLYPH_BYTES, 18)
        self.assertEqual(font.FONT_OFF, 0x08E970)
        self.assertEqual((font.ROWS, font.CELL), (12, 12))
        # 18바이트 = 12행 × 12비트 밀착 패킹
        self.assertEqual(font.ROWS * font.CELL, font.GLYPH_BYTES * 8)

    def test_font_end_is_the_expansion_table(self):
        """🔴 폰트 끝 = 렌더러 전개표 자리. 추정(1900·1990)으로 71·51자를 표 위에 구웠었다."""
        self.assertEqual(font.font_slots("ed3"), 1829)
        self.assertEqual(font.font_slots("ed4"), 1936)
        for disc, f in font.FONTS.items():
            # 표는 마지막 글리프 뒤에 온다 — 여백은 한 칸(18B) 미만 (ED3 2B · ED4 0B)
            self.assertLess((f["table"] - f["ram"]) % font.GLYPH_BYTES, font.GLYPH_BYTES, disc)
            self.assertEqual(font.font_end(b"", disc), font.font_slots(disc))

    def test_pack_roundtrip(self):
        rnd = np.random.default_rng(7)
        for _ in range(50):
            bits = rnd.integers(0, 2, size=(12, 12), dtype=np.uint8)
            buf = bytearray(font.FONT_OFF + 18 * 4)
            font.write_glyph(buf, 0, bits)
            back = font.read_glyph(bytes(buf), 0)
            self.assertTrue((back == bits).all())

    def test_write_touches_only_its_slot(self):
        """🔴 글리프 하나를 쓰면 **그 18바이트만** 바뀐다 (이웃이 밀리면 전부 틀린다)."""
        buf = bytearray(b"\xaa" * (font.FONT_OFF + 18 * 5))
        before = bytes(buf)
        font.write_glyph(buf, 3, np.ones((12, 12), dtype=np.uint8))
        o = font.FONT_OFF + 3 * 18
        self.assertEqual(bytes(buf[:o]), before[:o])
        self.assertEqual(bytes(buf[o + 18 :]), before[o + 18 :])
        self.assertEqual(bytes(buf[o : o + 18]), b"\xff" * 18)

    def test_pair_swap_is_self_inverse(self):
        """열 쌍 교환은 자기 역함수 — 읽기·쓰기가 같은 함수를 쓴다."""
        rnd = np.random.default_rng(3)
        g = rnd.integers(0, 2, size=(12, 12), dtype=np.uint8)
        self.assertTrue((font._swap_pairs(font._swap_pairs(g)) == g).all())

    def test_pair_swap_moves_the_right_columns(self):
        """🔴 실측 계약 — 비트 0 은 **1열**로, 비트 11 은 **10열**로 간다(탐침 글리프)."""
        g = np.zeros((12, 12), dtype=np.uint8)
        g[0, 0] = 1
        self.assertEqual(font._swap_pairs(g)[0].tolist(), [0, 1] + [0] * 10)
        g = np.zeros((12, 12), dtype=np.uint8)
        g[0, 11] = 1
        self.assertEqual(font._swap_pairs(g)[0].tolist(), [0] * 10 + [1, 0])

    def test_hangul_glyph_fits_cell(self):
        g = font.hangul_glyph("한")
        self.assertEqual(g.shape, (12, font.HANGUL_W))
        self.assertGreater(int(g.sum()), 10)  # 빈 글리프가 아니다
        self.assertLess(int(g.sum()), 120)


if __name__ == "__main__":
    unittest.main()


class TestDiscLayout(unittest.TestCase):
    """🔴 **저장 규약이 디스크마다 다르다** — ED3 은 열 짝 교환, ED4 는 몸통이 한 행 아래.

    ED3 규약으로 ED4 를 읽으면 글자가 **그럭저럭 보이는 채로** 틀린다(획이 한 칸 튄다).
    실제로 그 상태에서 「ED4 카나를 폰트 렌더로 확인했다」고 적어 두고 있었다.
    그걸 바로잡자 두 활자가 **1,595자 비트 완전일치**로 붙었다(2026-09-03).
    """

    def test_layout_table(self):
        self.assertEqual(font.LAYOUT["ed3"], {"swap": True, "top": 0})
        self.assertEqual(font.LAYOUT["ed4"], {"swap": False, "top": 1})

    def test_roundtrip_each_disc(self):
        """디스크마다 쓰고 되읽으면 그대로 나온다 (ED4 는 몸통이 11행)."""
        rnd = np.random.default_rng(11)
        for disc in font.LAYOUT:
            rows = 12 - font.LAYOUT[disc]["top"]
            for _ in range(20):
                bits = rnd.integers(0, 2, size=(rows, 12), dtype=np.uint8)
                buf = bytearray(font.font_off(disc) + 18 * 4)
                font.write_glyph(buf, 1, bits, disc)
                back = font.read_glyph(bytes(buf), 1, disc)
                self.assertTrue((back[:rows] == bits).all(), disc)
                self.assertFalse(back[rows:].any(), disc)

    def test_ed4_is_not_read_with_ed3_rules(self):
        """규약이 갈렸다는 것 자체를 박는다 — 같아지면 위 실측이 무너진 것이다."""
        self.assertNotEqual(font.LAYOUT["ed3"], font.LAYOUT["ed4"])


class TestEllipsis(unittest.TestCase):
    def test_ellipsis_is_three_bottom_dots_in_one_cell(self):
        """🔴 말줄임은 「…」 전각 한 글자, 점 셋은 마침표와 같은 바닥 행(마스터 10-08)."""
        g = np.asarray(font.hangul_glyph("…"))
        rows = [r for r in range(g.shape[0]) if g[r].any()]
        dot = np.asarray(font.hangul_glyph("."))
        period_rows = [r for r in range(dot.shape[0]) if dot[r].any()]
        self.assertEqual(rows, period_rows)  # 마침표와 같은 높이(바닥) — Galmuri 의 가운데 행(5)이 아니다
        self.assertGreaterEqual(min(rows), 9)
        self.assertEqual(int(g.sum()), 3 * int(dot.sum()))  # 점 셋
        self.assertEqual(font.ELLIPSIS_CODE["ed3"], 3)

    def test_ellipsis_encodes_to_the_reshaped_code_and_is_full_width(self):
        import hangul_map
        import typeset

        self.assertEqual(hangul_map.encode("…", "ed3", {}), [3])
        self.assertEqual(typeset.width_cells("…", "ed3"), 1.0)  # 반각(0.5)이 아니다
