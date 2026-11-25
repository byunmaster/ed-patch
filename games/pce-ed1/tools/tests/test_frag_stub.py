"""시스템 문구 조각 보관소 스텁(`hook._frag_asm`) 검산 — 스택 복귀 주소 바꿔 끼우기 · 마커 판정 · RAM 버퍼 복사.

실제 호출 사슬(`$6A41 JSR FRAGSH` → glue → entry(X=2) → `JSR FRAG`)이 쌓는 스택 모양을 손으로 만들어 두고 돌린다 —
복귀 주소 칸(S+8·S+9)이 어긋나면 이 시험이 먼저 운다(실제 에뮬 시험은 devlog 11-15).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import hook

SLOT = 3
STORE_AT = 0x6000 + hook.STORE_OFF


def machine(ptr: int, frag: bytes):
    mem = bytearray(0x10000)
    code = hook.frag_routine()
    mem[hook.FRAG_ADDR : hook.FRAG_ADDR + len(code)] = code
    mem[STORE_AT + 0x11 : STORE_AT + 0x11 + len(frag)] = frag
    mem[0x26] = SLOT
    mem[0x2F95 + SLOT] = ptr & 0xFF
    mem[0x2FE7 + SLOT] = ptr >> 8
    cpu = cpu65.CPU(mem)
    # 호출 사슬이 쌓은 것(깊은 쪽부터): `$6A41` 호출부 복귀($6A43) · P · MPR4 · glue 복귀 · MPR3
    for v in (0x6A >> 0, 0x43, 0xAA, 0xBB, 0x25, 0xFD, 0xCC):
        cpu.push(v)
    cpu.sp_before = cpu.sp
    return cpu, mem


class FragStub(unittest.TestCase):
    def test_marker_copies_and_repoints(self):
        frag = bytes(range(0x30, 0x30 + 20))
        cpu, mem = machine(0x4000 + hook.STORE_OFF + 0x11, frag)
        cpu.run(hook.FRAG_ADDR)
        buf = bytes(mem[hook.FRAG_BUF : hook.FRAG_BUF + len(frag)])
        self.assertEqual(buf, frag)
        self.assertEqual(mem[0x2F95 + SLOT] | mem[0x2FE7 + SLOT] << 8, hook.FRAG_BUF)
        self.assertEqual(cpu.sp, cpu.sp_before)  # 스택 균형(RTS 만 소비)

    def test_return_address_is_rewritten(self):
        cpu, mem = machine(0x4000 + hook.STORE_OFF, b"\x00")
        sp = cpu.sp
        cpu.run(hook.FRAG_ADDR)
        # 루틴 안의 S = 호출 전 sp − 2(복귀 주소 2B) — 호출부 복귀 칸은 S+8(하)·S+9(상) = sp+6·sp+7 (아래 machine() 이 쌓은 `$43`·`$6A` 자리)
        self.assertEqual(mem[0x2100 + sp + 6], hook.FRAG_RET & 0xFF)
        self.assertEqual(mem[0x2100 + sp + 7], hook.FRAG_RET >> 8)
        self.assertEqual(mem[0x2100 + sp + 5], 0xAA)  # P 는 안 건드린다
        self.assertEqual(mem[0x2100 + sp + 4], 0xBB)  # MPR4

    def test_ordinary_pointer_untouched(self):
        for ptr in (0x9D90, 0xA57C, 0xC400, 0x5BFF, 0x5D00):
            cpu, mem = machine(ptr, b"\x01")
            cpu.run(hook.FRAG_ADDR)
            self.assertEqual(mem[0x2F95 + SLOT] | mem[0x2FE7 + SLOT] << 8, ptr, hex(ptr))
            self.assertEqual(mem[hook.FRAG_BUF], 0, hex(ptr))

    def test_layout_fits(self):
        end = hook.FRAG_OFF + len(hook.frag_routine())
        # 복사 루틴은 보관소와 겹치지 않는다 — 앞(11-15)이거나 뒤(11-16 디버그 목록 코드가 길어져 보관소 뒤 `$7D00` 로 옮김)
        self.assertTrue(end <= hook.STORE_OFF or hook.FRAG_OFF >= hook.STORE_OFF + hook.STORE_SIZE)
        self.assertLess(end, 0x2000)
        self.assertEqual(hook.STORE_OFF + hook.STORE_SIZE, 0x1D00)
        self.assertLessEqual(hook.FRAG_BUF + hook.FRAG_LEN, 0x3E90)  # 11-01 후보 구간 `$3E46~$3E90` 안


if __name__ == "__main__":
    unittest.main()
