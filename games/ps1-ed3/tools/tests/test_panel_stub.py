"""월드맵 패널 가운데 정렬 스텁(`tile_hook.panel_stubs`)을 해석기(`mips_cpu`)로 돌려 줄 시작 x · 글자 전진을 모델과 대조한다 — 원본 없이 돈다.

모델: 공백 6px · 0 코드 0px · 나머지 12px, 줄 폭이 72px 를 넘으면 그 줄만 글자 간격 11px(공백 6 그대로), 시작 x = 칸 왼쪽 + 36 − 폭/2."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_patch
import exetext
import tile_hook
from mips_cpu import RA_END, Cpu

SP = 0x2A  # 공백 코드(임의)
FP = 0x801F0000
STR = 0x801E0000
WIN = 0x801D0000
LEFT = 100  # 칸 왼쪽 x


def build():
    words, base, labels, init = tile_hook.panel_stubs("ed3", SP)
    prog = {base + 4 * i: w for i, w in enumerate(words)}
    prog.update({tile_hook.PANEL_INIT_ADDR + 4 * i: w for i, w in enumerate(init)})
    return prog, labels


def model(codes):
    """(시작 x 오프셋, 간격, [글자별 x])."""
    w12 = sum(6 if c == SP else 12 for c in codes if c)
    n = sum(1 for c in codes if c and c != SP)
    pitch, w = (12, w12) if w12 <= 72 else (11, w12 - n)
    x = 36 - w // 2
    xs = []
    for c in codes:
        xs.append(x)
        x += 0 if c == 0 else (6 if c == SP else pitch)
    return 36 - w // 2, pitch, xs


class TestPanelStub(unittest.TestCase):
    def setUp(self):
        self.prog, self.lab = build()

    def cpu(self, words, idx=0):
        cpu = Cpu(self.prog)
        R = engine_patch._R
        for i, w in enumerate(words):
            cpu.w16(STR + 2 * i, w)
        cpu.w32(FP + 0x60, STR)
        cpu.w32(FP + 0x34, WIN)
        cpu.w16(WIN + 2, LEFT)
        cpu.w16(FP + 0x22, idx)
        cpu.regs[R["fp"]] = FP
        cpu.regs[R["sp"]] = FP - 0x100
        cpu.regs[R["ra"]] = RA_END
        return cpu, R

    def start(self, codes, label="stub_init", idx=0):
        cpu, _ = self.cpu(list(codes) + [0x8002], idx)
        cpu.run(self.lab[label])
        return cpu.r16(FP + 0x10) - LEFT, cpu.r16(FP + 0x24)

    def draw(self, codes):
        """줄 시작 후 글자마다 `stub_adv` 를 돌린 x 열."""
        cpu, R = self.cpu(list(codes) + [0x8002])
        cpu.run(self.lab["stub_init"])
        xs = []
        for i in range(len(codes)):
            x = cpu.r16(FP + 0x10)
            xs.append(x - LEFT)
            cpu.w16(FP + 0x22, i)
            cpu.regs[R["v0"]] = x
            cpu.regs[R["ra"]] = RA_END
            cpu.run(self.lab["stub_adv"])
        return xs

    def check(self, codes):
        x0, pitch, xs = model(codes)
        got, p = self.start(codes)
        self.assertEqual((got, p), (x0, pitch), codes)
        self.assertEqual(self.draw(codes), xs, codes)

    def test_short_line_centered(self):
        self.check([0x100, 0x101, 0x102])  # 36px → 시작 18

    def test_full_row_is_not_tight(self):
        self.check([0x100 + i for i in range(6)])  # 72px 딱 맞음 — 12px 그대로
        self.assertEqual(self.start([0x100 + i for i in range(6)])[1], 12)

    def test_space_is_six(self):
        self.check([0x100, 0x101, SP, 0x102, 0x103])  # 54px

    def test_five_names_fit(self):
        # 큰 뱀의 등뼈(5글자 + 공백 둘 = 72px) · 그레이스 산지(66px) — 12px. 6글자 + 공백 둘(84px)은 11px 로도 78px 라 게이트가 막는다
        self.check([1, SP, 2, 3, SP, 4, 5])  # 5글자 + 공백 둘 = 72
        self.check([1, 2, 3, SP, 4, 5])  # 66

    def test_over_row_is_tight(self):
        codes = [1, 2, 3, SP, 4, 5, 6]  # 수정호 오솔길 — 78px → 11px 간격 72px
        x0, pitch, _ = model(codes)
        self.assertEqual((x0, pitch), (0, 11))
        self.check(codes)

    def test_zero_indent_has_no_width(self):
        self.check([0, 0, 1, 2, 3])
        self.check([0, 1, 2, 3, SP, 4, 5, 6])

    def test_second_line_recomputed(self):
        """줄바꿈 뒤(`stub_line`)는 idx = fp+0x22 + 1 부터 — 앞 줄이 넓어도 둘째 줄은 자기 폭."""
        first = [1, 2, 3, SP, 4, 5, 6]
        second = [7, 8, 9]
        words = first + [0x8000] + second + [0x8002]
        cpu, _ = self.cpu(words)
        cpu.run(self.lab["stub_init"])
        self.assertEqual(cpu.r16(FP + 0x24), 11)
        cpu.w16(FP + 0x22, len(first))  # 줄바꿈 코드 칸
        cpu.regs[engine_patch._R["ra"]] = RA_END
        cpu.run(self.lab["stub_line"])
        self.assertEqual((cpu.r16(FP + 0x10) - LEFT, cpu.r16(FP + 0x24)), (model(second)[0], 12))

    def test_init_stub_in_r1_tail(self):
        import cursor_hook

        used = 4 * len(cursor_hook.build("ed3", SP)[0])
        self.assertEqual(tile_hook.PANEL_INIT_ADDR, cursor_hook.R1 + used)
        self.assertLessEqual(used + 8, cursor_hook.R1_LEN)

    def test_data_before_stub(self):
        self.assertGreaterEqual(
            tile_hook.PANEL_CODE_OFF, tile_hook.data_size(25)
        )  # 상태·표(받침표 25개까지) 뒤

    def test_stub_fits_before_msg_stub(self):
        words, base, _lab, _init = tile_hook.panel_stubs("ed3", SP)
        self.assertLessEqual(
            base - engine_patch.PATCH["ed3"]["data"] + 4 * len(words), tile_hook.MSG_OFF
        )


class TestPanelWidthGate(unittest.TestCase):
    def pool(self, lines):
        ws = []
        for ln in lines:
            ws += list(ln) + [0x8002]
        return struct.pack(f"<{len(ws)}H", *ws)

    def test_gate(self):
        ok = self.pool([[1, 2, 3, SP, 4, 5, 6], [1] * 6, [1, SP, 2, 3, SP, 4, 5]])
        self.assertEqual(exetext.panel_width_problems(ok, 0, len(ok), SP, 72), [])
        bad = self.pool([[1] * 7])  # 붙여 쓴 7글자 = 84 → 11px 로 77 > 72
        self.assertEqual(len(exetext.panel_width_problems(bad, 0, len(bad), SP, 72)), 1)
        zero = self.pool([[0, 0, 1, 2, 3]])
        self.assertEqual(exetext.panel_width_problems(zero, 0, len(zero), SP, 72), [])


if __name__ == "__main__":
    unittest.main()
