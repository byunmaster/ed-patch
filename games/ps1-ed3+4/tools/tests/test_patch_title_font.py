"""타이틀 BIOS 폰트 리다이렉트 — 원본 없이 도는 회귀(2026-09-27 · 10-05).

에뮬 없이는 못 잡는 사고라(분기 어긋남 · 로드 지연 · 비정렬 점프), 우리가 만든 명령 부분집합만
도는 **미니 MIPS 해석기**로 글리프 스텁을 실제 실행해 각 코드가 자기 글리프 주소를 돌려주는지 본다.
(10-05: 부팅 복사 스텁은 없앴다 — 글꼴·스텁은 MD05.BIN 꼬리에 디스크가 직접 채운다.)
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import patch_title_font as p

REG_NAMES = {v: k for k, v in p.REG.items()}
MAX_STEPS = 100_000  # 이걸 넘으면 무한루프로 본다(예전 사고가 이랬다)


def run_mips(code, mem, start_addr, ra_sentinel=0):
    """아주 작은 MIPS 해석기 — 우리 스텁이 쓰는 명령만. `mem` 은 {주소: 바이트} 딕셔너리.

    지연 슬롯을 흉내 낸다: 분기/점프를 만나면 **다음 명령(지연 슬롯)을 먼저 실행**한 뒤
    목표로 뛴다.
    """
    regs = [0] * 32
    pc = start_addr
    steps = 0
    while pc != ra_sentinel:
        steps += 1
        if steps > MAX_STEPS:
            raise AssertionError(f"{steps} 스텝을 넘었다 — 무한루프로 본다(PC=0x{pc:X})")
        word = code[pc]
        op = word >> 26
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm

        if op == 0x05:  # bne
            branch_to = (pc + 4 + simm * 4) if regs[rs] != regs[rt] else None
        elif op == 0x02:  # j
            branch_to = (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        elif op == 0x00 and (word & 0x3F) == 0x08:  # jr
            branch_to = regs[rs]
        elif word == 0 or op in (0x09, 0x0D, 0x0C, 0x0F, 0x24, 0x28):
            branch_to = "not_a_branch"
            _exec_one(word, regs, mem, pc)
        else:
            raise AssertionError(f"미지원 명령 0x{word:08X} @ 0x{pc:X}")

        if branch_to == "not_a_branch":
            pc += 4
            continue
        # 지연 슬롯을 먼저 실행하고서 뛴다(목표가 None 이면 그냥 다음 명령).
        _exec_one(code[pc + 4], regs, mem, pc + 4)
        pc = branch_to if branch_to is not None else pc + 8
    return regs, mem


def _exec_one(word, regs, mem, pc):
    """분기가 아닌 단순 명령 하나 — 본문에서도, 지연 슬롯에서도 쓴다."""
    op = word >> 26
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if word == 0:
        return
    if op == 0x09:
        regs[rt] = (regs[rs] + simm) & 0xFFFFFFFF
    elif op == 0x0D:
        regs[rt] = (regs[rs] | imm) & 0xFFFFFFFF
    elif op == 0x0C:
        regs[rt] = regs[rs] & imm
    elif op == 0x0F:
        regs[rt] = (imm << 16) & 0xFFFFFFFF
    elif op == 0x24:  # lbu
        regs[rt] = mem.get((regs[rs] + simm) & 0xFFFFFFFF, 0)
    elif op == 0x0B:  # sltiu
        regs[rt] = 1 if regs[rs] < (simm & 0xFFFFFFFF) else 0
    elif op == 0 and (word & 0x3F) == 0x00:  # sll
        regs[(word >> 11) & 0x1F] = (regs[rt] << ((word >> 6) & 0x1F)) & 0xFFFFFFFF
    elif op == 0 and (word & 0x3F) == 0x21:  # addu
        regs[(word >> 11) & 0x1F] = (regs[rs] + regs[rt]) & 0xFFFFFFFF
    elif op == 0 and (word & 0x3F) == 0x23:  # subu
        regs[(word >> 11) & 0x1F] = (regs[rs] - regs[rt]) & 0xFFFFFFFF
    elif op == 0x28:
        mem[(regs[rs] + simm) & 0xFFFFFFFF] = regs[rt] & 0xFF
    else:
        raise AssertionError(f"지연 슬롯에 예상 밖 명령 0x{word:08X}")
    regs[0] = 0


# 지명까지 넣은 실제 규모(≈156자)를 원본 없이 흉내 낸다 — B 자리(YUKI8 꼬리)까지 쓰게 된다.
GLYPHS = (
    p.GLYPHS
    + [
        c
        for c in "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허고노도로모보소오조초코토포호구누두루무부수우주추쿠투푸후그느드르므브스으즈츠크트프흐기니디리미비시이지치키티피히각난달람만방상앙장창칸탄팔한건널덕럭먹벌설얼적천컴털펄헐곡논돌롬몽복솔옥종촌콩톱폭혹국눈둘룸물불술울줄춘쿵툴풀훈극는들름믈블슬을즐측큼틀플흙긴닐딸림밀빌실일질칠킬틸필힐"
        if c not in p.GLYPHS
    ][:140]
)


def _load(parts):
    """A·B 자리를 {주소: 바이트} 로 깐다 — 스텁도 이 메모리에서 읽는다."""
    mem = {}
    bases = [(p.FONT_DEST, parts["a"])] + [(ram + size, parts[nm]) for nm, size, _s, ram in p.TAILS]
    for base, blob in bases:
        for i, b in enumerate(blob):
            mem[base + i] = b
    code = {
        a: struct.unpack("<I", bytes(mem[a + k] for k in range(4)))[0]
        for a in range(p.FONT_DEST, p.FONT_DEST + p.STUB_WORDS * 4, 4)
    }
    return code, mem


class TestGlyphHookStub(unittest.TestCase):
    def test_each_code_unpacks_its_own_cell(self):
        """코드마다 셀 버퍼에 **그 글자의 30B 셀**이 펼쳐지고 그 주소가 돌아온다(A·B 양쪽)."""
        parts, entry = p.build_payload(GLYPHS)
        for nm, *_r in p.TAILS:
            self.assertTrue(parts[nm], f"{nm} 자리를 안 썼다 — 시험이 일부만 돈다")
        code, mem = _load(parts)
        seen = set()
        for idx, ch in enumerate(GLYPHS):
            regs = [0] * 32
            regs[p.REG["a0"]] = p.CODE_BASE + idx
            regs[p.REG["ra"]] = 0xDEADBEEF
            _run_until_jr(code, regs, mem, entry)
            v0 = regs[p.REG["v0"]]
            # 🔴 글자마다 다른 칸 — 한 칸을 돌려 쓰면 한 줄이 전부 마지막 글자로 나온다(10-05 실측)
            self.assertNotIn(v0, seen, f"{ch}: 셀 칸이 겹친다")
            seen.add(v0)
            got = bytes(mem.get(v0 + k, 0) for k in range(30))
            self.assertEqual(got, p._pack_bios_cell(ch), f"{ch}(#{idx})")


class TestFallback(unittest.TestCase):
    def test_non_glyph_code_reaches_fallback(self):
        parts, entry = p.build_payload(GLYPHS)
        code, mem = _load(parts)
        fb = entry + p.STUB_WORDS * 4 - 16  # 마지막 4워드 = fallback
        for c in (0x8140, p.CODE_BASE - 1, p.CODE_BASE + len(GLYPHS)):
            regs = [0] * 32
            regs[p.REG["a0"]] = c
            pc = entry
            for _ in range(40):
                if pc == fb:
                    break
                w = code[pc]
                if (w >> 26) in (0x04, 0x05):
                    eq = regs[(w >> 21) & 31] == regs[(w >> 16) & 31]
                    taken = eq if (w >> 26) == 0x04 else not eq
                    _exec_one(code[pc + 4], regs, mem, pc + 4)
                    imm = w & 0xFFFF
                    imm = imm - 0x10000 if imm & 0x8000 else imm
                    pc = pc + 4 + imm * 4 if taken else pc + 8
                else:
                    _exec_one(w, regs, mem, pc)
                    pc += 4
            self.assertEqual(pc, fb, hex(c))


def _run_until_jr(code, regs, mem, pc, max_steps=10_000):
    """`jr ra` 를 만나면 멈추는 축소판 — 글리프 훅은 분기·점프가 단순해 이걸로 충분하다."""
    steps = 0
    while True:
        steps += 1
        if steps > max_steps:
            raise AssertionError("무한루프")
        word = code[pc]
        if (word >> 26) == 0 and (word & 0x3F) == 0x08:  # jr
            rs = (word >> 21) & 0x1F
            target = regs[rs]
            dw = code[pc + 4]
            _exec_one(dw, regs, mem, pc + 4)
            if target == 0xDEADBEEF:
                return
            pc = target
            continue
        if (word >> 26) in (0x04, 0x05):  # beq / bne
            rs = (word >> 21) & 0x1F
            rt = (word >> 16) & 0x1F
            imm = word & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            taken = (regs[rs] != regs[rt]) if (word >> 26) == 0x05 else (regs[rs] == regs[rt])
            dw = code[pc + 4]
            _exec_one(dw, regs, mem, pc + 4)
            pc = (pc + 4 + simm * 4) if taken else pc + 8
            continue
        _exec_one(word, regs, mem, pc)
        pc += 4


class TestStubAlignment(unittest.TestCase):
    def test_hook_jumps_to_stub_start(self):
        """🔴 훅의 `j` 목표가 스텁 시작과 정확히 같아야 한다 — 하위 2비트는 버려진다(2026-10-05)."""
        _, entry = p.build_payload(GLYPHS)
        self.assertEqual(entry % 4, 0)
        word = struct.unpack("<I", p.build_hook_patch()[:4])[0]
        self.assertEqual((word & 0x03FFFFFF) << 2 | (entry & 0xF0000000), entry)


class TestLoadDelay(unittest.TestCase):
    def test_no_load_delay_hazard_in_stub(self):
        """🔴 R3000 로드 지연 — 복사 루프가 이걸 어겨 글꼴이 1바이트 밀렸다(2026-10-05)."""
        import engine_patch

        parts, entry = p.build_payload(GLYPHS)
        words = list(struct.unpack(f"<{p.STUB_WORDS}I", parts["a"][: p.STUB_WORDS * 4]))
        engine_patch.verify(words, entry)


class TestTails(unittest.TestCase):
    def test_all_parts_fit_their_slots(self):
        """🔴 각 조각이 제 멤버의 섹터 여유 안 — 다음 멤버를 덮으면 남의 자료가 깨진다."""
        parts, _ = p.build_payload(GLYPHS)
        self.assertEqual(p.FONT_DEST % 4, 0)
        self.assertLessEqual((p.FONT_DEST - p.OVERLAY_RAM) + len(parts["a"]), p.MD05_SLOT)
        for nm, size, slot, _ram in p.TAILS:
            self.assertLessEqual(len(parts[nm]), slot - size, nm)


class TestPlaceEncoding(unittest.TestCase):
    def test_centered_like_original(self):
        code = {ch: p.CODE_BASE + i for i, ch in enumerate(GLYPHS)}
        out = p.encode_place("가나다", code)
        self.assertEqual(len(out), 16)
        self.assertEqual(out[12:], bytes(4))
        self.assertEqual(out[:2], b"\x81\x40")  # 남는 3칸 → 왼쪽 1 · 오른쪽 2 (원문 규칙)
        self.assertEqual(out[8:12], b"\x81\x40\x81\x40")

    def test_seven_cells_keep_terminator(self):
        code = {ch: p.CODE_BASE + i for i, ch in enumerate(GLYPHS)}
        out = p.encode_place("가나다 라마바", code)
        self.assertEqual(len(out), 16)
        self.assertEqual(out[14:], b"\x00\x00", "7자면 종결 2B 가 남아야 한다")


class TestCodeValidity(unittest.TestCase):
    def test_codes_pass_the_printers_validity_check(self):
        """🔴 글자 출력 루프(0x80012DE0)는 (code+0x7EC0)&0xFFFF < 0x1731 만 통과시킨다 — 밖은 공백이 된다."""
        for i in range(len(GLYPHS)):
            self.assertLess((p.CODE_BASE + i + 0x7EC0) & 0xFFFF, 0x1731, i)


if __name__ == "__main__":
    unittest.main()
