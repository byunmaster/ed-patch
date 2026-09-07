"""정본 문안의 제어 태그 → 토큰. `<fc32>` 처럼 인자 딸린 제어가 글자로 새던 회귀(2026-09-05)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene
import sysmsg


def enc(s):
    return s.encode("ascii")


class Tags(unittest.TestCase):
    def test_multibyte_ctl_tag_is_control_not_text(self):
        st = scene.Stream(
            0, [scene.Token(0, b"\xfc\x32", "ctl", 0xFC), scene.Token(2, b"\x07", "end", 0x07)], 3
        )
        toks = sysmsg._tokens_from_ours(st, "<fc32>ab<07>", enc)
        self.assertEqual(
            [(t.kind, t.raw) for t in toks],
            [("ctl", b"\xfc\x32"), ("text", b"ab"), ("end", b"\x07")],
        )

    def test_single_byte_ctl_and_newline(self):
        st = scene.Stream(0, [scene.Token(0, b"\x06", "end", 0x06)], 1)
        toks = sysmsg._tokens_from_ours(st, "<fe0e>a\nb", enc)
        self.assertEqual([t.raw for t in toks], [b"\xfe\x0e", b"a", b"\x01", b"b", b"\x06"])


if __name__ == "__main__":
    unittest.main()
