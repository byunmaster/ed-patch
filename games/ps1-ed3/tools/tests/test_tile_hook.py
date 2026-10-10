"""안 B 타일 합성 훅(`tile_hook`)을 미니 MIPS 해석기로 돌려 **파이썬 모델(`tilecomp`)과 타일 단위로 대조**한다.

엔진 쪽 동작(글리프 소스 = a1+a0 에서 18B → 타일, rect = fp+0x40/0x42)과 훅이 직접 부르는 `LoadImage` 를 같이 흉내 내
줄 하나를 흘린 뒤의 **VRAM 타일 상태**가 모델과 같은지 본다. 원본 없이 돈다.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine_patch
import tile_hook
import tilecomp

FONT = 0x8009E170
EXPAND = 0x800A620C
SLOT_TAB = 0x800DE4B8
SLOTBASE = 0x5A
LOADIMAGE = 0x8008A8DC
FP = 0x801F0000
HALF = (0x0F0, 0x0F1)  # 반 칸 글자 코드(공백·부호 흉내)
BLANK = 0x0F0
MARK_EUN = 0x7000  # 조사 표지 코드(은/는)
RA_END = 0xDEAD0000


def glyph_bytes(code):
    """코드마다 다른 18B — 12행 × 12비트가 겹치지 않는 무늬(검사용)."""
    if code == BLANK:  # 공백 글리프는 비어 있다(「(으)」 안 그림 = 공백 글리프)
        return bytes(18)
    rows = [((code * 37 + r * 91 + 1) * 0x9E5) & 0xFFF or 1 for r in range(12)]
    return tilecomp.pack(rows)


def expand_entry(b):
    return (b * 0x01000193 ^ 0x5A5A5A00) & 0xFFFFFFFF


INV_EXPAND = {expand_entry(b): b for b in range(256)}


def slot_v(s):
    return ((s % 64) * 4) | ((s // 64 + 1) << 8)


def slot_of_rect(x, y):
    return (y - 1) * 64 + (x - 0x140)


class Sim:
    def __init__(self, glyphs, cols=24, rows=2, josa=None, y=-24):
        self.p = engine_patch.PATCH["ed3"]
        self.mem = {}
        self.vram = {}  # 슬롯 → 12행
        self.cols = cols
        self.glyphs = glyphs
        p = self.p
        words, labels = tile_hook.hooks_b("ed3", len(josa["blist"]) if josa else 0, with_josa=josa is not None)
        self.prog = {p["dead"] + 4 * i: w for i, w in enumerate(words)}
        mwords, mbase = tile_hook.msg_stub("ed3", labels)
        self.prog.update({mbase + 4 * i: w for i, w in enumerate(mwords)})
        for c in glyphs:
            for i, b in enumerate(glyph_bytes(c)):
                self.mem[FONT + c * 18 + i] = b
        for b in range(256):
            self.w32(EXPAND + 4 * b, expand_entry(b))
        for s in range(0, 400):
            self.w16(SLOT_TAB + 2 * s, slot_v(s))
        h = p["handles"]
        self.w16(h, 0x8000)
        self.w16(h + 6, cols)
        self.w16(h + 8, rows)
        self.w16(h + 4, y & 0xFFFF)
        self.w16(h + 0xE, SLOTBASE)
        half = [c for c in HALF]
        markers = josa["markers"] if josa else [(0x7FFF, 0, 0, 0)] * tile_hook.N_MARK
        blist = josa["blist"] if josa else []
        blob = tile_hook.data_blob(p, half, markers, blist)
        for i, b in enumerate(blob):
            self.mem[p["data"] + i] = b
        self.w16(FP + 0x14, 0)  # 링 인덱스
        self.w16(FP + 0x44, 3)  # 엔진이 미리 채워 두는 rect 폭·높이
        self.w16(FP + 0x46, 13)
        self.loadimages = []

    # 메모리
    def r8(self, a):
        return self.mem.get(a, 0)

    def r16(self, a):
        return self.r8(a) | (self.r8(a + 1) << 8)

    def r32(self, a):
        return self.r16(a) | (self.r16(a + 2) << 16)

    def w16(self, a, v):
        self.mem[a] = v & 0xFF
        self.mem[a + 1] = (v >> 8) & 0xFF

    def w32(self, a, v):
        self.w16(a, v & 0xFFFF)
        self.w16(a + 2, v >> 16)

    def run_glyph(self, code, k):
        """칸 k(0 기반, 첫 줄 col = k % cols)에 글자 `code` 를 그리는 한 번 호출 — 엔진 몫(타일 쓰기)까지 흉내."""
        R = engine_patch._R
        regs = [0] * 32
        regs[R["a2"]] = code
        regs[R["a0"]] = code * 18
        regs[R["fp"]] = FP
        regs[R["ra"]] = RA_END
        self.w16(FP + 0x10, SLOTBASE + 1 + k)
        pc = self.p["dead"]
        hi = lo = 0
        steps = 0
        mem = self.mem

        def sx16(v):
            return v - 0x10000 if v & 0x8000 else v

        def s32(v):
            return v - (1 << 32) if v & 0x80000000 else v

        def step(wd, pc):
            nonlocal hi, lo
            op, rs, rt, imm = wd >> 26, (wd >> 21) & 31, (wd >> 16) & 31, wd & 0xFFFF
            rd, sa, fn = (wd >> 11) & 31, (wd >> 6) & 31, wd & 63
            nxt = None
            if op == 0:
                if fn == 0:
                    regs[rd] = (regs[rt] << sa) & 0xFFFFFFFF
                elif fn == 2:
                    regs[rd] = regs[rt] >> sa
                elif fn == 8:
                    nxt = ("jr", regs[rs])
                elif fn == 0x10:
                    regs[rd] = hi
                elif fn == 0x12:
                    regs[rd] = lo
                elif fn == 0x18:
                    lo = (regs[rs] * regs[rt]) & 0xFFFFFFFF
                    hi = 0
                elif fn == 0x1A:
                    a, b = s32(regs[rs]), s32(regs[rt])
                    q = int(a / b)
                    lo, hi = q & 0xFFFFFFFF, (a - q * b) & 0xFFFFFFFF
                elif fn in (0x21, 0x23, 0x24, 0x25, 0x2A, 0x2B):
                    a, b = regs[rs], regs[rt]
                    regs[rd] = {
                        0x21: (a + b) & 0xFFFFFFFF,
                        0x23: (a - b) & 0xFFFFFFFF,
                        0x24: a & b,
                        0x25: a | b,
                        0x2A: int(s32(a) < s32(b)),
                        0x2B: int(a < b),
                    }[fn]
                else:
                    raise AssertionError(f"해석기 미지원 R {fn:#x}")
            elif op in (4, 5, 1):
                a, b = regs[rs], regs[rt]
                take = (a == b) if op == 4 else (a != b) if op == 5 else (s32(a) < 0 if rt == 0 else s32(a) >= 0)
                nxt = ("br", pc + 4 + (sx16(imm) << 2)) if take else ("no", 0)
            elif op == 2:
                nxt = ("j", ((wd & 0x3FFFFFF) << 2) | (pc & 0xF0000000))
            elif op == 3:
                regs[31] = pc + 8
                nxt = ("j", ((wd & 0x3FFFFFF) << 2) | (pc & 0xF0000000))
            elif op in (9, 0xD, 0xC, 0xF, 0xA, 0xB):
                a = regs[rs]
                if op == 9:
                    regs[rt] = (a + sx16(imm)) & 0xFFFFFFFF
                elif op == 0xD:
                    regs[rt] = a | imm
                elif op == 0xC:
                    regs[rt] = a & imm
                elif op == 0xF:
                    regs[rt] = imm << 16
                elif op == 0xB:
                    regs[rt] = int(a < (sx16(imm) & 0xFFFFFFFF))
                else:
                    regs[rt] = int(s32(a) < sx16(imm))
            elif op in (0x20, 0x21, 0x23, 0x24, 0x25):
                a = (regs[rs] + sx16(imm)) & 0xFFFFFFFF
                if op == 0x23:
                    regs[rt] = self.r32(a)
                elif op in (0x21, 0x25):
                    v = self.r16(a)
                    regs[rt] = (sx16(v) if op == 0x21 else v) & 0xFFFFFFFF
                else:
                    regs[rt] = self.r8(a)
            elif op in (0x28, 0x29, 0x2B):
                a = (regs[rs] + sx16(imm)) & 0xFFFFFFFF
                if op == 0x28:
                    mem[a] = regs[rt] & 0xFF
                elif op == 0x29:
                    self.w16(a, regs[rt])
                else:
                    self.w32(a, regs[rt])
            else:
                raise AssertionError(f"해석기 미지원 op {op:#x}")
            regs[0] = 0
            return nxt

        while pc != RA_END:
            steps += 1
            self.assertLess = None
            assert steps < 20000, "무한루프"
            res = step(self.prog[pc], pc)
            if res is None:
                pc += 4
                continue
            slot = self.prog[pc + 4]
            kind, tgt = res
            if kind == "no":
                step(slot, pc + 4)
                pc += 8
                continue
            step(slot, pc + 4)
            if kind == "br":
                pc = tgt
            elif tgt == LOADIMAGE:
                self.load_image(regs)
                pc = regs[31]
            else:
                pc = tgt
        # 엔진 몫: a1 + a0 의 18B 를 fp+0x40/42 의 rect 타일로
        src = (regs[R["a1"]] + regs[R["a0"]]) & 0xFFFFFFFF
        rows = tilecomp.unpack(bytes(self.r8(src + i) for i in range(18)))
        x, y = self.r16(FP + 0x40), self.r16(FP + 0x42)
        self.vram[slot_of_rect(x, y)] = rows
        return src

    def load_image(self, regs):
        R = engine_patch._R
        rect = regs[R["a0"]]
        x, y = self.r16(rect), self.r16(rect + 2)
        w, h = self.r16(rect + 4), self.r16(rect + 6)
        assert (w, h) == (3, 13), (w, h)
        data = regs[R["a1"]]
        raw = bytes(INV_EXPAND[self.r32(data + 4 * i)] for i in range(18))
        self.loadimages.append((x, y, data))
        self.vram[slot_of_rect(x, y)] = tilecomp.unpack(raw)


def model_line(codes, half=HALF):
    """모델로 같은 줄을 돌려 {타일 칸 번호: 12행}."""
    line = tilecomp.Line()
    out = {}
    for c in codes:
        adv = 6 if c in half else 12
        rows = tilecomp.unpack(glyph_bytes(c))
        for t, r in line.put(rows, adv):
            out[t] = r
    return out


class TestTileHook(unittest.TestCase):
    def flow(self, codes, rows=1):
        sim = Sim(set(codes) | set(HALF), rows=rows)
        for k, c in enumerate(codes):
            sim.run_glyph(c, k)
        return sim

    def check_line(self, codes, base=0):
        sim = self.flow(codes)
        want = model_line(codes)
        for t, r in want.items():
            if t >= 24:
                continue
            self.assertEqual(sim.vram.get(SLOTBASE + t), r, f"타일 {t} (코드열 {[hex(c) for c in codes]})")

    def test_full_width_only(self):
        self.check_line([0x100, 0x101, 0x102, 0x103])

    def test_half_then_full(self):
        self.check_line([0x100, 0x0F1, 0x101, 0x102])

    def test_halves_pair(self):
        self.check_line([0x100, 0x0F0, 0x0F1, 0x101, 0x0F1, 0x0F0, 0x102])

    def test_leading_half(self):
        self.check_line([0x0F1, 0x100, 0x101])

    def test_long_line_to_row_end(self):
        codes = [0x100 + i for i in range(10)] + [0x0F0] + [0x110 + i for i in range(13)]
        self.check_line(codes)

    def test_second_row_resets(self):
        codes = [0x100, 0x0F0, 0x101] + [0x0F0] * 21  # 24칸을 채워 둘째 줄로
        sim = Sim({0x100, 0x101, 0x102, 0x0F0, 0x0F1}, rows=2)
        for k, c in enumerate(codes):
            sim.run_glyph(c, k)
        sim.run_glyph(0x102, 24)
        # 둘째 줄 첫 칸은 앞 줄 상태가 새지 않는다
        self.assertEqual(sim.vram[SLOTBASE + 24], tilecomp.unpack(glyph_bytes(0x102)))

    def test_sprites_never_touched(self):
        """스프라이트 버퍼는 한 바이트도 안 쓴다(안 B 의 핵심)."""
        sim = Sim({0x100, 0x0F0}, rows=1)
        before = dict(sim.mem)
        for k, c in enumerate([0x100, 0x0F0, 0x100]):
            sim.run_glyph(c, k)
        p = self.p = engine_patch.PATCH["ed3"]
        lo, hi = p["prims"], p["prims"] + 0xA000
        touched = [a for a in sim.mem if lo <= a < hi and sim.mem[a] != before.get(a, 0)]
        self.assertEqual(touched, [])

    def test_non_dialogue_window_is_plain(self):
        sim = Sim({0x100}, cols=4, rows=2)
        R = engine_patch._R
        src = sim.run_glyph(0x100, 3)
        self.assertEqual(src, FONT + 0x100 * 18)  # 원판 그대로
        self.assertEqual(sim.loadimages, [])


class TestMessageWindow(unittest.TestCase):
    """전투 메시지 창(18×2: 경험치·레벨업) — 공백이 반 칸으로 합성되고, 엔진이 커서를 옮기면(이름 뒤 폭 표 · 숫자 자리) 위치가 따라온다."""

    def run_msg(self, steps, cols=18, rows=2, y=-24):
        """steps = [(칸 k, 코드)] — 칸이 연속이 아니면 엔진이 커서를 옮긴 것."""
        sim = Sim({c for _, c in steps} | set(HALF), cols=cols, rows=rows, y=y)
        for k, c in steps:
            sim.run_glyph(c, k)
        return sim

    def test_half_space_packs_like_dialogue(self):
        codes = [0x100, 0x101, 0x0F0, 0x102, 0x103]
        sim = self.run_msg(list(enumerate(codes)))
        for t, r in model_line(codes).items():
            if t < 17:
                self.assertEqual(sim.vram.get(SLOTBASE + t), r, f"타일 {t}")

    def test_other_message_columns(self):
        codes = [0x100, 0x101, 0x0F0, 0x102]
        sim = self.run_msg(list(enumerate(codes)), cols=13)
        for t, r in model_line(codes).items():
            self.assertEqual(sim.vram.get(SLOTBASE + t), r, f"타일 {t}")

    def test_every_listed_window_composes(self):
        codes = [0x100, 0x0F0, 0x101]
        shapes = [(c, r, b) for c, r, b in tile_hook.MSG_WINDOWS] + [(5, 1, 0), (7, 1, 0), (10, 2, 0), (13, 2, 0), (18, 2, 0), (14, 1, 0)]
        for cols, rows, bias in shapes:
            sim = self.run_msg(list(enumerate(codes)), cols=cols, rows=rows)
            for tt, r in model_line(([0x0F0] if bias else []) + codes).items():
                self.assertEqual(sim.vram.get(SLOTBASE + tt), r, f"{cols}x{rows} 타일 {tt}")

    def test_result_window_is_left_aligned(self):
        """10×1 승리·패배 창의 문장은 왼쪽 정렬 — 줄 앞 밀기 0."""
        codes = [0x100, 0x101, 0x0F0, 0x102, 0x103, 0x0F1]
        sim = self.run_msg(list(enumerate(codes)), cols=10, rows=1)
        for tt, r in model_line(codes).items():
            self.assertEqual(sim.vram.get(SLOTBASE + tt), r, f"타일 {tt}")

    def test_non_battle_area_stays_plain(self):
        """전투 화면 밖(y150·y12) 의 1·2행 창은 원판 그대로 — 용도를 모르는 창은 안 바꾼다."""
        for y in (30, -108, 0):
            sim = self.run_msg([(3, 0x100)], cols=9, rows=1, y=y)
            self.assertEqual(sim.loadimages, [], f"y={y} 는 원판 그대로")

    def test_cursor_jump_restarts_position(self):
        """이름 세 글자 + 빈 칸 셋 뒤 커서가 3 칸으로 돌아오면(폭 표) 다음 글자는 36px 에서 시작한다."""
        steps = [(0, 0x100), (1, 0x101), (2, 0x102), (3, 0x0F0), (4, 0x0F0), (5, 0x0F0), (3, 0x103), (4, 0x0F0), (5, 0x104)]
        sim = self.run_msg(steps)
        want = model_line([0x100, 0x101, 0x102, 0x103, 0x0F0, 0x104])
        for t, r in want.items():
            self.assertEqual(sim.vram.get(SLOTBASE + t), r, f"타일 {t}")

    def test_other_window_shapes_stay_plain(self):
        for cols, rows in ((18, 4), (19, 2), (4, 2), (3, 2), (4, 1), (6, 4), (7, 4), (10, 4), (12, 5)):
            sim = self.run_msg([(3, 0x100)], cols=cols, rows=rows)
            self.assertEqual(sim.loadimages, [], f"{cols}x{rows} 는 원판 그대로")


JOSA = {
    "markers": [
        (0x7000, 0x201, 0x202, 0),  # 은/는
        (0x7001, 0x203, 0x204, 0),
        (0x7002, 0x205, 0x206, 0),
        (0x7003, 0x207, 0x208, 0),
        (0x7004, 0x209, BLANK, 3),  # (으) — 받침 없거나 ㄹ 이면 안 그림
    ],
    "blist": [0x300, 0x301 | 0x8000],  # 받침 있는 끝 글자 · ㄹ 받침
}


def resolve(codes):
    """모델 쪽 조사 해석 → [(글리프 코드, 전진폭)]. 직전 글자 = 마지막으로 **실제 그려진** 글자."""
    out, last = [], 0
    marks = {m[0]: m for m in JOSA["markers"]}
    bl = {c & 0x7FFF: (2 if c & 0x8000 else 1) for c in JOSA["blist"]}
    for c in codes:
        if c in marks:
            _, w, wo, fl = marks[c]
            k = bl.get(last, 0)
            if fl & 2 and k == 2:
                k = 0
            if k:
                g, adv = w, 12
            else:
                g, adv = wo, (0 if fl & 1 else 12)
        else:
            g, adv = c, 6 if c in HALF else 12
        out.append((g, adv))
        if adv:
            last = g
    return out


class TestTileHookJosa(unittest.TestCase):
    def run_codes(self, codes):
        glyphs = {c for c in codes if c < 0x7000} | {m[1] for m in JOSA["markers"]} | {m[2] for m in JOSA["markers"]} | set(HALF)
        sim = Sim(glyphs, josa=JOSA)
        for k, c in enumerate(codes):
            sim.run_glyph(c, k)
        line = tilecomp.Line()
        want = {}
        for g, adv in resolve(codes):
            for t, r in line.put(tilecomp.unpack(glyph_bytes(g)) if adv else [0] * 12, adv):
                want[t] = r
        for t, r in want.items():
            self.assertEqual(sim.vram.get(SLOTBASE + t), r, f"타일 {t} {[hex(c) for c in codes]}")

    def test_batchim_picks_eun(self):
        self.run_codes([0x300, 0x7000, 0x100])

    def test_no_batchim_picks_neun(self):
        self.run_codes([0x100, 0x7000, 0x101])

    def test_rieul_is_batchim_for_ordinary_marker(self):
        self.run_codes([0x301, 0x7001, 0x101])

    def test_eu_ro_draws_after_batchim(self):
        self.run_codes([0x300, 0x7004, 0x102, 0x103])

    def test_eu_ro_skipped_after_open_syllable_and_rieul(self):
        self.run_codes([0x100, 0x7004, 0x102, 0x103])  # 받침 없음 — 으 를 안 그리고 전진 0
        self.run_codes([0x301, 0x7004, 0x102, 0x103])  # ㄹ

    def test_skipped_marker_keeps_last_glyph(self):
        self.run_codes([0x300, 0x7004, 0x7000, 0x104])  # (으) 가 앞에서 그려졌으니 은/는 은 「으」 기준

    def test_after_halves_and_misaligned(self):
        self.run_codes([0x0F0, 0x300, 0x7002, 0x0F1, 0x101, 0x7004, 0x102, 0x103])


if __name__ == "__main__":
    unittest.main()
