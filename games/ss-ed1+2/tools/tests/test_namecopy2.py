"""이름 복사 둘째 패스 회귀 — **원본 없이 돈다**(합성 코드).

🔴 2026-10-19: 몬스터 슬롯 B·C 이름이 「나무인愛」·「지팡이품」으로 깨졌다. 원인은 고정 오프셋 한 바이트 복사
(`add #104,r3 · …`)와 `bra` 로 공유 런 중간에 뛰어드는 복사였고, 옛 검산(`UNIT` 꼴)엔 둘 다 안 걸렸다.
여기선 ① 의미 검사(`semantic_check`)가 그 꼴을 잡고 ② 고친 코드가 같은 검사를 통과하며 ③ 실제로 돌려 긴 이름이 NUL 까지
들어가는지 본다.
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_fixed_copy as C
import patch_namecopy as P
from test_msgwrap import Sh2

BASE = 0x060E0000
DST = 0x0609F561
LONG = b"ABCDEFGHIJ"  # 우리 문안(10B)
SHORT = b"ABCDEF"  # 원본(6B + NUL = 7B 복사)


def w(*ws):
    return b"".join(x.to_bytes(2, "big") for x in ws)


def f1_image(src_text, n=6):
    """고정 오프셋 복사(슬롯 B 꼴) — `n` 유닛 + 꼬리. 리터럴 풀: [0]=소스 포인터, [1]=남의 리터럴(`mov.l ..,r2`)."""
    code = bytearray()
    code += b"\xd1\x00"  # mov.l @(d,pc),r1 — 디스플레이스먼트는 아래서 채운다
    for k in range(n):
        code += w(0x6214, 0x7300 | (104 + k), 0x2320, 0x6373)
    code += w(0x7300 | (104 + n), 0x6110, 0xD200, 0x2310)  # add · load · (남의) mov.l ..,r2 · store
    code += w(0x000B, 0x0009)
    while len(code) % 4:
        code += b"\x00\x09"
    pool = len(code)
    src_at = BASE + pool + 8
    code += src_at.to_bytes(4, "big") + (0xCAFE0000).to_bytes(4, "big")
    code += src_text + b"\0"
    code[1] = (pool - ((2 + 4) & ~3)) // 4
    other = 2 + 8 * n + 4  # 남의 `mov.l` 의 위치
    code[other + 1] = (pool + 4 - ((other + 4) & ~3)) // 4
    return bytes(code), src_at


def run_cpu(code, src_text, max_steps=5000):
    mem = {BASE + i: v for i, v in enumerate(code)}
    cpu = Sh2(mem)
    cpu.pc, cpu.pr = BASE, 0x06000000
    cpu.r[7] = DST
    for _ in range(max_steps):
        if cpu.pc == 0x06000000:
            break
        cpu.step()
    else:
        raise AssertionError("안 끝난다")
    return cpu


def dest(cpu, off, n=40):
    out = bytearray()
    for i in range(n):
        v = cpu.b(DST + off + i)
        if v == 0:
            break
        out.append(v)
    return bytes(out)


class SecondPass(unittest.TestCase):
    def setUp(self):
        self.orig, self.src = f1_image(SHORT)
        # 우리 빌드: 같은 코드 + 같은 주소에 더 긴 문안(풀 뒤에 붙으니 길이만 다르다)
        self.built = bytearray(self.orig[: self.src - BASE]) + LONG + b"\0"
        self.built = bytes(self.built)

    def test_semantic_check_catches_fixed_offset_copy(self):
        """🔴 옛 검산(`UNIT` 꼴)은 이 꼴을 못 봤다. 의미 검사는 효과로 잰다."""
        self.assertEqual(C.sites(self.orig), [], "옛 꼴 검산에 걸리면 이 시험의 전제가 틀렸다")
        bad, seen = C.semantic_check(self.orig, self.built, BASE)
        self.assertEqual(seen, 1)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0][1:4], (6, 10, 7))  # 원본 6B · 우리 10B · 복사 7B

    def test_fitting_name_is_not_flagged(self):
        fits = self.orig[: self.src - BASE] + b"ABC\0"
        self.assertEqual(C.semantic_check(self.orig, fits, BASE)[0], [])

    def test_unpatched_truncates_when_run(self):
        cpu = run_cpu(self.built, LONG)
        cpu.r[7] = DST
        self.assertNotEqual(dest(cpu, 104), LONG)  # 7B 만 들어가고 NUL 이 없다

    def test_patched_copies_to_nul_and_passes_check(self):
        pl = P.plan_f1(self.built, 0)
        self.assertIsNotNone(pl)
        self.assertEqual((pl["rb"], pl["imm0"], pl["n"]), (7, 104, 6))
        new = bytearray(self.built)
        for c in pl["nop"]:
            new[c : c + 2] = P.NOP
        new[2 : 2 + P.F1_LOOP] = P.loop_f1(BASE + 2, pl["rb"], pl["imm0"])
        new = bytes(new)
        # 디스어셈블로 되읽는다(손인코딩 금지 규율) — 연속 디코드
        import sh2

        self.assertGreater(len(sh2.verify(new[2 : 2 + P.F1_LOOP], BASE + 2, P.F1_LOOP)), 5)
        self.assertEqual(C.semantic_check(self.orig, new, BASE)[0], [])
        cpu = run_cpu(new, LONG)
        self.assertEqual(dest(cpu, 104), LONG)  # 끝까지 + NUL
        self.assertEqual(cpu.r[2], 0xCAFE0000, "남의 `mov.l ..,r2` 가 제자리에서 살아 있다")

    def test_pad_is_all_nops_and_after_the_loop(self):
        pl = P.plan_f1(self.built, 0)
        a, b = pl["pad"]
        self.assertGreaterEqual(a, 2 + P.F1_LOOP)
        self.assertGreater(b, a)

    def test_unknown_shape_is_refused_not_guessed(self):
        junk = bytes(self.built)
        junk = junk[:2] + w(0x6214, 0x7300 | 99, 0x2320) + junk[8:]  # 첫 오프셋이 이어지지 않는다
        self.assertIsNone(P.plan_f1(junk, 0))


class SharedRunEntry(unittest.TestCase):
    """`bra` 로 공유 런의 중간에 뛰어드는 복사 — 길이가 진입점으로 정해진다(나무인간C)."""

    def build(self, src_text):
        code = bytearray()
        code += w(0xD100, 0xD200)  # mov.l src,r1 · mov.l dst,r2
        bra_at = len(code)
        code += w(0xA000, 0x6314)  # bra X · (지연) mov.b @r1+,r3
        # 공유 런: 4 유닛 + 꼬리(출구는 그대로 아래로 떨어진다)
        run = len(code)
        for _ in range(4):
            code += w(0x6314, 0x7201, 0x2230)
        code += w(0x6110, 0x7201, 0x2210)
        z = len(code)
        code += w(0x000B, 0x0009)
        while len(code) % 4:
            code += b"\x00\x09"
        pool = len(code)
        src_at = BASE + pool + 8
        code += src_at.to_bytes(4, "big") + DST.to_bytes(4, "big") + src_text + b"\0"
        code[1] = (pool - ((0 + 4) & ~3)) // 4
        code[3] = (pool + 4 - ((2 + 4) & ~3)) // 4
        # 런의 둘째 유닛 `mov.b r3,@r2`(= run+6+4)로 뛴다 — 지연 슬롯이 첫 글자를 읽는다
        target = run + 2 * 5 - 0  # 첫 유닛의 store(`2230`)
        target = run + 4
        disp = (target - (bra_at + 4)) // 2
        code[bra_at : bra_at + 2] = (0xA000 | (disp & 0xFFF)).to_bytes(2, "big")
        return bytes(code), src_at, z

    def test_plan_and_run(self):
        orig, src, z = self.build(b"ABCDE")
        built = orig[: src - BASE] + b"ABCDEFGHIJ\0"
        bad, seen = C.semantic_check(orig, built, BASE)
        self.assertEqual((len(bad), seen), (1, 1))
        pl = P.plan_f2m(built, BASE, 0)
        self.assertIsNotNone(pl)
        self.assertEqual(pl["z"], BASE + z)
        new = bytearray(built)
        for c in pl["nop"]:
            new[c : c + 2] = P.NOP
        at = pl["code_at"]
        self.assertGreaterEqual(pl["end"] - at, 4)
        # 이 합성 자리는 런 전체가 비므로 인라인으로 둘 수 있다
        new[at : at + P.F2_LOOP] = P.loop_f2(BASE + at, pl["z"])
        new = bytes(new)
        self.assertEqual(C.semantic_check(orig, new, BASE)[0], [])
        cpu = run_cpu(new, b"")
        self.assertEqual(dest(cpu, 0), b"ABCDEFGHIJ")

    def test_loop_f2_jump_target_encodes(self):
        code = P.loop_f2(BASE + 0x100, BASE + 0x200)
        import capstone

        md = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
        last = list(md.disasm(code, BASE + 0x100))[-2]
        self.assertEqual((last.mnemonic, last.op_str), ("bra", f"0x{BASE + 0x200:x}"))


class HeadShort(unittest.TestCase):
    def test_routine_head_short_copies_to_nul(self):
        code, _b = P.routine_head_short(BASE)
        mem = {BASE + i: v for i, v in enumerate(code + w(0x000B, 0x0009))}
        src = 0x060E2000
        mem.update({src + i: v for i, v in enumerate(b"ABCDEFGH\0zz")})
        cpu = Sh2(mem)
        cpu.pc, cpu.pr = BASE, 0x06000000
        cpu.r[7], cpu.r[2], cpu.r[1] = DST, ord("A"), src + 9 - 8  # r1 = 둘째 글자
        cpu.r[1] = src + 1
        for _ in range(500):
            if cpu.pc == 0x06000000:
                break
            cpu.step()
        self.assertEqual(dest(cpu, 0), b"ABCDEFGH")
        self.assertEqual(cpu.r[3], DST)


if __name__ == "__main__":
    unittest.main()
