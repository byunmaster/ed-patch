"""이름 복사 루프(`patch_namecopy`)를 작은 SH-2 해석기로 돌려 본다 — 원본이 없어도 돈다.

확인: ① NUL 까지 옮긴다(원본 언롤은 N 바이트에서 끊겼다) ② 끝에 `r3 = r7`(변형 A 가 원 코드 대신 한다)
③ 상한(`LIMIT`)에서 멈춘다 ④ 변형 B 의 채움 명령(`mov #6,r7`)이 살아 있다.
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import patch_namecopy as P
import sh2
from test_msgwrap import Sh2

CODE, SRC, DST, STACK, RET = 0x060E1000, 0x060E2000, 0x0609F561, 0x060FFD00, 0x060E1F00


def _run(code, src, *, variant):
    mem = {CODE + i: v for i, v in enumerate(code)}
    mem.update({CODE + len(code) + i: v for i, v in enumerate(bytes.fromhex("000b0009"))})  # rts · nop
    mem.update({SRC + i: v for i, v in enumerate(src)})
    cpu = Sh2(mem)
    cpu.pc, cpu.pr = CODE, RET
    cpu.r[15], cpu.r[7] = STACK, DST
    if variant == "A":  # 앞에서 첫 글자를 r2 에, 둘째 글자 주소를 r1 에
        cpu.r[1], cpu.r[2] = SRC + 1, src[0]
    else:  # 변형 B — 목적지 r2, 소스 r1
        cpu.r[1], cpu.r[2] = SRC, DST
    for _ in range(20000):
        if cpu.pc == RET:
            break
        cpu.step()
    else:
        raise AssertionError("루프가 안 끝난다")
    out = bytearray()
    i = 0
    while cpu.b(DST + i) and i < 80:
        out.append(cpu.b(DST + i))
        i += 1
    return bytes(out), cpu


class NameCopy(unittest.TestCase):
    def test_copies_to_nul_variant_a(self):
        src = "나무인간A".encode("cp932", "replace") + b"\0junk"
        code, _ = P.routine(CODE)
        got, cpu = _run(code, src, variant="A")
        self.assertEqual(got, src.split(b"\0")[0])  # 6B 에서 안 끊긴다
        self.assertEqual(cpu.r[3], DST)  # 원 코드의 `mov r7,r3`

    def test_empty_string(self):
        code, _ = P.routine(CODE)
        got, _ = _run(code, b"\0", variant="A")
        self.assertEqual(got, b"")

    def test_limit_stops_a_runaway(self):
        code, _ = P.routine(CODE)
        got, _ = _run(code, b"A" * 200, variant="A")
        self.assertLessEqual(len(got), P.LIMIT + 2)

    def test_variant_b_keeps_the_filler_and_copies(self):
        code, _ = P.routine_b(CODE, "mov   #6,r7")
        src = b"ABCDEFGHIJKL\0zz"
        mem_dst = DST
        got, cpu = _run(code, src, variant="B")
        self.assertEqual(got, b"ABCDEFGHIJKL")
        self.assertEqual(cpu.r[7], 6)  # 첫 UNIT 에 끼어 있던 `mov #6,r7`
        self.assertEqual(mem_dst, DST)

    def test_variant_b_raw_filler_stays_at_its_address(self):
        """채움이 자리 의존(`mov.l @(d,pc)`)이면 원문 낱말 그대로 같은 주소에 둔다 — 여기선 `mov #6,r7`(0xE706)로 갈음."""
        code, _ = P.routine_b(CODE, 0xE706)
        self.assertEqual(code[:4].hex(), "6314e706")  # mov.b @r1+,r3 · 채움 — 원본 순서·주소
        got, cpu = _run(code, b"ABCDEFGHIJKL\0zz", variant="B")
        self.assertEqual(got, b"ABCDEFGHIJKL")
        self.assertEqual(cpu.r[7], 6)

    def test_assembles(self):
        self.assertGreater(len(sh2.verify(*P.routine(CODE)[0:1], CODE, P.routine(CODE)[1])), 5)


if __name__ == "__main__":
    unittest.main()
