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
BUF, INJ = 0xC600, 0x6973  # 전투 블록 창·삽입 버퍼 — 실측 자리
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
        self.stack += [None, None]  # 돌아갈 자리 표지(2B — PLA 두 번으로 버리는 코드가 있다)
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
                lo, hi = self.stack.pop(), self.stack.pop()
                if lo is None:
                    assert hi is None, "스택이 안 맞는다"
                    return
                self.pc = (hi << 8 | lo) + 1
            elif op == 0x4C:  # JMP abs
                self.pc = w()
            elif op == 0x20:
                t = w()
                ret = self.pc - 1
                self.stack += [ret >> 8, ret & 0xFF]
                self.pc = t
            elif op == 0x48:
                self.stack.append(self.a)
            elif op == 0x68:
                self.a = nz(self.stack.pop())
            elif op == 0xAE:
                self.x = nz(m[w()])
            elif op == 0xA2:
                self.x = nz(b())
            elif op == 0xA0:
                self.y = nz(b())
            elif op == 0x62:  # CLA(HuC6280 — 플래그 안 건드림)
                self.a = 0
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
            elif op == 0xE0:  # CPX imm
                v = b()
                self.c = int(self.x >= v)
                nz(self.x - v)
            elif op == 0x38:  # SEC (미사용이어도 무해)
                self.c = 1
            elif op == 0xA6:  # LDX zp
                self.x = nz(m[ZP + b()])
            elif op == 0x0A:  # ASL A
                r = self.a << 1
                self.c = int(r > 0xFF)
                self.a = nz(r)
            elif op == 0x4A:  # LSR A
                self.c = self.a & 1
                self.a = nz(self.a >> 1)
            elif op == 0x65:  # ADC zp
                r = self.a + m[ZP + b()] + self.c
                self.c = int(r > 0xFF)
                self.a = nz(r)
            elif op == 0xCD:  # CMP abs
                v = m[w()]
                self.c = int(self.a >= v)
                nz(self.a - v)
            elif op == 0xB0:  # BCS
                br(self.c)
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


HS = tuple(font.HALF_SPACE)  # 대사창 반각 공백 — 어절 끝 · 어절 첫 글자 판정에서 전각 공백과 같다


