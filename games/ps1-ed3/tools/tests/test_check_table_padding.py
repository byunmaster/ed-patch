"""낱말 표 재삽입 대조의 회귀 — 빈 항목이 내용을 얻거나 종결이 바뀌거나 별칭이 갈라지면 잡는다(가짜 바이트, 원본 없이 돈다)."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_table_padding as T


def make(strings, terms=None):
    """표(u16 오프셋 N개) + 풀. 종결 기본 0x8000."""
    n = len(strings)
    pool = bytearray()
    offs = []
    for i, s in enumerate(strings):
        offs.append(n * 2 + len(pool))
        pool += struct.pack(f"<{len(s)}H", *s) + struct.pack("<H", (terms or {}).get(i, 0x8000))
    return struct.pack(f"<{n}H", *offs) + bytes(pool)


class TestTablePadding(unittest.TestCase):
    def test_identical_is_clean(self):
        a = make([[1, 2], [], [3], [4, 5]])
        self.assertEqual(T.compare(a, a, [(0, 0, 4)]), [])

    def test_empty_slot_gaining_text_is_flagged(self):
        a = make([[1, 2], [], [3], [4, 5]])
        b = make([[1, 2], [9], [3], [4, 5]])
        self.assertTrue(any("빈 항목" in p for p in T.compare(a, b, [(0, 0, 4)])))

    def test_terminator_change_is_flagged(self):
        a = make([[1, 2], [7], [3], [4, 5]])
        b = make([[1, 2], [7], [3], [4, 5]], {2: 0xFFFF})
        self.assertTrue(any("종결" in p for p in T.compare(a, b, [(0, 0, 4)])))

    def test_alias_split_is_flagged(self):
        a = bytearray(make([[1], [2], [3], [4]]))
        struct.pack_into("<H", a, 2, struct.unpack_from("<H", a, 0)[0])  # 항목 1 이 0 과 같은 자리
        b = bytearray(a)
        struct.pack_into("<H", b, 2, struct.unpack_from("<H", b, 4)[0])  # 갈라짐
        self.assertTrue(any("갈라졌다" in p for p in T.compare(bytes(a), bytes(b), [(0, 0, 4)])))


if __name__ == "__main__":
    unittest.main()
