"""디버그 진입키 후크(debug_key) — 기계어를 디스어셈블로 검산하고, 기대 입구·칸 크기를 지킨다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import debug_key as D

try:
    from capstone import CS_ARCH_M68K, CS_MODE_M68K_000, Cs
except ImportError:  # pragma: no cover
    Cs = None


@unittest.skipIf(Cs is None, "capstone 없음")
class DebugKey(unittest.TestCase):
    def dis(self):
        md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
        return [(i.address, i.mnemonic, i.op_str) for i in md.disasm(D.code(), D.HOOK_AT)]

    def test_decodes_to_the_whole_hook(self):
        ins = self.dis()
        self.assertEqual(ins[-1][1], "rts")
        self.assertEqual(ins[-1][0] + 2, D.HOOK_AT + len(D.code()))  # 연속 디코드가 끝까지 맞는다

    def test_reads_exact_combo_byte_and_hold(self):
        txt = " ".join(f"{m} {o}" for _a, m, o in self.dis())
        self.assertIn(f"move.b ${D.PAD:x}.l, d0", txt)
        self.assertIn("cmpi.b #$d0, d0", txt)  # Start+A+B 만 — 방향·C 가 섞이면 같지 않다
        self.assertIn(f"cmpi.w #${D.HOLD:x}, d1", txt)

    def test_title_combo_is_always_open_and_level_only_toggles_62(self):
        md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
        ins = [(i.mnemonic, i.op_str) for i in md.disasm(D.CMP_NEW, D.CMP_AT)]
        self.assertEqual(ins[0], ("cmp.b", "d0, d0"))  # 항상 같다 → 뒤의 bne 를 안 탄다
        self.assertEqual(len(D.CMP_NEW), len(D.CMP_OLD))
        txt = " ".join(f"{m} {o}" for _a, m, o in self.dis())
        self.assertNotIn("#$63", txt)  # 0x63 단계는 없다(리셋에 지워져 못 쓴다)

    def test_room_and_entry(self):
        self.assertLessEqual(len(D.code()), D.HOOK_ROOM)
        e = D.patch_entry()
        self.assertEqual(len(e), len(D.ENTRY_OLD))
        self.assertEqual(e[:2].hex(), "4eb9")
        self.assertEqual(int.from_bytes(e[2:6], "big"), D.HOOK_AT)

    def test_replaced_call_is_done_first(self):
        self.assertEqual(D.code()[: len(D.ENTRY_OLD)], D.ENTRY_OLD)  # 패드 갱신을 먼저 부른 뒤 읽는다


if __name__ == "__main__":
    unittest.main()
