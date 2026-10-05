"""낱말 표 칸 맞추기 — 원본 없이 도는 회귀(2026-09-27).

아이템 표 한 칸(열쇠 셋, 9코드)이 1코드 넘치자, 표 전체에서 「가장 많이 는 것」부터 되돌리던
옛 루프가 **다른 칸의 멀쩡한 이름 39개**를 일본어로 돌려놨다. 계약 둘을 박는다:
넘친 칸에서만 손댄다 · 되돌리기 전에 띄어쓰기부터 뺀다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build

TABLE = {"가": 0x100, "나": 0x101, "다": 0x102, "라": 0x103, " ": 0x104}


def mem_with_gap(chunks):
    """[[코드열…] 칸…] → 표 + 풀. 칸 사이엔 표가 안 가리키는 문자열(닻)을 끼운다."""
    strings = [s for ch in chunks for s in ch]
    n = len(strings)
    tbl, pool = [], bytearray()
    for ci, ch in enumerate(chunks):
        if ci:
            pool += struct.pack("<2H", 0x99, 0xFFFF)  # 닻
        for codes in ch:
            tbl.append(n * 2 + len(pool))
            pool += struct.pack(f"<{len(codes)}H", *codes) + struct.pack("<H", 0xFFFF)
    return struct.pack(f"<{n}H", *tbl) + bytes(pool), n


class TestFitChunks(unittest.TestCase):
    def setUp(self):
        self._enc = build.hangul_map.encode
        build.hangul_map.encode = lambda kr, disc, table: [TABLE[c] for c in kr]

    def tearDown(self):
        build.hangul_map.encode = self._enc

    def run_fit(self, chunks, krs):
        mem, n = mem_with_gap(chunks)
        t = {"table": 0, "base": 0, "n": n}
        ents = struct.unpack_from(f"<{n}H", mem, 0)
        orig = [s for ch in chunks for s in ch]
        cur = [[TABLE[c] for c in k] if k else o for k, o in zip(krs, orig, strict=True)]
        report = {}
        back = build.fit_chunks(mem, t, ents, cur, list(krs), orig, "ed3", None, report)
        return cur, back, report

    def test_spaces_go_before_names(self):
        # 칸 하나: 원문 2+2코드 → 우리말 「가 나」(3)+「다라」(2) = 1코드 초과 → 공백 하나만 뺀다
        cur, back, rep = self.run_fit([[[0x40, 0x41], [0x42, 0x43]]], ["가 나", "다라"])
        self.assertEqual(back, 0)
        self.assertEqual(rep.get("squeezed"), 1)
        self.assertEqual(cur[0], [0x100, 0x101])

    def test_revert_stays_in_the_overflowing_chunk(self):
        # 칸 A 는 들어가고(늘었지만 여유), 칸 B 는 공백 없이 넘친다 → B 에서만 되돌린다
        chunks = [[[0x40, 0x41, 0x42], [0x43]], [[0x44], [0x45]]]
        krs = ["가나", "다", "가나", "라"]
        cur, back, _ = self.run_fit(chunks, krs)
        self.assertEqual(back, 1)
        self.assertEqual(cur[0], [0x100, 0x101], "넘치지 않은 칸의 이름이 되돌려졌다")
        self.assertEqual(cur[2], [0x44], "넘친 칸에서 가장 많이 는 것을 되돌린다")


if __name__ == "__main__":
    unittest.main()
