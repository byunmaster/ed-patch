"""확인용 롬 스텁 회귀 — **원본 없이 돈다**(가짜 0.BIN).

🔴 확인용 롬은 제품 롬과 **섹터 둘만** 달라야 한다(`/0.BIN` 풀 리터럴 4B · `KANJI12.FON` 코드 예약 칸) — 자막 시각·문안이 같다는 증명이 거기서 온다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import codearea as CA
import voicecheck as VC


class Voicecheck(unittest.TestCase):
    def test_fits_room(self):
        self.assertLessEqual(len(VC.build(CA.VCHK)), CA.VCHK_ROOM)

    def test_table_terminated_and_aligned(self):
        tb = VC.table_bytes()
        self.assertEqual(tb[-4:], b"\x00\x00\x00\x00")
        self.assertEqual((len(tb) - 4) % VC.ROW, 0)
        self.assertEqual(VC.build(CA.VCHK).count(tb), 1)  # 표가 코드 뒤에 그대로 든다

    def test_keys_unique(self):
        keys = [r[2] for r in VC.TABLE]
        self.assertEqual(len(keys), len(set(keys)))
        maps = [r[1] for r in VC.TABLE]
        self.assertEqual(len(maps), len(set(maps)))

    def test_patch_changes_only_literal(self):
        base = bytearray(0x7F000)
        off = VC.CALL_LIT - VC.BASE
        base[off : off + 4] = struct.pack(">I", VC.CALL_LIT_ORIG)
        CA.reset()
        out = VC.patch(bytes(base))
        diff = [i for i in range(len(base)) if base[i] != out[i]]
        self.assertEqual(diff, [off + k for k in range(4) if base[off + k] != out[off + k]])
        self.assertEqual(struct.unpack(">I", out[off : off + 4])[0], CA.VCHK)
        self.assertEqual(len(CA.SIDE), 1)  # 스텁은 폰트 쪽에만 쓴다
        CA.reset()


if __name__ == "__main__":
    unittest.main()
