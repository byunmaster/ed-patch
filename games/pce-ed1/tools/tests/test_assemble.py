"""컨테이너 재조립 — 원본 없이 돈다. 디렉터리 형식·블록 공유·되풀기를 못 박는다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import containers
import lz


class Assemble(unittest.TestCase):
    def test_왕복과_공유(self):
        a = (
            b"\x1f"
            + "侍女".encode("cp932")
            + b"\x04\x01"
            + "おはよう".encode("cp932") * 20
            + b"\x00"
        )
        b = b"\x4c\x10\xa0" + bytes(range(64)) + b"\x00" * 50
        out = build.assemble([(0, a), (7, b), (9, a)])  # 9 는 0 과 같은 블록
        ents, dend = containers.parse_dir(out[:2048])
        self.assertEqual([e[0] for e in ents], [0, 7, 9])
        self.assertEqual(ents[0][1], ents[2][1])  # 같은 src 를 나눠 갖는다
        self.assertEqual(dend, 3 * 5 + 1)
        for id_, src, ln in ents:
            got, _ = lz.decode(out[src:], ln)
            self.assertEqual(got, a if id_ in (0, 9) else b)

    def test_뱅크를_넘으면_죽는다(self):
        with self.assertRaises(build.BuildError):
            build.assemble([(0, b"x" * 0x2001)])

    def test_편집은_정확히_한_번_맞아야(self):
        with self.assertRaises(build.BuildError):
            build.apply_edits(b"abab", [(b"ab", b"cd")], "t")
        self.assertEqual(build.apply_edits(b"xab", [(b"ab", b"cde")], "t"), b"xcde")


if __name__ == "__main__":
    unittest.main()
