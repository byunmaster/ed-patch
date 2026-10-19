"""구운 글리프 비트맵 중복 게이트 — 합성 롬으로 「같은 그림이면 잡는다」를 고정한다(원문 인용 없음)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: E402,F401,I001
import check_glyph_dups as G  # noqa: E402
import common  # noqa: E402


def make_slot(tmp: Path, rawtab: dict[int, bytes], glyphs: dict[int, bytes], n: int = 6) -> Path:
    rom = bytearray(0x200000)
    off = G._off("$3F:A188")
    base = {}  # 지정 쌍의 부호는 서로 다른 그림으로 미리 채운다 — 시험이 고른 것만 덮어쓴다
    for a, b in G.PAIRS:
        for ch in (a, b):
            code = G.encode.KR_TABLE.get(ch)
            if code is not None and code < 0xCF:
                base[code] = bytes([code] * 16)
    for code, pic in {**base, **rawtab}.items():
        rom[off + code * 16 : off + code * 16 + 16] = pic
    b1 = common.snes2off(0x3D8000)
    for i, pic in glyphs.items():
        rom[b1 + i * 32 : b1 + i * 32 + 32] = pic
    (tmp / "x.sfc").write_bytes(bytes(rom))
    (tmp / "manifest.json").write_text(json.dumps({"hook": {"labels": {"rawtab": "$3F:A188"}, "glyphs": n}}))
    return tmp


class GlyphDups(unittest.TestCase):
    def test_distinct_ok(self):
        with tempfile.TemporaryDirectory() as t:
            s = make_slot(Path(t), {0x83: bytes([1] * 16), 0x84: bytes([2] * 16)}, {0: bytes([3] * 32), 1: bytes([4] * 32)})
            self.assertEqual(G.scan(s), [])

    def test_comma_equals_period_caught(self):
        with tempfile.TemporaryDirectory() as t:
            pic = bytes([0] * 12 + [0x18, 0x18, 0, 0])
            s = make_slot(Path(t), {0x83: pic, 0x84: pic}, {})
            self.assertTrue(any("rawtab 같은 그림" in b for b in G.scan(s)))

    def test_glyph_bank_dup_caught_filler_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            same = bytes(range(32))
            s = make_slot(Path(t), {}, {0: same, 1: same, 2: G.FILLER, 3: G.FILLER})
            bad = G.scan(s)
            self.assertEqual(len(bad), 1)
            self.assertIn("[0, 1]", bad[0])


if __name__ == "__main__":
    unittest.main()
