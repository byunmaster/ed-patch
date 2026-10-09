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
HTAB = 0x060A7800  # 시험용 반각 표 자리 (실기는 한글 표 바로 뒤)
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


def run_hook(payload, table, code, buf_bytes, half=None):
    """훅을 돌려 버퍼를 돌려준다. `jmp` 로 나가면 멈춘다."""
    mem = {}
    for i, v in enumerate(payload):
        mem[code + i] = v
    for i, v in enumerate(table):
        mem[TAB + i] = v
    for i, v in enumerate(half if half is not None else josa.build_half_table()):
        mem[HTAB + i] = v
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
        cls.half = josa.build_half_table()
        cls.code, cls.body = H.routine(CODE, TAB, HTAB, DRAW, josa.pairs(cls.codes), end=END)

    def enc(self, s):
        out = bytearray()
        for ch in s:
            out += self.codes[ch].to_bytes(2, "big") if ch in self.codes else ch.encode("cp932")
        return bytes(out)

    def both(self, s):
        """기계어 결과와 기준 구현 결과를 같이 낸다."""
        raw = self.enc(s) + b"\x00" * 8
        got, _ = run_hook(self.code, self.table, CODE, raw, self.half)
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
            # 🔴 **반각으로 끝나는 이름** — 개체 접미가 붙은 몬스터가 그렇다(171칸).
            #    앞말이 우리 슬롯 코드가 아니라, 안 보면 `prev` 가 직전 한글 음절에 머물러
            #    `슬라임A` 가 「임」으로 판정된다 — 실기에서 **「슬라임A을」**이 나왔다.
            "슬라임A을(를) 해치웠다.",
            "니어트허니J이(가) 나타났다.",
            "슬라임A은(는) 달아났다.",
            "%c슬라임A%c을(를) 해치웠다.",  # 색 코드가 껴도 이름을 본다
            "슬라임Ａ을(를) 해치웠다.",  # 🔴 전각 접미(원판처럼) — 「임」으로 판정되면 안 된다
            "%c니어트허니Ｊ%c이(가) 나타났다.",
            "엘Ｍ을(를) 보았다.",
            "엘M을(를) 보았다.",  # 엠 — 받침 있는 몇 안 되는 알파벳
            "3을(를) 골랐다.",  # 삼 — 받침
            "2을(를) 골랐다.",  # 이 — 무받침
        ):
            got, ref = self.both(s)
            self.assertEqual(got, ref, s)

    def test_half_width_suffix_picks_by_how_the_letter_is_read(self):
        """🔴 개체 접미는 **한국어로 읽은 소리**로 고른다 — A~J 는 전부 무받침이다.

        받침이 있는 건 L(엘)·M(엠)·N(엔)뿐이라, 몬스터 이름은 모두 「를/는/가」가 맞다.
        ⚠ 기계어 결과로 본다(기준 구현과 대조는 위 테스트가 한다).
        """
        for ch in "AFJLMN":  # A~J 는 개체 접미가 실제로 쓰는 글자, L·M·N 은 받침이 있는 셋
            got, ref = self.both(f"슬라임{ch}을(를) 해치웠다.")
            self.assertEqual(got, ref, ch)
            expect = "을" if ch in "LMN" else "를"
            self.assertEqual(
                got[: len(self.enc(f"슬라임{ch}{expect}"))],
                self.enc(f"슬라임{ch}{expect}"),
                f"{ch}: {expect} 가 아니다",
            )

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

        ⚠ 함수는 **둘**을 찾는다 — 그리기(6곳)와 줄 나누기(1곳). 나누기에는 **안 걸지만**
          (`test_split_entry_is_never_hooked`) 시그니처는 계속 검산한다 — 원본이 바뀌면
          여기서 먼저 울어야 한다. 그래서 `find_sites` 가 아니라 `find_fn` 을 직접 본다.
        """
        import common

        want = [
            (H.DRAW_SIG, H.DRAW_REFS_EXPECTED, "그리기"),
            (H.SPLIT_SIG, H.SPLIT_REFS_EXPECTED, "줄 나누기"),
        ]
        for fname in H.FREE:
            d = common.extract(fname)
            for sig, refs_expected, what in want:
                ent, refs = H.find_fn(d, sig, refs_expected, what)
                self.assertEqual(len(refs), refs_expected, f"{fname} {what}")
                self.assertTrue(0x06028000 < ent < 0x060B0000, f"{fname} {what}")
            sites = H.find_sites(d)
            self.assertEqual(sites["그리기"][1].__len__(), H.DRAW_REFS_EXPECTED, fname)
            self.assertEqual(sites["그리기"][2], "r6", fname)

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

    def test_draw_entry_pads_its_tail(self):
        """🔴 그리기 진입점은 **꼬리를 채운다** — 줄어든 두 칸에 글리프 0 이 찍혀 화면에
        흰 네모가 남았다(2026-08-26 실기). 반각 공백 넷으로 폭을 되돌린다.
        """
        import common

        for fname in H.FREE:
            sites = H.find_sites(common.extract(fname))
            self.assertTrue(sites["그리기"][3], f"{fname}: 그리기가 꼬리를 안 채운다")

    def test_split_entry_is_installed_but_inert(self):
        """🔴 나누기 진입점은 **걸되 즉시 되돌린다** — 훑지도, 빼지도 않는다.

        훑으면 BGM 이 죽는다(이 자리의 `r4` 는 아직 안 채워진 회차가 있어, 범위 가드를
        세워도 남의 버퍼가 통과한다 — 2026-08-26 게임 정지 · 2026-09-01 BGM 소실).
        🔴 그런데 **설치까지 빼면 BGM 이 다시 죽는다**(2026-09-01 실기). 원본에 더 가까운
        쪽이 죽으므로 아직 설명이 안 된다 — 빌드 이분으로 이 하나만 남겨 확인했다:

            설치 안 함   c998b0452638   BGM ❌
            설치 + 무동작 2c0ee330b3ef   BGM ✅

        ⇒ 실측을 따른다. ⚠ 어느 쪽으로든 되돌리려면 **BGM 을 실기로 보이고** 같이 지운다.
        """
        import common

        self.assertIn("나누기", H.DRY_SITES, "나누기가 무동작이 아니다")
        self.assertNotIn("나누기", H.SKIP_SITES, "나누기를 통째로 빼면 BGM 이 죽는다")
        for fname in H.FREE:
            sites = H.find_sites(common.extract(fname))
            self.assertIn("나누기", sites, f"{fname}: 나누기 진입점이 안 걸린다")
            self.assertIn("그리기", sites, f"{fname}: 그리기가 사라졌다")

    def test_inert_entry_returns_before_touching_anything(self):
        """🔴 무동작이 정말 무동작인가 — 버퍼를 **한 바이트도** 안 건드려야 한다."""
        code, body = H.routine(CODE, TAB, HTAB, DRAW, josa.pairs(self.codes), dry=True, end=END)
        raw = self.enc("류난은(는) 달아났다.") + b"\x00" * 8
        got, _ = run_hook(code, self.table, CODE, raw, self.half)
        self.assertEqual(got, raw, "무동작인데 버퍼가 바뀌었다")
        sh2.verify(code, CODE, body)  # 디스어셈블도 끝까지 되어야 한다


if __name__ == "__main__":
    unittest.main(verbosity=2)
