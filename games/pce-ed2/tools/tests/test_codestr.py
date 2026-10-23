"""장면 코드 영역 문자열 옮기기 — 합성 패키지로 포인터·0xFF 패딩·원문 대조를 못 박는다(원본 없이 돈다)."""

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import codestr as c
import font


class Apply(unittest.TestCase):
    def _fake(self, sp: c.Spec, old: bytes):
        pkg = bytearray(b"\xff" * 0x400)
        pkg[sp.ptr - 4 : sp.ptr + 2] = b"\x20\x3c\x40\x2c" + (c.BASE + sp.old).to_bytes(2, "little")
        pkg[sp.old : sp.old + len(old)] = old
        return bytes(pkg)

    def test_원문이_다르면_거부(self):
        sp = c.SPECS[0]
        pkg = self._fake(sp, b"\x01" * sp.n)
        with self.assertRaises(ValueError):
            c.apply(sp.rel, pkg, bytearray(pkg), font.GlyphTable())

    def test_포인터가_패딩으로_돌아간다(self):
        sp = c.SPECS[0]
        old = bytes(range(1, sp.n)) + b"\x00"
        spx = c.Spec(sp.rel, sp.ptr, sp.old, sp.n, hashlib.sha1(old).hexdigest()[:12], sp.free, sp.parts)
        orig = c.SPECS
        c.SPECS = (spx,)
        try:
            pkg = self._fake(spx, old)
            tab = font.GlyphTable()
            tab.map = {ch: i for i, ch in enumerate(sorted(set("방어력이내려갔다")))}
            new = bytearray(pkg)
            c.apply(spx.rel, pkg, new, tab)
        finally:
            c.SPECS = orig
        ptr = new[spx.ptr] | new[spx.ptr + 1] << 8
        self.assertEqual(ptr, c.BASE + spx.free)
        self.assertEqual(new[spx.free : spx.free + 2], font.code(tab.map["방"]))
        self.assertEqual(new[spx.old : spx.old + spx.n], b"\xff" * spx.n)  # 옛 문자열은 지워진다

    def test_정본_조각_조합이_기대_문안과_같다(self):
        flat = lambda i: "".join(p if isinstance(p, str) else "|" for p in c._flat(c.SPECS[i]))  # noqa: E731
        self.assertEqual(flat(4), "|에게 합계 |의 피해|")  # 정본 「{name}에게 합계」 + 「{n}의 피해」(끝 부호 없음 — 원문대로)
        self.assertEqual(flat(5), "|에게 |의 피해!!|")

    def test_글자와_자리(self):
        for sp in c.SPECS:
            n = sum(len(p) if isinstance(p, bytes) else 0 for p in c._flat(sp))
            self.assertGreater(n, 0)
        ch = c.chars_by_pkg()
        self.assertIn("합", ch[2690])
        self.assertIn("력", ch[1026])


if __name__ == "__main__":
    unittest.main()
