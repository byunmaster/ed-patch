"""선택 커서 틀 오른쪽 끝 보정(`cursorfix`) — 가짜 본 프로그램에 심어 자리·값이 맞는지 본다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import cursorfix
import layout


def fake_prog(ctx: bytes = cursorfix.CONTEXT_ORIG) -> layout.Prog:
    orig = bytearray(b"\xff" * (layout.NBANKS * layout.BANK))
    s = (cursorfix.CONTEXT[0] - layout.BANK0) * layout.BANK + cursorfix.CONTEXT[1]
    orig[s : s + len(ctx)] = ctx
    for b, o, n in layout.ZERO_PADDING:
        t = (b - layout.BANK0) * layout.BANK + o
        orig[t : t + n] = bytes(n)
    return layout.Prog(orig=bytes(orig))


class CursorFix(unittest.TestCase):
    def test_오른쪽_끝만_4px_옮긴다(self):
        p = fake_prog()
        cursorfix.fix(p)
        w = {k: d for k, (d, _lab) in p.writes.items()}
        self.assertEqual(w[cursorfix.CAP], bytes([0x49]))
        self.assertEqual(len(w), 1)
        self.assertEqual(cursorfix.CAP_NEW - cursorfix.CAP_ORIG, 4)

    def test_원본이_다르면_멈춘다(self):
        bad = bytearray(cursorfix.CONTEXT_ORIG)
        bad[-5] ^= 0xFF
        with self.assertRaises(AssertionError):
            cursorfix.fix(fake_prog(bytes(bad)))


if __name__ == "__main__":
    unittest.main()
