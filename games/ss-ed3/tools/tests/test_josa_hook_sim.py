"""조사 훅 스텁(SH-2)을 **작은 모의기로 실제로 돌려** 본다 — 전각 숫자 조사 · 어절 접기.

원본 이미지 없이 돈다: 스텁을 `routine()` 으로 조립하고, 스텁이 쓰는 명령(≈40종)만 흉내 내는 모의기에 올린다.
기대값은 **파이썬 쪽 기준 구현**(`ref_fold`)이다 — 스텁과 같은 규칙을 한 번 더 독립적으로 쓴 것이다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
import hangul_map as H
import patch_josa_hook as J

M32 = 0xFFFFFFFF


def s8(v):
    return v - 256 if v & 0x80 else v


def s16(v):
    return v - 65536 if v & 0x8000 else v


class Sim:
    """스텁이 쓰는 SH-2 부분집합."""

    def __init__(self):
        self.mem = {}
        self.r = [0] * 16
        self.t = 0
        self.macl = 0
        self.pc = 0

    def rb(self, a):
        return self.mem.get(a & M32, 0)

    def wb(self, a, v):
        self.mem[a & M32] = v & 0xFF

    def rl(self, a):
        return (self.rb(a) << 24) | (self.rb(a + 1) << 16) | (self.rb(a + 2) << 8) | self.rb(a + 3)

    def wl(self, a, v):
        for i in range(4):
            self.wb(a + i, v >> (24 - 8 * i))

    def load(self, a, blob):
        for i, b in enumerate(blob):
            self.mem[a + i] = b

    def run(self, start, stop, limit=200000):
        self.pc = start
        n = 0
        while self.pc != stop:
            n += 1
            assert n < limit, "무한 루프"
            self.step()
        return n

    def fetch(self, pc):
        return (self.rb(pc) << 8) | self.rb(pc + 1)

    def step(self):
        pc = self.pc
        op = self.fetch(pc)
        self.pc = pc + 2
        r = self.r
        n, m, hi = (op >> 8) & 15, (op >> 4) & 15, op >> 12
        lo, d8 = op & 15, op & 0xFF

        def delay(target):
            self.pc = pc + 2
            self.step()
            self.pc = target & M32

        if hi == 0x6:
            if lo == 0:
                r[n] = s8(self.rb(r[m])) & M32
            elif lo == 1:
                r[n] = s16((self.rb(r[m]) << 8) | self.rb(r[m] + 1)) & M32
            elif lo == 2:
                r[n] = self.rl(r[m])
            elif lo == 3:
                r[n] = r[m]
            elif lo == 4:
                r[n] = s8(self.rb(r[m])) & M32
                r[m] = (r[m] + 1) & M32
            elif lo == 6:
                r[n] = self.rl(r[m])
                r[m] = (r[m] + 4) & M32
            elif lo == 0xC:
                r[n] = r[m] & 0xFF
            elif lo == 0xD:
                r[n] = r[m] & 0xFFFF
            else:
                raise AssertionError(hex(op))
        elif hi == 0x2:
            if lo == 0:
                self.wb(r[n], r[m])
            elif lo == 1:
                self.wb(r[n], r[m] >> 8)
                self.wb(r[n] + 1, r[m])
            elif lo == 2:
                self.wl(r[n], r[m])
            elif lo == 6:
                r[n] = (r[n] - 4) & M32
                self.wl(r[n], r[m])
            elif lo == 8:
                self.t = int((r[n] & r[m]) == 0)
            elif lo == 9:
                r[n] = r[n] & r[m]
            elif lo == 0xE:
                self.macl = ((r[n] & 0xFFFF) * (r[m] & 0xFFFF)) & M32
            else:
                raise AssertionError(hex(op))
        elif hi == 0xE:
            r[n] = s8(d8) & M32
        elif hi == 0xD:
            r[n] = self.rl(((pc + 4) & ~3) + d8 * 4)
        elif hi == 0x7:
            r[n] = (r[n] + s8(d8)) & M32
        elif hi == 0x5:
            r[n] = self.rl(r[m] + lo * 4)
        elif hi == 0x3:
            if lo == 0xC:
                r[n] = (r[n] + r[m]) & M32
            elif lo == 8:
                r[n] = (r[n] - r[m]) & M32
            elif lo == 0:
                self.t = int(r[n] == r[m])
            elif lo == 2:
                self.t = int(r[n] >= r[m])
            elif lo == 7:
                a = r[n] - (1 << 32) if r[n] >> 31 else r[n]
                b = r[m] - (1 << 32) if r[m] >> 31 else r[m]
                self.t = int(a > b)
            else:
                raise AssertionError(hex(op))
        elif hi == 0x4:
            if d8 == 0x18:
                r[n] = (r[n] << 8) & M32
            elif d8 == 0x08:
                r[n] = (r[n] << 2) & M32
            elif d8 == 0x01:
                self.t = r[n] & 1
                r[n] >>= 1
            elif d8 == 0x09:
                r[n] >>= 2
            elif d8 == 0x11:
                self.t = int(not (r[n] >> 31))
            elif d8 == 0x2B:
                delay(r[n])
            else:
                raise AssertionError(hex(op))
        elif hi == 0x8:
            sub = n
            if sub == 0x8:
                self.t = int(r[0] == (s8(d8) & M32))
            elif sub == 0x9:
                if self.t:
                    self.pc = (pc + 4 + s8(d8) * 2) & M32
            elif sub == 0xB:
                if not self.t:
                    self.pc = (pc + 4 + s8(d8) * 2) & M32
            elif sub == 0x4:
                r[0] = s8(self.rb(r[m] + lo)) & M32
            elif sub == 0x0:
                self.wb(r[m] + lo, r[0])
            else:
                raise AssertionError(hex(op))
        elif hi == 0xA:
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            delay(pc + 4 + disp * 2)
        elif hi == 0xC:
            if n == 9:
                r[0] &= d8
            else:
                raise AssertionError(hex(op))
        elif op == 0x0009:
            pass
        elif (op & 0xF0FF) == 0x001A:
            r[n] = self.macl
        else:
            raise AssertionError(hex(op))


STUB, TBL = J.STUB, J.TBL
FMT_ADDR, NAME_ADDR, FRAME = 0x0C000000, 0x0C001000, 0x0C100000


def run_stub(name_kr, fmt_kr, prefix_w=13):
    """스텁을 한 번 돌려 `(r12 문자열 바이트, 서식 바이트)` 를 돌려준다."""
    return run_stub_raw(H.encode_kr(name_kr), fmt_kr, prefix_w)


def run_stub_raw(name_bytes, fmt_kr, prefix_w=13):
    bits = J.bit_table()
    tbuf = STUB + J.LIT_OFF + 36
    code = J.routine(STUB, TBL, prefix_w=prefix_w, tbuf=tbuf) + b"\x00" * J.FOLD_BUF
    sim = Sim()
    sim.load(STUB, code)
    sim.load(TBL, bits)
    name = name_bytes + b"\x00"
    fmt = fmt_kr + b"\x00" * 8
    sim.load(NAME_ADDR, name)
    sim.load(FMT_ADDR, fmt)
    # 진입 상태 — 밀어낸 6 명령이 `r12` 를 만든다
    args, argstruct = 0x0C200000, 0x0C300000
    sim.r[14] = FRAME
    sim.r[13] = 0x0C400000
    sim.wl(0x0C400000, 0x0C500000)
    sim.r[1] = 0x204
    sim.wl(FRAME + 0x204, argstruct)
    sim.wl(argstruct + 4, NAME_ADDR)
    sim.wl(FRAME + J.FRAME_FMT, FMT_ADDR + fmt_kr.index(b"%s") + 2)
    sim.r[15] = 0x0C0F0000
    # 훅이 뛰어들어 오는 자리: 스텁 첫 명령에서 시작해 `HOOK_RET` 로 빠져나올 때까지
    sim.wl(STUB + J.LIT_OFF + 16, 0xDEAD0000)  # HOOK_RET 상수를 가짜 값으로 — 도착을 잡는다
    sim.run(STUB, 0xDEAD0000)
    out = bytearray()
    p = sim.r[12]
    while sim.rb(p):
        out.append(sim.rb(p))
        p += 1
    f = bytearray()
    p = FMT_ADDR
    for _ in range(len(fmt)):
        f.append(sim.rb(p))
        p += 1
    return bytes(out), bytes(f)


def width(b):
    w, i = 0, 0
    while i < len(b):
        if b[i] >= 0x80:
            w, i = w + 2, i + 2
        else:
            w, i = w + 1, i + 1
    return w


def ref_fold(text, prefix_w, limit=34):
    """기준 구현 — `text` 는 공백으로 시작하는 바이트열(공백 + 어절들). 공백을 0x0D 로 바꾼 것."""
    out = bytearray(text)
    col, i = prefix_w, 0
    while i < len(out):
        assert out[i] == 0x20
        j = i + 1
        while j < len(out) and out[j] != 0x20:
            j += 2 if out[j] >= 0x80 else 1
        w = width(bytes(out[i + 1 : j]))
        if col + 1 + w > limit:
            out[i] = 0x0D
            col = w
        else:
            col += 1 + w
        i = j
    return bytes(out)


FMT = H.encode_kr("쥬리오 일행은%s\x1f을(를) 얻었다.\x10")
PW = width(H.encode_kr("쥬리오 일행은"))


class Fold(unittest.TestCase):
    def test_short_name_stays_one_line(self):
        out, fmt = run_stub("약초", FMT, PW)
        self.assertEqual(out, H.encode_kr(" 약초") + H.encode_kr("를 얻었다."))
        self.assertEqual(fmt[fmt.index(b"%s") + 2 :][:2], b"\x10\x00")
        self.assertNotIn(0x0D, out)

    def test_long_name_folds_at_word_boundary(self):
        out, _ = run_stub("순례자의 마음가짐", FMT, PW)
        self.assertEqual(out, ref_fold(H.encode_kr(" 순례자의 마음가짐을 얻었다."), PW))
        self.assertIn(0x0D, out)

    def test_many_names_match_reference(self):
        names = ["약초", "단검", "순례자의 마음가짐", "마법저항의 반지1", "검사교본 3", "가죽 갑옷", "제１", "제３"]
        for nm in names:
            josa = "을" if J.batchim_of(H.encode_kr(nm), J.bit_table()) else "를"
            want = ref_fold(H.encode_kr(" " + nm + josa + " 얻었다."), PW)
            out, _ = run_stub(nm, FMT, PW)
            self.assertEqual(out, want, nm)

    def test_roman_numeral_names_fold_too(self):
        """정본에만 있고 게임 자료엔 없는 `…Ⅰ~Ⅲ` 이름 — 도구 인코딩(`encode_kr`)이 못 하는 `Ⅰ`(SJIS 0x8754~)를 그대로 넣어 본다.

        스텁은 이 글자의 받침을 못 정해(슬롯 밖) **병기를 그대로 둔다** — 접기만 한다. 이름이 게임 자료에 없어 화면엔 안 나온다."""

        def enc(t):
            return b"".join(c.encode("cp932") if c in "ⅠⅡⅢ" else H.encode_kr(c) for c in t)

        for nm in ("행운의 반지Ⅰ", "민첩의 반지Ⅱ", "마법저항의 반지Ⅲ", "지혜의 반지Ⅰ"):
            sim_name = enc(nm)
            out, _ = run_stub_raw(sim_name, FMT, PW)
            want = ref_fold(b" " + sim_name + H.encode_kr("을(를) 얻었다."), PW)
            self.assertEqual(out, want, nm)

    def test_no_marker_keeps_old_behaviour(self):
        fmt = H.encode_kr("%s을(를) 샀다.\x10")
        out, f = run_stub("약초", fmt, PW)
        self.assertEqual(out, H.encode_kr("약초"))
        self.assertTrue(f.startswith(b"%s" + H.encode_kr("를 샀다.")))


class FullwidthDigit(unittest.TestCase):
    def pick(self, nm):
        fmt = H.encode_kr("%s을(를) 샀다.\x10")
        _, f = run_stub(nm, fmt, PW)
        return f[2:4]

    def test_reads_like_the_sound(self):
        #   일→을 · 이→를 · 삼→을 (반각 숫자와 같은 표)
        eul, reul = H.encode_kr("을"), H.encode_kr("를")
        self.assertEqual(self.pick("제１"), eul)
        self.assertEqual(self.pick("제２"), reul)
        self.assertEqual(self.pick("제３"), eul)
        self.assertEqual(self.pick("제４"), reul)  # 사
        self.assertEqual(self.pick("제９"), reul)  # 구
        self.assertEqual(self.pick("제０"), eul)  # 영

    def test_halfwidth_unchanged(self):
        eul, reul = H.encode_kr("을"), H.encode_kr("를")
        self.assertEqual(self.pick("반지1"), eul)
        self.assertEqual(self.pick("반지2"), reul)


if __name__ == "__main__":
    unittest.main()


class NameJosaStub(unittest.TestCase):
    """`08`(이름 호출) 뒤 「이라니」 표지 — 이름 끝소리로 제자리 고침(`patch_josa_hook.name_routine`)."""

    SCRIPT = 0x0C600000
    NAMEBUF = 0x0C610000
    ENGINE = 0x0C700000  # r10
    R12 = 0x0C720000
    LITADDR = J.NAME_LIT

    def run_once(self, sim, name_kr, script):
        rani, i_, nop2 = J.name_marker()
        sim.load(self.NAMEBUF, H.encode_kr(name_kr) + b"\x00")
        sim.load(self.SCRIPT, script)
        sim.wl(self.LITADDR, self.NAMEBUF)
        sim.r[10] = self.ENGINE
        sim.r[12] = self.R12
        sim.wl(sim.r[12], 1)  # 스택 깊이 단어(상위 2B 가 값) — 임의
        sim.wb(self.R12, 0)
        sim.wb(self.R12 + 1, 3)
        sim.wl(self.ENGINE + 4, self.SCRIPT)  # 스크립트 포인터(08 바이트를 읽고 난 뒤)
        sim.r[15] = 0x0C0F0000
        sim.wl(J.NAME_LIT, self.NAMEBUF)
        sim.run(J.CA.NAMEJ, 0xDEAD0000)
        return bytes(sim.rb(self.SCRIPT + i) for i in range(len(script)))

    def sim(self):
        J.bit_table()
        sim = Sim()
        orig = J.NAME_HOOK_ORIG
        code = J.name_routine(J.CA.NAMEJ, TBL, orig)
        sim.load(J.CA.NAMEJ, code)
        sim.load(TBL, J.bit_table())
        sim.wl(J.CA.NAMEJ + J.NAME_LIT_OFF + 16, 0xDEAD0000)  # 복귀 상수를 가짜로 — 도착을 잡는다
        return sim

    def forms(self):
        rani, i_, nop2 = J.name_marker()
        return i_ + rani, nop2 + rani  # (받침 있음 꼴, 받침 없음 꼴)

    def test_vowel_batchim_digit(self):
        sim = self.sim()
        hasb, nob = self.forms()
        tail = b"\x0d" + H.encode_kr("보는") + b"\x00"
        #   모음 끝 → 라니 · 받침 끝 → 이라니 · 멱등(다시 돌려도 맞다) · 두 꼴 어디서 시작해도 같다
        for name, want in (
            ("약초", nob),
            ("해독약", hasb),
            ("약초", nob),
            ("해독약", hasb),
            ("단검", hasb),
            ("구슬", hasb),
            ("행운의 반지", nob),
            ("행운의 반지2", nob),  # 2 → 이 → 받침 없음
            ("행운의 반지1", hasb),  # 1 → 일 → 받침 있음
            ("검사교본 3", hasb),
        ):
            for start in (hasb, nob):
                got = self.run_once(sim, name, start + tail)
                self.assertEqual(got, want + tail, (name, start.hex()))

    def test_lowered_names(self):
        """아이템 이름은 **내린 판** 슬롯으로 나간다(실화면 11-10: 「신앙의 부적」이 라니로 떨어졌다)."""
        sim = self.sim()
        hasb, nob = self.forms()
        tail = b"\x0d" + H.encode_kr("보는") + b"\x00"
        low = {**H.load(), **H.load_low()}
        low_enc = lambda t: H.encode_kr(t, low)  # noqa: E731
        for name, want in (("신앙의 부적", hasb), ("약초", nob), ("해독약", hasb), ("행운의 반지2", nob)):
            sim.load(self.NAMEBUF, low_enc(name) + b"\x00")
            for start in (hasb, nob):
                sim.load(self.SCRIPT, start + tail)
                sim.wl(self.LITADDR, self.NAMEBUF)
                sim.r[10] = self.ENGINE
                sim.r[12] = self.R12
                sim.wb(self.R12, 0)
                sim.wb(self.R12 + 1, 3)
                sim.wl(self.ENGINE + 4, self.SCRIPT)
                sim.r[15] = 0x0C0F0000
                sim.run(J.CA.NAMEJ, 0xDEAD0000)
                got = bytes(sim.rb(self.SCRIPT + i) for i in range(len(want + tail)))
                self.assertEqual(got, want + tail, (name, start.hex()))

    def test_non_marker_untouched(self):
        sim = self.sim()
        other = H.encode_kr("인가요?") + b"\x0d\x00"
        got = self.run_once(sim, "약초", other)
        self.assertEqual(got, other)
        other2 = H.encode_kr("이라고") + b"\x00"  # 앞 두 글자가 비슷해도 「라니」가 아니면 그대로
        self.assertEqual(self.run_once(sim, "약초", other2), other2)

    def test_empty_name_untouched(self):
        sim = self.sim()
        hasb, nob = self.forms()
        got = self.run_once(sim, "", hasb + b"\x00")
        self.assertEqual(got, hasb + b"\x00")
