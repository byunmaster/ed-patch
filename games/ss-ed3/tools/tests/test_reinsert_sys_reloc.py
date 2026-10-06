"""예산이 모자란 시스템 문자열을 죽은 구역 칸으로 옮기는 재배치 — 원본 없이 돈다(가짜 바이트)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reinsert_sys as RS
import subtitle_stub as SS


class Reloc(unittest.TestCase):
    def test_slot_constants_are_the_same_knowledge(self):
        self.assertEqual(RS.RELOC_AT, SS.RELOC)  # 두 곳이 갈리면 크레딧 코드가 문자열을 덮는다

    def test_slot_sits_before_gclk(self):
        self.assertLessEqual(RS.RELOC_AT + RS.RELOC_LEN, SS.GCLK)

    def test_relocates_and_repoints_a_single_reference(self):
        base = 0x06004000
        out = bytearray(0x20000)
        s = {"off": 0x100}
        ref = 0x8000
        out[ref : ref + 4] = (base + 0x100).to_bytes(4, "big")
        raw = "전투에서 승리했다!".encode("euc-kr")
        self.assertIsNone(RS._relocate(out, s, raw, base))
        at = RS.RELOC_AT - base
        self.assertEqual(bytes(out[at : at + len(raw) + 1]), raw + b"\x00")
        self.assertEqual(int.from_bytes(out[ref : ref + 4], "big"), RS.RELOC_AT)

    def test_refuses_when_pointer_count_is_not_one(self):
        base = 0x06004000
        out = bytearray(0x20000)
        self.assertIn("0개", RS._relocate(out, {"off": 0x100}, b"x", base))

    def test_refuses_too_long(self):
        out = bytearray(0x20000)
        self.assertIn("보다 길다", RS._relocate(out, {"off": 0x100}, b"x" * 40, 0x06004000))


if __name__ == "__main__":
    unittest.main()
