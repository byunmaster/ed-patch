"""글리프 읽기·쓰기 동치 — ps1-ed3 `font.py`(ED3·ED4 규약)와 **같은 바이트**를 내야 옮겨 탈 수 있다(원본 불필요, ED3 파일이 있을 때만)."""

import importlib.util
import os
import random
import sys
import unittest

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, ROOT)
from shared.ps1 import glyph as G


def ed3_font():
    d = os.path.join(ROOT, "games", "ps1-ed3", "tools")
    if not os.path.exists(os.path.join(d, "font.py")):
        return None
    sys.path.insert(0, d)
    try:
        spec = importlib.util.spec_from_file_location("ed3_font_ref", os.path.join(d, "font.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        sys.path.remove(d)
    return m


def blank(lay):
    return bytearray(lay.off() + lay.slots() * G.GLYPH_BYTES)


class TestLayout(unittest.TestCase):
    def test_칸_수는_코드에_적힌_값(self):
        self.assertEqual(G.ED4.slots(), 1936)
        self.assertEqual(G.ED3.slots(), 1829)  # 마지막 글리프 뒤 2바이트 여백 — 내림
        self.assertEqual(G.ED4.off(), 0x80070BD4 - 0x80010000 + 0x800)

    def test_왕복_두_규약(self):
        rng = np.random.default_rng(5)
        for lay in (G.ED3, G.ED4):
            bits = (rng.random((12, 12)) > 0.6).astype(np.uint8)
            buf = blank(lay)
            G.write_glyph(buf, 7, bits, lay)
            got = G.read_glyph(bytes(buf), 7, lay)
            keep = 12 - lay.top
            self.assertTrue((got[:keep] == bits[:keep]).all(), lay)

    def test_두_규약은_같은_그림을_다르게_저장한다(self):
        bits = np.zeros((12, 12), dtype=np.uint8)
        bits[2, 0] = 1
        a, b = blank(G.ED3), blank(G.ED4)
        G.write_glyph(a, 0, bits, G.ED3)
        G.write_glyph(b, 0, bits, G.ED4)
        self.assertNotEqual(
            bytes(a[G.ED3.off() : G.ED3.off() + 18]), bytes(b[G.ED4.off() : G.ED4.off() + 18])
        )

    def test_폰트_밖_코드는_실패(self):
        with self.assertRaises(ValueError):
            G.write_glyph(blank(G.ED4), G.ED4.slots(), np.zeros((12, 12)), G.ED4)


class TestEquivalenceWithEd3(unittest.TestCase):
    def test_ED3_font_py_와_같은_바이트(self):
        ref = ed3_font()
        if ref is None:
            self.skipTest("games/ps1-ed3 없음")
        rng = random.Random(11)
        for disc, lay in (("ed3", G.ED3), ("ed4", G.ED4)):
            self.assertEqual(ref.font_off(disc), lay.off())
            self.assertEqual(ref.font_slots(disc), lay.slots())
            buf_a, buf_b = blank(lay), blank(lay)
            for code in (0, 1, 63, 500, lay.slots() - 1):
                bits = np.array(
                    [[rng.random() > 0.55 for _ in range(12)] for _ in range(12)], dtype=np.uint8
                )
                ref.write_glyph(buf_a, code, bits, disc)
                G.write_glyph(buf_b, code, bits, lay)
                self.assertEqual(buf_a, buf_b, (disc, code))
                self.assertTrue(
                    (
                        ref.read_glyph(bytes(buf_a), code, disc)
                        == G.read_glyph(bytes(buf_b), code, lay)
                    ).all()
                )


if __name__ == "__main__":
    unittest.main()
