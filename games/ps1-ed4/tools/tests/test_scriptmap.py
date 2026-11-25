"""대본 멤버 재구축 회귀 — **원본 없이 돈다**(합성 멤버). 표 규격(ED4 356)과 풀 규격(125) 둘 다.

🔴 지키는 것: 항등 재구축이 바이트 같음 · 길이가 바뀌어도 색인/포인터가 「몇 번째 조각」으로 다시 매핑됨 · 조각 수가 다르면 멈춤.
"""

import struct
import unittest

import _path  # noqa: F401

from shared.ps1 import gmf_script as scriptmap

TERM = 0xFFFF


def table_member(strings):
    """표 규격: [u16 base][0F 00 + u16 색인 0][표 N][풀]."""
    n = len(strings)
    base = 6
    pool, tbl = bytearray(), []
    for s in strings:
        tbl.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", TERM)
    return struct.pack("<H", base) + b"\x0f\x00\x00\x00" + struct.pack(f"<{n}H", *tbl) + bytes(pool)


def pool_member(strings):
    """풀 규격: [u16 base][0F 90 + u16 V(조각 0)][풀] — ED3 꼴 `0F 90 V`."""
    base = 8
    pool = b"".join(struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", TERM) for s in strings)
    return struct.pack("<H", base) + b"\x0f\x90" + struct.pack("<H", 0) + b"\x00\x00" + pool


class TestTable(unittest.TestCase):
    def setUp(self):
        self.mem = table_member([[0x40, 0x41], [0x42], [0x43, 0x44, 0x45]])

    def test_규격을_구조로_판정한다(self):
        self.assertEqual(scriptmap.layout(self.mem), scriptmap.LAYOUT_TABLE)
        self.assertEqual(scriptmap.table_len(self.mem), 3)

    def test_항등_재구축은_바이트_같다(self):
        segs = [list(c) for _, c in scriptmap.parse(self.mem)["segments"]]
        out, _ = scriptmap.rebuild(self.mem, segs, event_data=True)
        self.assertEqual(out, self.mem)

    def test_길이를_바꿔도_표만_다시_계산된다(self):
        segs = [list(c) for _, c in scriptmap.parse(self.mem)["segments"]]
        segs[1] = [0x50] * 9
        out, _ = scriptmap.rebuild(self.mem, segs, event_data=True)
        back = [list(c) for _, c in scriptmap.parse(out)["segments"]]
        self.assertEqual(back, segs)
        self.assertEqual(out[:6], self.mem[:6])  # 스크립트(색인)는 안 건드린다
        self.assertGreater(len(out), len(self.mem))

    def test_조각_수가_다르면_멈춘다(self):
        with self.assertRaises(scriptmap.ScriptError):
            scriptmap.rebuild(self.mem, [[1]], event_data=True)


class TestPool(unittest.TestCase):
    def setUp(self):
        self.mem = pool_member([[0x40, 0x41], [0x42]])

    def test_규격을_구조로_판정한다(self):
        self.assertEqual(scriptmap.layout(self.mem), scriptmap.LAYOUT_POOL)

    def test_항등_재구축은_바이트_같다(self):
        segs = [list(c) for _, c in scriptmap.parse(self.mem)["segments"]]
        out, _ = scriptmap.rebuild(self.mem, segs, event_data=True)
        self.assertEqual(out, self.mem)

    def test_앞_조각이_길어져도_포인터가_따라간다(self):
        segs = [list(c) for _, c in scriptmap.parse(self.mem)["segments"]]
        segs[0] = [0x40, 0x41, 0x42, 0x43]
        out, _ = scriptmap.rebuild(self.mem, segs, event_data=True)
        self.assertEqual([list(c) for _, c in scriptmap.parse(out)["segments"]], segs)


if __name__ == "__main__":
    unittest.main()
