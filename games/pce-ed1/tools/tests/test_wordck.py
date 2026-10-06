"""로그 어절 줄바꿈(`hook.wordck`) — 손인코딩 기계어를 **미니 인터프리터로 실제로 돌려** 검산한다.

글자마다 `mark` 경로가 부르는 것처럼 「지금 글자 `$F9:$F8` · 열 `$38BB` · 다음 바이트 `($14),Y`」를
차려 놓고 부른 뒤, 개행 보류(`$CF15`)·`flag` 와 X·Y 보존을 본다(원본 없이 돈다).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook

ZP = 0x2000  # HuC6280 영페이지
COL, PEND = 0x38BB, 0xCF15
BUF, INJ = 0x4000, 0x4100
SP = (0x81, 0x40)
CH = (font.LEAD0, 0x80)  # 아무 글자
DOT = (font.LEAD0, 0x2E)  # 매다는 부호


def chars(n):
    return bytes(CH) * n


class CPU:
    """`wordck` 가 쓰는 명령만."""

    def __init__(self, m):
        self.m = m
        self.a = self.x = self.y = 0
        self.c = self.z = 0
        self.stack = []

    def run(self, pc):
        m = self.m
        self.stack.append(None)  # 돌아갈 자리 표지
        self.pc = pc

        def b():
            v = m[self.pc]
            self.pc += 1
            return v

        def w():
            return b() | b() << 8

        def nz(v):
            v &= 0xFF
            self.z = int(v == 0)
            return v

        def br(take):
            d = b()
            if take:
                self.pc += d - 256 if d > 127 else d

        for _ in range(100000):
            op = b()
            if op == 0x5A:
                self.stack.append(self.y)
            elif op == 0xDA:
                self.stack.append(self.x)
            elif op == 0xFA:
                self.x = nz(self.stack.pop())
            elif op == 0x7A:
                self.y = nz(self.stack.pop())
            elif op == 0x60:
                assert self.stack.pop() is None, "스택이 안 맞는다"
                return
            elif op == 0xAE:
                self.x = nz(m[w()])
            elif op == 0xA2:
                self.x = nz(b())
            elif op == 0xA0:
                self.y = nz(b())
            elif op == 0x9C:
                m[w()] = 0
            elif op == 0xA5:
                self.a = nz(m[ZP + b()])
            elif op == 0xA9:
                self.a = nz(b())
            elif op == 0xAD:
                self.a = nz(m[w()])
            elif op == 0x85:
                m[ZP + b()] = self.a
            elif op == 0x8D:
                m[w()] = self.a
            elif op == 0xB1:
                zp = ZP + b()
                self.a = nz(m[(m[zp] | m[zp + 1] << 8) + self.y])
            elif op in (0xC9, 0xC5):
                v = b() if op == 0xC9 else m[ZP + b()]
                self.c = int(self.a >= v)
                nz(self.a - v)
            elif op == 0x29:
                self.a = nz(self.a & b())
            elif op == 0xEE:
                at = w()
                m[at] = nz(m[at] + 1)
            elif op == 0x8A:
                self.a = nz(self.x)
            elif op == 0xAA:
                self.x = nz(self.a)
            elif op == 0xC8:
                self.y = nz(self.y + 1)
            elif op == 0x88:
                self.y = nz(self.y - 1)
            elif op == 0x18:
                self.c = 0
            elif op == 0x6D:
                r = self.a + m[w()] + self.c
                self.c = int(r > 0xFF)
                self.a = nz(r)
            elif op == 0xD0:
                br(not self.z)
            elif op == 0xF0:
                br(self.z)
            elif op == 0x90:
                br(not self.c)
            elif op == 0x80:
                br(True)
            else:
                raise AssertionError(f"모르는 옵코드 {op:02X} @ {self.pc - 1:04X}")
        raise AssertionError("안 끝난다")


class WordCk(unittest.TestCase):
    def setUp(self):
        self.m = bytearray(0x10000)
        code = hook.wordck()
        self.m[hook.WORDCK_ADDR : hook.WORDCK_ADDR + len(code)] = code
        self.labels = hook._wordck_asm().labels

    def call(self, cur, rest, col, prev_space=True, inject=None):
        """`cur` 를 그리기 직전 — `rest` 는 그 뒤 바이트. 끝나면 (보류, flag)."""
        m = self.m
        m[self.labels["prevsp"]] = int(prev_space)
        m[ZP + 0xF9], m[ZP + 0xF8] = cur
        m[COL] = col
        m[PEND] = 0
        m[ZP + hook.LINE_COLS_ZP] = 13
        m[hook.WRAP_ADDR] = 0xAA
        m[BUF : BUF + len(rest) + 1] = rest + b"\x00"
        m[ZP + 0x14], m[ZP + 0x15] = BUF & 0xFF, BUF >> 8
        m[ZP + 0x90] = 0
        if inject is not None:  # 이름 삽입 중 — 돌아갈 자리는 `$93/$94`
            m[ZP + 0x90] = 2
            m[INJ : INJ + len(inject) + 1] = inject + b"\x00"
            m[ZP + 0x93], m[ZP + 0x94] = INJ & 0xFF, INJ >> 8
        cpu = CPU(m)
        cpu.x, cpu.y = 0x48, 0
        cpu.run(hook.WORDCK_ADDR)
        self.assertEqual((cpu.x, cpu.y), (0x48, 0), "X·Y 를 지켜야 한다")
        return m[PEND], m[hook.WRAP_ADDR]

    def test_word_fits(self):
        # 열 9 + 4글자 = 13칸 — 이 줄에 들어간다
        self.assertEqual(self.call(CH, chars(3) + bytes(SP), 9)[0], 0)

    def test_word_overflows(self):
        # 열 10 + 4글자 = 14칸 — 이 글자부터 새 줄
        self.assertEqual(self.call(CH, chars(3) + bytes(SP), 10)[0], 1)

    def test_width_from_engine(self):
        # 폭은 엔진의 `$99` 를 읽는다 — 넓은 창이면 같은 자리에서도 안 넘긴다
        self.m[ZP + hook.LINE_COLS_ZP] = 20
        m = self.m
        m[self.labels["prevsp"]] = 1
        m[ZP + 0xF9], m[ZP + 0xF8] = CH
        m[COL], m[PEND] = 10, 0
        m[BUF : BUF + 8] = chars(3) + bytes(SP)
        m[ZP + 0x14], m[ZP + 0x15] = BUF & 0xFF, BUF >> 8
        m[ZP + 0x90] = 0
        CPU(m).run(hook.WORDCK_ADDR)
        self.assertEqual(m[PEND], 0)

    def test_not_word_start(self):
        self.assertEqual(self.call(CH, chars(9), 12, prev_space=False)[0], 0)

    def test_line_head(self):
        self.assertEqual(self.call(CH, chars(20), 0)[0], 0)

    def test_hanging_punct_not_counted(self):
        # 열 9 + 4글자 + 마침표 — 마침표는 줄 밖에 매달리니 13칸으로 본다
        self.assertEqual(self.call(CH, chars(3) + bytes(DOT), 9)[0], 0)

    def test_stops_at_control(self):
        # 01(개행) 뒤 글자는 다른 줄이다
        self.assertEqual(self.call(CH, chars(1) + b"\x01" + chars(9), 10)[0], 0)

    def test_inject_continues_after_06(self):
        # 이름 삽입 중: 이름 끝(06) 뒤 본문 조사까지 한 어절 — 열 10 + 3 + 1 = 14
        self.assertEqual(self.call(CH, chars(2) + b"\x06", 10, inject=chars(1))[0], 1)
        self.assertEqual(self.call(CH, chars(2) + b"\x06", 9, inject=chars(1))[0], 0)

    def test_06_outside_inject_stops(self):
        self.assertEqual(self.call(CH, chars(2) + b"\x06" + chars(5), 10)[0], 0)

    def test_space_sets_prevsp_and_flag(self):
        m = self.m
        # 공백 — 판정 없이 「직전이 공백」만 세운다. 보류가 없으면 flag = 0
        self.assertEqual(self.call(SP, chars(5), 5, prev_space=False), (0, 0))
        self.assertEqual(m[self.labels["prevsp"]], 1)

    def test_flag_when_wrap_on_space(self):
        # `$6D95` 가 이미 보류를 세운 줄 끝 공백이면 flag = 1 → `eat` 이 칸 전진을 건너뛴다
        m = self.m
        m[self.labels["prevsp"]] = 0
        m[ZP + 0xF9], m[ZP + 0xF8] = SP
        m[PEND] = 1
        m[BUF] = 0
        m[ZP + 0x14], m[ZP + 0x15] = BUF & 0xFF, BUF >> 8
        cpu = CPU(m)
        cpu.run(hook.WORDCK_ADDR)
        self.assertEqual(m[hook.WRAP_ADDR], 1)

    def test_flag_clear_on_word_wrap(self):
        # 어절로 넘긴 글자는 공백이 아니다 — flag 0(칸을 먹는다)
        self.assertEqual(self.call(CH, chars(5), 12), (1, 0))

    def test_fits_tail(self):
        self.assertLessEqual(len(hook._wordck_asm().bytes()), font.GLYPH_TAIL)
        self.assertEqual(hook.WORDCK_ADDR + font.GLYPH_TAIL, 0xA000)


if __name__ == "__main__":
    unittest.main()
