"""조사 훅 기계어 회귀 — **원본 없이 돈다**.

🔴 손인코딩 기계어는 **디스어셈블로 검산한다**(레포 빌드 규율). 여기선 한 걸음 더 간다 —
   작은 SH-2 인터프리터로 **실제로 돌려** `josa.fix_buffer`(기준 구현)와 **같은 답**이
   나오는지 본다. 캡스톤은 「디코드가 되나」만 보지 「맞게 도나」는 못 본다.

⚠ 인터프리터는 훅이 쓰는 명령만 안다. 루틴에 새 명령을 넣으면 여기서 **이름 그대로**
  실패한다 — 조용히 안 도는 것보다 낫다.
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import josa
import patch_josa_hook as H
import sh2

BUF = 0x060C0000  # 시험용 버퍼 — 적재 이미지 밖(훅이 도는 조건)
TAB = 0x060A7000  # 시험용 표 자리
CODE = 0x060A6748
DRAW = 0x0607D504  # 시험용 — 꼬리 점프 목적지(실기 값과 같을 필요는 없다)
END = 0x060B0000  # 시험용 적재 끝 — `BUF` 가 이 위라 훅이 돈다 (실기 값은 편마다 유도한다)


class Sh2:
    """훅이 쓰는 명령만 아는 SH-2 인터프리터."""

    def __init__(self, mem):
        self.m = dict(mem)
        self.r = [0] * 16
        self.t = 0
        self.pc = 0

    def b(self, a):
        return self.m.get(a & 0xFFFFFFFF, 0)

    def wb(self, a, v):
        self.m[a & 0xFFFFFFFF] = v & 0xFF

    def l(self, a):
        return int.from_bytes(bytes(self.b(a + i) for i in range(4)), "big")

    def w(self, a):
        return (self.b(a) << 8) | self.b(a + 1)

    def step(self):
        op = self.w(self.pc)
        pc = self.pc
        self.pc += 2
        n, m = (op >> 8) & 0xF, (op >> 4) & 0xF
        d8, d12 = op & 0xFF, op & 0xFFF
        s8 = d8 - 256 if d8 > 127 else d8
        s12 = d12 - 4096 if d12 > 2047 else d12
        R = self.r
        if op == 0x0009:
            return
        if op & 0xF00F == 0x2006:  # mov.l Rm,@-Rn
            R[n] = (R[n] - 4) & 0xFFFFFFFF
            for i in range(4):
                self.wb(R[n] + i, (R[m] >> (24 - 8 * i)) & 0xFF)
        elif op & 0xF00F == 0x6006:  # mov.l @Rm+,Rn
            R[n] = self.l(R[m])
            R[m] = (R[m] + 4) & 0xFFFFFFFF
        elif op & 0xF00F == 0x6003:  # mov Rm,Rn
            R[n] = R[m]
        elif op & 0xF000 == 0xE000:  # mov #imm,Rn
            R[n] = s8 & 0xFFFFFFFF
        elif op & 0xF000 == 0xD000:  # mov.l @(d,pc),Rn
            R[n] = self.l(((pc + 4) & ~3) + d8 * 4)
        elif op & 0xF00F == 0x6000:  # mov.b @Rm,Rn
            v = self.b(R[m])
            R[n] = v | 0xFFFFFF00 if v & 0x80 else v
        elif op & 0xF00F == 0x000C:  # mov.b @(r0,Rm),Rn
            v = self.b(R[0] + R[m])
            R[n] = v | 0xFFFFFF00 if v & 0x80 else v
        elif op & 0xF00F == 0x2000:  # mov.b Rm,@Rn
            self.wb(R[n], R[m])
        elif op & 0xF00F == 0x600C:  # extu.b
            R[n] = R[m] & 0xFF
        elif op & 0xF000 == 0x7000:  # add #imm,Rn
            R[n] = (R[n] + s8) & 0xFFFFFFFF
        elif op & 0xF00F == 0x300C:  # add Rm,Rn
            R[n] = (R[n] + R[m]) & 0xFFFFFFFF
        elif op & 0xF00F == 0x3008:  # sub
            R[n] = (R[n] - R[m]) & 0xFFFFFFFF
        elif op & 0xF00F == 0x3000:  # cmp/eq
            self.t = int(R[n] == R[m])
        elif op & 0xF00F == 0x3002:  # cmp/hs (unsigned Rn >= Rm)
            self.t = int(R[n] >= R[m])
        elif op & 0xF00F == 0x2008:  # tst
            self.t = int((R[n] & R[m]) == 0)
        elif op & 0xF00F == 0x200B:  # or
            R[n] |= R[m]
        elif op & 0xF0FF == 0x4018:  # shll8
            R[n] = (R[n] << 8) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4028:  # shll16
            R[n] = (R[n] << 16) & 0xFFFFFFFF
        elif op & 0xF0FF == 0x4019:  # shlr8
            R[n] = (R[n] & 0xFFFFFFFF) >> 8
        elif op & 0xF0FF == 0x4001:  # shlr
            R[n] = (R[n] & 0xFFFFFFFF) >> 1
        elif op & 0xF0FF == 0x4009:  # shlr2
            R[n] = (R[n] & 0xFFFFFFFF) >> 2
        elif op & 0xFF00 == 0xC900:  # and #imm,r0
            R[0] &= d8
        elif op & 0xFF00 == 0xC800:  # tst #imm,r0
            self.t = int((R[0] & d8) == 0)
        elif op & 0xF00F == 0x2009:  # and Rm,Rn
            R[n] &= R[m]
        elif op & 0xFF00 == 0x8900:  # bt
            if self.t:
                self.pc = pc + 4 + s8 * 2
        elif op & 0xFF00 == 0x8B00:  # bf
            if not self.t:
                self.pc = pc + 4 + s8 * 2
        elif op & 0xF000 == 0xA000:  # bra (지연 슬롯)
            tgt = pc + 4 + s12 * 2
            self.step()
            self.pc = tgt
        elif op & 0xF0FF == 0x402B:  # jmp (지연 슬롯)
            tgt = R[n]
            self.step()
            self.pc = tgt
        else:
            raise AssertionError(f"인터프리터가 모르는 명령: 0x{op:04X} @0x{pc:08X}")


def run_hook(payload, table, code, buf_bytes):
    """훅을 돌려 버퍼를 돌려준다. `jmp` 로 나가면 멈춘다."""
    mem = {}
    for i, v in enumerate(payload):
        mem[code + i] = v
    for i, v in enumerate(table):
        mem[TAB + i] = v
    for i, v in enumerate(buf_bytes):
        mem[BUF + i] = v
    cpu = Sh2(mem)
    cpu.pc = code
    cpu.r[6] = BUF
    cpu.r[15] = 0x060FF000
    for _ in range(200000):
        if cpu.pc == DRAW:  # 꼬리 점프로 원 함수에 도착 = 끝
            break
        cpu.step()
    else:
        raise AssertionError("루틴이 안 끝난다(무한 루프)")
    return bytes(cpu.b(BUF + i) for i in range(len(buf_bytes))), cpu


class Hook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codes = josa.slot_codes()
        cls.table = josa.build_table(cls.codes)
        cls.code, cls.body = H.routine(CODE, TAB, DRAW, josa.pairs(cls.codes), end=END)

    def enc(self, s):
        out = bytearray()
        for ch in s:
            out += self.codes[ch].to_bytes(2, "big") if ch in self.codes else ch.encode("cp932")
        return bytes(out)

    def both(self, s):
        """기계어 결과와 기준 구현 결과를 같이 낸다."""
        raw = self.enc(s) + b"\x00" * 8
        got, _ = run_hook(self.code, self.table, CODE, raw)
        ref = bytearray(raw)
        josa.fix_buffer(ref, self.table, self.codes)
        return got, bytes(ref)

    def test_disassembles_continuously(self):
        """캡스톤이 끝까지 디코드해야 한다 — 인코딩 오타를 잡는다."""
        dis = sh2.verify(self.code, CODE, self.body)
        self.assertGreater(len(dis), 100)

    def test_matches_reference(self):
        """🔴 기계어와 기준 구현이 **같은 바이트**를 내야 한다."""
        for s in (
            "류난은(는) 달아났다.",
            "세리오스은(는) 잠에서 깼다.",
            "%c게일%c은(는) 정신을 차렸다.",
            "소니아을(를) 쓰러뜨렸다.",
            "류난이(가) 나타났다.",
            "류난은(는) 소니아을(를) 보았다.",
            "회심의 일격!!",
            "HP 30/30",
        ):
            got, ref = self.both(s)
            self.assertEqual(got, ref, s)

    def test_does_not_touch_the_loaded_image(self):
        """🔴 r6 이 적재 이미지 안이면 **한 바이트도 안 쓴다** — 원본 보호 장치."""
        raw = self.enc("류난은(는) 달아났다.") + b"\x00" * 8
        mem = {CODE + i: v for i, v in enumerate(self.code)}
        mem.update({TAB + i: v for i, v in enumerate(self.table)})
        inside = 0x060A5FE8  # 실측: 원본 문자열을 직접 그리는 호출이 준 값
        mem.update({inside + i: v for i, v in enumerate(raw)})
        cpu = Sh2(mem)
        cpu.pc, cpu.r[6], cpu.r[15] = CODE, inside, 0x060FF000
        for _ in range(10000):
            if cpu.pc == DRAW:
                break
            cpu.step()
        self.assertEqual(bytes(cpu.b(inside + i) for i in range(len(raw))), raw)

    def test_tail_jump_keeps_args(self):
        """원 함수 인자(r4~r7)를 그대로 넘겨야 한다."""
        raw = self.enc("류난은(는) 달아났다.") + b"\x00" * 8
        _, cpu = run_hook(self.code, self.table, CODE, raw)
        self.assertEqual(cpu.r[6], BUF)
        self.assertEqual(cpu.r[15], 0x060FF000, "스택을 복구해야 한다")

    def test_fits_the_free_space(self):
        """⚠ 루틴이 **둘**이라 자리가 빠듯하다 — 표(1.3KB)를 두 벌 뜨면 안 들어간다."""
        import common

        for fname, (_off, size) in H.FREE.items():
            d = common.extract(fname)
            sites = H.find_sites(d)
            blob, _at, _dis = H.build(fname, self.table, sites, H.image_end(d))
            self.assertLessEqual(len(blob) + 2 * H.MARGIN, size, fname)

    def test_both_signatures_are_unique_per_file(self):
        """🔴 자리를 손으로 적었다가 ED2 에 **참조 0곳**으로 조용히 통과할 뻔했다.

        ⚠ 자리가 **둘**이다 — 그리기(6곳)와 **줄 나누기**(1곳). 나누기에도 거는 이유는
          길이다: 그리기에서만 접으면 게임은 이미 **접기 전 길이로 줄을 나눈 뒤**다.
        """
        import common

        for fname in H.FREE:
            sites = H.find_sites(common.extract(fname))
            self.assertEqual(set(sites), {"나누기", "그리기"}, fname)
            want = {"나누기": (H.SPLIT_REFS_EXPECTED, "r4"), "그리기": (H.DRAW_REFS_EXPECTED, "r6")}
            for name, (ent, refs, arg, _pad) in sites.items():
                self.assertEqual(len(refs), want[name][0], f"{fname} {name}")
                self.assertEqual(arg, want[name][1], f"{fname} {name}")
                self.assertTrue(0x06028000 < ent < 0x060B0000, f"{fname} {name}")

    def test_image_end_is_per_file_not_a_constant(self):
        """🔴 **적재 끝은 편마다 다르다.** ED1 기준 상수를 두 편에 같이 썼다가 ED2 는 훅이
        통째로 무동작했다(2026-08-27 — 병기가 화면에 그대로 떴다).

            ED.BIN  0x875E4 → 0x060AF5E4 → 0x060B0000
            ED2.BIN 0x6CFC8 → 0x06094FC8 → **0x06095000**
        """
        import common

        ends = {}
        for fname in H.FREE:
            d = common.extract(fname)
            e = H.image_end(d)
            ends[fname] = e
            self.assertGreaterEqual(e, H.LOAD_BASE + len(d), fname)
            self.assertLess(e, H.LOAD_BASE + len(d) + 0x1000, f"{fname}: 너무 멀리 올렸다")
            self.assertEqual(e & 0xFFF, 0, f"{fname}: 4KB 정렬이 아니다")
            self.assertLess(e, H.WORKRAM_TOP, fname)
        self.assertNotEqual(
            ends["/ED.BIN"], ends["/ED2.BIN"], "두 편의 적재 끝이 같다 — 상수로 돌아갔나?"
        )

    def test_split_entry_does_not_pad(self):
        """🔴 나누기 진입점은 **꼬리를 안 채운다** — 채우면 예산을 되찾은 의미가 없다.

        그리기 진입점은 반대로 채운다(나누기를 안 거치고 바로 그려지는 경로의 안전망).
        """
        import common

        for fname in H.FREE:
            sites = H.find_sites(common.extract(fname))
            self.assertFalse(sites["나누기"][3], f"{fname}: 나누기가 꼬리를 채운다")
            self.assertTrue(sites["그리기"][3], f"{fname}: 그리기가 꼬리를 안 채운다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
