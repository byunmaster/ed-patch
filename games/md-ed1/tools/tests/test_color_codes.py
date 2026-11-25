"""check_color_codes — 색 코드가 빠지거나 안 닫히면 잡는다(양성 대조)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_color_codes as C
import scene


def toks(*items):
    out = []
    for kind, code in items:
        out.append(
            scene.Token(
                0,
                bytes([code]) if kind == "ctl" else b"\x20",
                kind,
                code if kind == "ctl" else None,
            )
        )
    return out


GREEN, REST, NAME = 0x1C, 0x04, 0x1E


class Color(unittest.TestCase):
    def test_same(self):
        a = toks(("ctl", GREEN), ("text", 0), ("ctl", REST))
        self.assertEqual(C.compare(a, list(a)), [])

    def test_missing_restore_is_caught(self):
        a = toks(("ctl", GREEN), ("text", 0), ("ctl", REST))
        b = toks(("ctl", GREEN), ("text", 0))
        self.assertTrue(C.compare(a, b))

    def test_missing_set_is_caught(self):
        a = toks(("ctl", GREEN), ("text", 0), ("ctl", REST))
        self.assertTrue(C.compare(a, toks(("text", 0), ("ctl", REST))))

    def test_name_tag_pair_ignored(self):
        a = toks(("text", 0))
        b = toks(("ctl", NAME), ("text", 0), ("ctl", REST), ("text", 0))
        self.assertEqual(C.compare(a, b), [])


if __name__ == "__main__":
    unittest.main()
