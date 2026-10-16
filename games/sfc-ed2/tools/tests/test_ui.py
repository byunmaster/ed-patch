"""ui.py — 창 블록 제자리 치환·이동 단위 시험(원본 롬 없이 합성 블록으로)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ui  # noqa: E402


def block(rows, stride, w=10, x=1, y=2):
    out = bytes([x, y, w, len(rows), stride])
    for r in rows:
        out += r + b"\x20" * (stride - 1 - len(r)) + b"\x00"
    return out


class PutRows(unittest.TestCase):
    def setUp(self):
        # 가짜 롬: $C0:0000 = 파일 0 에 블록을 둔다
        self.rom = bytearray(block([b"\x1fAB", b"\x1fCD"], 12) + b"\xff" * 64)

    def test_inplace_fits(self):
        w = []
        ui.put_rows(self.rom, 0xC00000, [b"\x1fXYZ", b"\x1fQ"], w)
        self.assertEqual(bytes(self.rom[5:17]), b"\x1fXYZ" + b"\x20" * 7 + b"\x00")
        self.assertEqual(w, [(5, 5 + 24)])

    def test_inplace_too_long_dies(self):
        with self.assertRaises(SystemExit):
            ui.put_rows(self.rom, 0xC00000, [b"\x1f" + b"A" * 11, b"\x1f"], [])

    def test_px_width(self):
        self.assertEqual(ui.px_width(b"\x1f\x20\x80\x00\x80\x01\x20\x00"), 8 + 24 + 8)


if __name__ == "__main__":
    unittest.main()