class WordCk(unittest.TestCase):
    def setUp(self):
        self.m = bytearray(0x10000)
        code = hook.wordck()
        self.m[hook.WCK_ADDR : hook.WCK_ADDR + len(code)] = code
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
        cpu.run(hook.WCK_ADDR)
        self.assertEqual((cpu.x, cpu.y), (0x48, 0), "X·Y 를 지켜야 한다")
        return m[PEND], m[hook.WRAP_ADDR]

    def test_line_head_space_is_eaten(self):
        # 11-21 줄 첫 칸 공백 근본 — 개행 보류가 없어도 줄 머리(칸 0)의 공백은 flag(안 먹음)
        self.assertEqual(self.call(SP, chars(2), 0, prev_space=False)[1], 1)
        self.assertEqual(self.call(font.HALF_SPACE, chars(2), 0, prev_space=False)[1], 1)

    def test_mid_line_space_and_head_punct_kept(self):
        self.assertEqual(self.call(SP, chars(2), 3, prev_space=False)[1], 0)
        self.assertEqual(self.call(font.HALF_SPACE, chars(2), 3, prev_space=False)[1], 0)
        self.assertEqual(self.call(DOT, chars(2), 0, prev_space=False)[1], 0)  # 부호는 공백 갈래 prevsp 를 타도 안 먹는다
        self.assertEqual(self.call(CH, chars(2), 0, prev_space=False)[1], 0)

    def test_head_space_not_eaten_after_hanging_punct(self):
        self.m[hook.NARROW_ADDR] = 4  # 줄 머리 매다는 부호가 4px 를 써서 칸 0 · 나머지 4
        self.assertEqual(self.call(SP, chars(2), 0, prev_space=False)[1], 0)

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
        CPU(m).run(hook.WCK_ADDR)
        self.assertEqual(m[PEND], 0)

    def test_remainder_counts_in_quarter_cells(self):
        # 🔴 11-20 정확 모델: 폭을 4px 눈금으로 센다(시작 = 열×3 + rem/4, 어절 = 보통 3 · 부호 1 · `?` 2, 들어가는 조건 ≤ 줄 폭×3 = 39).
        #   열 9 + 글자 4(= 12눈금): 나머지 0 → 27 + 12 = 39 들어감 · 나머지 4px → 28 + 12 = 40 새 줄 · 나머지 8px → 41 새 줄.
        rest = chars(3) + bytes(SP)
        self.m[hook.NARROW_ADDR] = 0
        self.assertEqual(self.call(CH, rest, 9)[0], 0)
        for rem in (4, 8):
            self.m[hook.NARROW_ADDR] = rem
            self.assertEqual(self.call(CH, rest, 9)[0], 1, rem)

    def test_punct_counts_one_quarter(self):
        # 매다는 부호(`! , .`)는 4px(1눈금) — 부호가 낀 어절을 칸 수로 세면 틀 칸을 안 덮는데도 넘어갔다(「않으시겠습니까!!』…」)
        for trail in hook.HANG_PUNCT:
            self.m[hook.NARROW_ADDR] = 4
            # 열 9(27) + rem 1 = 28, 어절: 글자 2(6) + 부호(1 · `?` 는 2) + 공백 → 35~36 ≤ 39 → 들어간다
            self.assertEqual(self.call(CH, chars(2) + bytes(trail) + bytes(SP), 9)[0], 0, trail)
        # 같은 길이 어절이 부호 없이 글자 셋이면 28 + 3 + 3×3 = 40 → 새 줄
        self.m[hook.NARROW_ADDR] = 4
        self.assertEqual(self.call(CH, chars(3) + bytes(SP), 9)[0], 1)
        # 어절이 글자 하나여도 나머지 8px 에 열 12 면 36 + 2 + 3 = 41 → 새 줄
        self.m[hook.NARROW_ADDR] = 8
        self.assertEqual(self.call(CH, bytes(SP), 12)[0], 1)

    def test_not_word_start(self):
        self.assertEqual(self.call(CH, chars(9), 12, prev_space=False)[0], 0)

    def test_line_head(self):
        self.assertEqual(self.call(CH, chars(20), 0)[0], 0)

    def test_hanging_punct_counted(self):
        # 11-08(마스터 「전투중 창 초과」): 매다는 부호도 어절 길이에 센다 — 열 9 + 4글자 + 마침표 = 마침표가 칸 13(틀 칸)에 걸리니 어절째 새 줄
        self.assertEqual(self.call(CH, chars(3) + bytes(DOT), 9)[0], 1)
        # 열 8 이면 마침표가 칸 12 — 들어간다
        self.assertEqual(self.call(CH, chars(3) + bytes(DOT), 8)[0], 0)

    def test_stops_at_control(self):
        # 01(개행) 뒤 글자는 다른 줄이다
        self.assertEqual(self.call(CH, chars(1) + b"\x01" + chars(9), 10)[0], 0)

    def test_inject_continues_after_06(self):
        # 이름 삽입 중: 이름 끝(06) 뒤 본문 조사까지 한 어절 — 열 10 + 3 + 1 = 14
        self.assertEqual(self.call(CH, chars(2) + b"\x06", 10, inject=chars(1))[0], 1)
        self.assertEqual(self.call(CH, chars(2) + b"\x06", 9, inject=chars(1))[0], 0)

    def test_pointer_in_own_window_skips(self):
        # 글이 `$4000~$5FFF`(우리가 건 창)에 있으면 못 읽는다 — 판정 없이 나간다(넘기지 않는다)
        m = self.m
        buf = 0x5000
        m[self.labels["prevsp"]] = 1
        m[ZP + 0xF9], m[ZP + 0xF8] = CH
        m[COL], m[PEND] = 12, 0
        m[ZP + hook.LINE_COLS_ZP] = 13
        m[buf : buf + 12] = chars(5) + b"\x00\x00"
        m[ZP + 0x14], m[ZP + 0x15] = buf & 0xFF, buf >> 8
        m[ZP + 0x90] = 0
        cpu = CPU(m)
        cpu.x, cpu.y = 0x48, 0
        cpu.run(hook.WCK_ADDR)
        self.assertEqual(m[PEND], 0)
        self.assertEqual((cpu.x, cpu.y), (0x48, 0))

    def test_jump_continues_the_word(self):
        # 조각 이음(`0F lo hi`): 「맞」+「지」 — 앞 조각만 재면 1글자라 줄 끝(열 12)에 들어가 「지」만 넘어갔다. 이어 재면 2글자 — 열 12+2=14 → 넘긴다.
        tail = 0xC700
        self.m[tail : tail + 4] = chars(1) + bytes(SP)
        jmp = b"\x0f" + tail.to_bytes(2, "little")
        self.assertEqual(self.call(CH, jmp, 12)[0], 1)
        self.assertEqual(self.call(CH, jmp, 11)[0], 0)  # 열 11 + 2 = 13 — 들어간다

    def test_jump_chain_and_inject(self):
        # 점프 뒤에서 이름 삽입 06 을 만나도 삽입 전 자리로 돌아가 이어 잰다(상태 X 가 점프에서 안 바뀐다)
        tail = 0xC700
        self.m[tail : tail + 4] = chars(1) + bytes(SP)
        jmp = b"\x0f" + tail.to_bytes(2, "little")
        # 이름 나머지 1 + (06 → 본문) 1 + 점프 뒤 1 = 3글자 — 열 10 + 3 = 13 → 넘긴다 / 열 9 이면 들어간다
        self.assertEqual(self.call(CH, chars(1) + b"\x06", 10, inject=chars(1) + jmp)[0], 1)
        self.assertEqual(self.call(CH, chars(1) + b"\x06", 9, inject=chars(1) + jmp)[0], 0)

    def test_06_outside_inject_stops(self):
        self.assertEqual(self.call(CH, chars(2) + b"\x06" + chars(5), 10)[0], 0)

    def test_half_space_ends_a_word(self):
        # 반각 공백(대사창)도 어절 끝 — 열 9 + 4글자 = 13칸 들어가고, 열 10 이면 넘어간다
        self.assertEqual(self.call(CH, chars(3) + bytes(HS), 9)[0], 0)
        self.assertEqual(self.call(CH, chars(3) + bytes(HS), 10)[0], 1)

    def test_half_space_sets_prevsp(self):
        m = self.m
        self.assertEqual(self.call(HS, chars(5), 5, prev_space=False), (0, 0))
        self.assertEqual(m[self.labels["prevsp"]], 1)

    def test_flag_when_wrap_on_half_space(self):
        m = self.m
        m[self.labels["prevsp"]] = 0
        m[ZP + 0xF9], m[ZP + 0xF8] = HS
        m[PEND] = 1
        m[BUF] = 0
        m[ZP + 0x14], m[ZP + 0x15] = BUF & 0xFF, BUF >> 8
        m[ZP + 0x90] = 0
        m[ZP + hook.LINE_COLS_ZP] = 13
        CPU(m).run(hook.WCK_ADDR)
        self.assertEqual(m[hook.WRAP_ADDR], 1)

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
        cpu.run(hook.WCK_ADDR)
        self.assertEqual(m[hook.WRAP_ADDR], 1)

    def test_flag_clear_on_word_wrap(self):
        # 어절로 넘긴 글자는 공백이 아니다 — flag 0(칸을 먹는다)
        self.assertEqual(self.call(CH, chars(5), 12), (1, 0))

    # 🔴 이음(종단 `0A`, 개행 없음) — 앞 문구 끝 부호 바로 뒤에 다음 문구가 붙는다(공백 없음). 부호 뒤 첫 글자도 어절 첫 글자다(11-06).
    BANG = (font.LEAD0, 0x24)
    PERIOD = (font.LEAD0, 0x27)

    def test_sentence_punct_marks_next_glyph_as_word_start(self):
        m = self.m
        for punct in (self.PERIOD, self.BANG):
            m[self.labels["prevsp"]] = 0
            # 부호 자신: 검사 없음(보류 0 · flag 0), 다음 글자를 어절 첫 글자로 표시
            self.assertEqual(self.call(punct, chars(3), 12, prev_space=False), (0, 0))
            self.assertEqual(m[self.labels["prevsp"]], 1)

    def test_name_straddling_after_sentence_end(self):
        # 「…없었다.」 뒤 이름 삽입(「세리오스」 + 06 + 「는」): 부호 → 이름 첫 글자. 열 10 + 이름 3 + 조사 1 = 14 → 새 줄 / 열 9 이면 들어간다
        m = self.m
        self.call(self.PERIOD, b"", 9, prev_space=False)
        self.assertEqual(self.call(CH, chars(2) + b"\x06", 10, prev_space=bool(m[self.labels["prevsp"]]), inject=chars(1))[0], 1)
        self.call(self.PERIOD, b"", 8, prev_space=False)
        self.assertEqual(self.call(CH, chars(2) + b"\x06", 9, prev_space=bool(m[self.labels["prevsp"]]), inject=chars(1))[0], 0)

    def test_plain_glyph_after_sentence_end_wraps_by_word(self):
        # 이름 삽입이 아닌 이음(도구 이름·일반 문구)도 같다 — 열 10 + 4글자
        m = self.m
        self.call(self.BANG, b"", 9, prev_space=False)
        self.assertEqual(self.call(CH, chars(3) + bytes(HS), 10, prev_space=bool(m[self.labels["prevsp"]]))[0], 1)

    def test_sentence_punct_at_col13_hangs(self):
        # 줄 끝 칸 13 에 오는 부호는 매달린다 — 어절 검사로 새 줄에 홀로 떨어지면 안 된다
        self.assertEqual(self.call(self.PERIOD, b"", 13, prev_space=True)[0], 0)
        self.assertEqual(self.call(self.BANG, b"", 13, prev_space=False)[0], 0)

    def test_same_trail_other_lead_is_not_punct(self):
        # 트레일 0x27 이어도 리드가 F0 이 아니면 부호가 아니다
        m = self.m
        self.assertEqual(self.call((font.LEAD0 + 1, 0x27), chars(3), 5, prev_space=False), (0, 0))
        self.assertEqual(m[self.labels["prevsp"]], 0)

    # ⚠ 알려진 한계: 개행 보류가 선 **줄 머리**에 문장 끝 부호가 오면 flag=1 이라 `eat` 이 그 부호의 칸 전진을 건너뛴다(공백과 같은 갈래라서).
    #   부호로 시작하는 줄은 우리 문안에 없다(전수 확인 — 전투·시스템 문구 줄 머리는 늘 글자·이름) — 코드 자리(+2B)가 모자라 안 막았다.

    def test_fits_bank73_tail(self):
        # 뱅크 0x73 꼬리 — musicresume 바로 뒤에서 시작해 뱅크 끝(벡터 `$FFF6` 앞)에 안 닿는다
        import musicresume

        self.assertEqual(hook.WCK_BANK_OFF, musicresume.OFF + musicresume.CODE_LEN)
        self.assertEqual(hook.WCK_BANK, musicresume.BANK)
        self.assertLessEqual(len(hook._wordck_asm().bytes()), hook.WCK_ROOM)
        self.assertLess(hook.WCK_ADDR + len(hook._wordck_asm().bytes()), 0xFFF6)
        self.assertEqual(hook.WCK_ADDR >> 13, hook.WCK_MPR)


if __name__ == "__main__":
    unittest.main()
