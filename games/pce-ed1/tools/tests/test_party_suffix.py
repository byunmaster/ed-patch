"""파티 호칭 접미 루틴(`hook.party_suffix`) 검산 — 쓰이는 옵코드 아홉만 도는 최소 인터프리터.

혼자(동료 레코드 셋의 비트 7 이 다 섬)면 복사 시작 X=2 · 길이 1(종결 `06` 뿐), 한 명이라도 파티에 있으면 X=0 · 길이 3(「들」+종결).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hook


def run(code: bytes, mem: dict[int, int]) -> tuple[int, int]:
    a = x = c = 0
    z21 = 0
    i = 0
    while True:
        op = code[i]
        if op == 0xAD:  # LDA abs
            a = mem[code[i + 1] | code[i + 2] << 8]
            i += 3
        elif op == 0x2D:  # AND abs
            a &= mem[code[i + 1] | code[i + 2] << 8]
            i += 3
        elif op == 0x0A:  # ASL A
            c = a >> 7
            a = (a << 1) & 0xFF
            i += 1
        elif op == 0x62:  # CLA
            a = 0
            i += 1
        elif op == 0x2A:  # ROL A
            a, c = ((a << 1) | c) & 0xFF, a >> 7
            i += 1
        elif op == 0xAA:  # TAX
            x = a
            i += 1
        elif op == 0x49:  # EOR #imm
            a ^= code[i + 1]
            i += 2
        elif op == 0x85:  # STA zp ($21 만)
            assert code[i + 1] == 0x21
            z21 = a
            i += 2
        elif op == 0x60:  # RTS
            return x, z21
        else:
            raise AssertionError(f"모르는 옵코드 {op:02X}")


class PartySuffix(unittest.TestCase):
    def test_바이트(self):
        self.assertEqual(hook.party_suffix().hex(), "ad40c32d80c32dc0c30a622a0aaa4903852160")

    def test_혼자와_파티(self):
        code = hook.party_suffix()
        out = {0xC340: 0x81, 0xC380: 0x82, 0xC3C0: 0x82}
        self.assertEqual(run(code, out), (2, 1))  # 혼자 — 종결만
        for who in (0xC340, 0xC380, 0xC3C0):
            out = {0xC340: 0x81, 0xC380: 0x82, 0xC3C0: 0x82}
            out[who] = 0x01  # 비트 7 이 내려가면 파티원이다
            self.assertEqual(run(code, out), (0, 3), hex(who))  # 「들」+종결

    def test_들어갈_자리(self):
        self.assertLessEqual(hook.PARTY_ADDR + len(hook.party_suffix()), hook.HOOK_ADDR + hook.PAYLOAD_LEN)


if __name__ == "__main__":
    unittest.main()
