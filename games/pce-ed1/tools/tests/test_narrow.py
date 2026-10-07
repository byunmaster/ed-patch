"""반 칸(4px) 전진 — 렌더러 입구 새 머리(`hook._narrow_asm`)와 글리프 뱅크의 `entry` 를 **조립 바이트 그대로** 돌려 검산한다.

엔진(뱅크 0x6C) 루틴은 가짜(트랩)다 — 호출 순서·인자·스택 균형·토글·나머지를 본다. 화면 결과는 에뮬 캡처가 맡는다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook

RET_IN = 0x7049  # `$7047` 의 JSR 이 쌓은 복귀(= `$704A` 직전 주소)
RET_CALLER = 0x1233  # 렌더러를 부른 쪽의 복귀(JSR 의 마지막 바이트)
END = {RET_IN + 1, RET_CALLER + 1}


class MiniCPU:
    """우리 코드가 쓰는 명령만 구현. 모르는 옵코드는 그 자리에서 죽는다. 엔진 주소는 트랩이 대신한다."""

    ZP = 0x2000

    def __init__(self, blobs: dict[int, bytes]):
        self.m = bytearray(0x10000)
        for at, code in blobs.items():
            self.m[at : at + len(code)] = code
        self.a = self.x = self.y = 0
        self.c = self.z = self.n = 0
        self.stack: list[int] = []
        self.traps: dict[int, callable] = {}
        self.calls: list[tuple] = []
        self.mpr = {2: 0x68}  # MPR2 에 걸린 뱅크 — 켜고 끈 흔적을 본다
        self.mpr_log: list[int] = []
        self.pc = 0

    def rd(self, a):
        return self.m[a & 0xFFFF]

    def wr(self, a, v):
        self.m[a & 0xFFFF] = v & 0xFF

    def setnz(self, v):
        v &= 0xFF
        self.z = int(v == 0)
        self.n = v >> 7
        return v

    def push16(self, v):
        self.stack += [v >> 8, v & 0xFF]

    def pop16(self):
        lo = self.stack.pop()
        return lo | self.stack.pop() << 8

    def fetch(self, n):
        v = int.from_bytes(self.m[self.pc : self.pc + n], "little")
        self.pc += n
        return v

    def ret(self):
        self.pc = (self.pop16() + 1) & 0xFFFF

    def run(self, pc, limit=4000):
        self.pc = pc
        for _ in range(limit):
            if self.pc in self.traps:  # 엔진 루틴 — 흉내 내고 RTS
                self.calls.append((self.pc, self.a, self.x, self.y))
                self.traps[self.pc](self)
                self.ret()
                if self.pc in END:
                    return
                continue
            op = self.rd(self.pc)
            self.pc += 1
            if op == 0xEE:
                a = self.fetch(2)
                self.wr(a, self.setnz(self.rd(a) + 1))
            elif op == 0xCE:
                a = self.fetch(2)
                self.wr(a, self.setnz(self.rd(a) - 1))
            elif op == 0xA5:
                self.a = self.setnz(self.rd(self.ZP + self.fetch(1)))
            elif op == 0xAD:
                self.a = self.setnz(self.rd(self.fetch(2)))
            elif op == 0xA9:
                self.a = self.setnz(self.fetch(1))
            elif op == 0x29:
                self.a = self.setnz(self.a & self.fetch(1))
            elif op == 0x69:  # ADC (캐리 사용)
                r = self.a + self.fetch(1) + self.c
                self.c = int(r > 0xFF)
                self.a = self.setnz(r)
            elif op == 0x18:
                self.c = 0
            elif op == 0x62:
                self.a = 0
            elif op == 0xC9:
                v = self.fetch(1)
                self.c = int(self.a >= v)
                self.setnz(self.a - v)
            elif op == 0xE9:  # SBC
                v = self.fetch(1)
                r = self.a - v - (1 - self.c)
                self.c = int(r >= 0)
                self.a = self.setnz(r)
            elif op == 0x85:
                self.wr(self.ZP + self.fetch(1), self.a)
            elif op == 0x8D:
                self.wr(self.fetch(2), self.a)
            elif op == 0x9C:
                self.wr(self.fetch(2), 0)
            elif op == 0x9E:
                self.wr(self.fetch(2) + self.x, 0)
            elif op == 0xA2:
                self.x = self.setnz(self.fetch(1))
            elif op == 0x82:
                self.x = 0
            elif op == 0xCA:
                self.x = self.setnz(self.x - 1)
            elif op in (0xD0, 0xF0, 0x10, 0x90, 0x80):
                d = self.fetch(1)
                t = self.pc + (d - 256 if d > 127 else d)
                take = {
                    0xD0: not self.z,
                    0xF0: self.z,
                    0x10: not self.n,
                    0x90: not self.c,
                    0x80: True,
                }[op]
                if take:
                    self.pc = t
            elif op == 0x20:
                t = self.fetch(2)
                self.push16(self.pc - 1)
                self.pc = t
            elif op == 0x4C:
                self.pc = self.fetch(2)
            elif op == 0x68:
                self.a = self.setnz(self.stack.pop())
            elif op == 0x48:
                self.stack.append(self.a)
            elif op == 0x08:
                self.stack.append(0xA5)  # P — 값은 안 본다(PLP 가 버린다)
            elif op == 0x28:
                self.stack.pop()
            elif op == 0x78:
                pass  # SEI
            elif op == 0x03:
                self.fetch(1)  # ST0 #imm — VDC 레지스터 선택(값은 안 본다)
            elif op == 0x4A:
                self.a = self.setnz(self.a >> 1)
            elif op == 0xA0:
                self.y = self.setnz(self.fetch(1))
            elif op == 0x88:
                self.y = self.setnz(self.y - 1)
            elif op == 0xB9:
                self.a = self.setnz(self.rd(self.fetch(2) + self.y))
            elif op == 0x19:
                self.a = self.setnz(self.a | self.rd(self.fetch(2) + self.y))
            elif op == 0x99:
                self.wr(self.fetch(2) + self.y, self.a)
            elif op == 0x38:
                self.c = 1
            elif op == 0xE0:  # CPX #
                v = self.fetch(1)
                self.c = int(self.x >= v)
                self.setnz(self.x - v)
            elif op == 0xB0:
                d = self.fetch(1)
                t = self.pc + (d - 256 if d > 127 else d)
                if self.c:
                    self.pc = t
            elif op == 0xBD:
                self.a = self.setnz(self.rd(self.fetch(2) + self.x))
            elif op == 0x9D:
                self.wr(self.fetch(2) + self.x, self.a)
            elif op == 0x43:  # TMA #mask
                bit = self.fetch(1)
                self.a = self.mpr[bit.bit_length() - 1]
            elif op == 0x53:  # TAM #mask
                bit = self.fetch(1)
                self.mpr[bit.bit_length() - 1] = self.a
                self.mpr_log.append(self.a)
            elif op == 0x60:
                self.ret()
                if self.pc in END:
                    return
            else:
                raise AssertionError(f"모르는 옵코드 {op:02X} @{self.pc - 1:04X}")
        raise AssertionError("안 끝난다")


def engine(cpu, toggle_after_draw=None):
    """엔진 트랩 — 그리기는 토글을 정해진 값으로 만든다."""
    seen = {}

    def draw(c):
        seen["lead_during_draw"] = c.rd(0x2000 + 0xF9)
        c.wr(hook.ENG_TOGGLE, toggle_after_draw)

    def blank(c):
        seen["toggle_at_blank"] = c.rd(hook.ENG_TOGGLE)

    def planes(c):
        seen["buf_at_planes"] = bytes(c.m[hook.ENG_GLYPH_BUF : hook.ENG_GLYPH_BUF + 32])
        if (
            c.x
        ):  # X=$20 — 면 버퍼 둘째 반(새 글자)을 채운다: 행 k 의 왼쪽 바이트 = $F0+k, 오른쪽 = 0
            for base in (hook.ENG_PLANE_A, hook.ENG_PLANE_B, hook.ENG_PLANE_C):
                for k in range(12):
                    c.m[base + c.x + 2 * k], c.m[base + c.x + 2 * k + 1] = 0xF0 + k, 0

    def fetch(
        c,
    ):  # 후킹 루틴 — `$FA/$FB` 가 가리키는 버퍼에 글리프 24B(왼쪽 바이트 = $A0+행, 오른쪽 = $0F) + 0
        at = c.rd(0x2000 + 0xFA) | c.rd(0x2000 + 0xFB) << 8
        seen["fetch_at"] = at
        for k in range(12):
            c.m[at + 2 * k], c.m[at + 2 * k + 1] = 0xA0 + k, 0x0F
        c.m[at + 24 : at + 32] = bytes(8)

    def colwrite(c):
        seen["colwrite_y"] = c.y
        seen["odd_at_write"] = [c.m[b + 1 + 2 * k] for b in (hook.ENG_PLANE_A,) for k in range(12)]

    for addr, fn in {
        hook.ENG_DRAW: draw,
        hook.ENG_ADV_COL: lambda c: None,
        hook.ENG_BLANK_COLS: blank,
        hook.ENG_REWIND: lambda c: None,
        hook.ENG_PLANES: planes,
        hook.ENG_FETCH: fetch,
        hook.ENG_COLWRITE: colwrite,
    }.items():
        cpu.traps[addr] = fn
    return seen


def machine(lead, trail, toggle_after_draw=1, flag=0, rem=0, col=5, toggle=1):
    """렌더러 입구 → 글리프 뱅크 코드까지 **조립 바이트 그대로**(껍데기 + pre/post). 엔진만 트랩."""
    cpu = MiniCPU({hook.NARROW_ADDR: hook.hook_narrow(), hook.ENTRY_ADDR: hook.hook_entry()})
    cpu.m[0x2000 + 0xF9] = lead
    cpu.m[0x2000 + 0xF8] = trail
    cpu.m[hook.ENG_COL_COUNT] = col
    cpu.m[hook.ENG_TOGGLE] = toggle
    cpu.m[hook.WRAP_ADDR] = flag
    cpu.m[hook.REM_ADDR] = rem
    cpu.m[hook.ENG_PATTERN], cpu.m[hook.ENG_PATTERN + 1] = 0x00, 0x54
    for i in range(32):  # 글리프 버퍼 — 24B 는 잉크, 뒤는 표식
        cpu.m[hook.ENG_GLYPH_BUF + i] = 0xAA
    for k in range(12):  # 면 버퍼 — 행마다 (왼쪽, 오른쪽) 바이트를 서로 다르게
        for base, v in (
            (hook.ENG_PLANE_A, 0x10),
            (hook.ENG_PLANE_B, 0x20),
            (hook.ENG_PLANE_C, 0x30),
        ):
            cpu.m[base + 2 * k], cpu.m[base + 2 * k + 1] = v + k, 0xE0 + k
    seen = engine(cpu, toggle_after_draw)
    cpu.stack = [
        RET_CALLER >> 8,
        RET_CALLER & 0xFF,
        RET_IN >> 8,
        RET_IN & 0xFF,
    ]  # 바닥 = 호출자, 위 = `$7047` 의 JSR
    return cpu, seen


def run(cpu):
    cpu.run(hook.NARROW_ENTRY)
    return [c[0] for c in cpu.calls]


def plane_pairs(cpu):
    return [
        (cpu.m[base + 2 * k], cpu.m[base + 2 * k + 1])
        for base in (hook.ENG_PLANE_A, hook.ENG_PLANE_B, hook.ENG_PLANE_C)
        for k in range(12)
    ]


def code_of(ch):
    return font.code_of(font._order_canon().index(ch))


class Layout(unittest.TestCase):
    def test_sizes(self):
        self.assertLessEqual(len(hook.hook_narrow()), hook.NARROW_ROOM)
        self.assertLessEqual(hook.NARROW_ADDR + hook.NARROW_ROOM, hook.HOOK_ADDR + hook.PAYLOAD_LEN)
        self.assertLessEqual(hook.HOOK_ADDR + hook.PAYLOAD_LEN - 1, 0x2648)  # 측정한 구간 끝
        self.assertLessEqual(len(hook.hook_entry()), hook.ENTRY_ROOM)

    def test_special_leads_do_not_collide_with_glyphs(self):
        self.assertEqual(font.VARIANT_LEAD0, 0xF4)
        self.assertEqual(font.HALF_SPACE[0], 0xF8)
        top = font.LEAD0 + (font.MAX_GLYPHS - 1) // font.PER_LEAD
        self.assertLess(top, font.VARIANT_LEAD0)

    def test_narrow_codes_match_the_glyph_canon(self):
        for ch in ".,!?":
            c = code_of(ch)
            self.assertEqual(c[0], font.LEAD0, ch)
            self.assertTrue(c[1] < hook.NARROW_LOW or c[1] == hook.NARROW_Q, ch)


class Stub(unittest.TestCase):
    def test_plain_glyph_untouched(self):
        for code in (
            (0xF0, 0x40),
            (0xF3, 0x30),
            (0xF0, 0x28),
            (0xF0, 0x2F),
            (0xF9, 0x24),
            (0x81, 0x40),
        ):
            cpu, _seen = machine(*code)
            calls = run(cpu)
            self.assertEqual(calls, [], code)  # 엔진을 안 부른다
            self.assertEqual(cpu.m[hook.ENG_COL_COUNT], 6)  # `INC` 는 한다
            self.assertEqual(
                (cpu.m[0x2000 + 0xF9], cpu.m[0x2000 + 0xF8]), code
            )  # 코드를 안 건드린다
            self.assertEqual(
                cpu.stack, [RET_CALLER >> 8, RET_CALLER & 0xFF], code
            )  # `$704A` 로 이어진다
            self.assertEqual(cpu.pc, RET_IN + 1)
            self.assertEqual(cpu.mpr[2], 0x68, "MPR2 를 되돌린다")

    def test_variant_draws_base_glyph_then_advances(self):
        for v, base in ((0xF4, 0xF0), (0xF5, 0xF1), (0xF7, 0xF3)):
            cpu, seen = machine(v, 0x55, toggle_after_draw=1)
            calls = run(cpu)
            self.assertEqual(seen["lead_during_draw"], base)  # 평범한 글자로 그렸다
            self.assertEqual(calls, [hook.ENG_DRAW, hook.ENG_ADV_COL])  # 열 가운데 → 싼 경로
            self.assertEqual(
                cpu.m[hook.ENG_COL_COUNT], 6
            )  # 글자는 1칸 — 나머지가 12 에 안 닿으면 그대로
            self.assertEqual(cpu.m[hook.REM_ADDR], 4)  # 반 칸 = 나머지 4
            self.assertEqual(cpu.m[hook.ENG_TOGGLE], 0)
            self.assertEqual(cpu.stack, [], "복귀가 원래 호출자여야 한다")
            self.assertEqual(cpu.pc, RET_CALLER + 1)

    def test_variant_after_boundary_makes_a_blank_column(self):
        cpu, seen = machine(0xF5, 0xE9, toggle_after_draw=0)
        calls = run(cpu)
        self.assertEqual(
            calls,
            [hook.ENG_DRAW, hook.ENG_PLANES, hook.ENG_BLANK_COLS, hook.ENG_REWIND, hook.ENG_REWIND],
        )
        self.assertEqual(seen["buf_at_planes"][:24], bytes(24))  # 글리프 버퍼가 0 으로 밀렸다
        self.assertEqual(seen["buf_at_planes"][24:], b"\xaa" * 8)  # 뒤는 안 건드린다
        self.assertEqual(seen["toggle_at_blank"], 1)  # 토글 1 상태로 부른다
        self.assertEqual([c[1] for c in cpu.calls[3:]], [0x20, 0x20])
        self.assertEqual(cpu.m[hook.ENG_TOGGLE], 1)

    def test_half_space_draws_nothing(self):
        cpu, _seen = machine(0xF8, 0x24, toggle=1)
        calls = run(cpu)
        self.assertEqual(calls, [hook.ENG_ADV_COL])  # 안 그린다 — 열 가운데에서 4px = 열 경계
        self.assertEqual(cpu.m[hook.ENG_COL_COUNT], 5)  # 칸은 나머지가 센다
        self.assertEqual(cpu.m[hook.REM_ADDR], 4)
        self.assertEqual(cpu.m[hook.ENG_TOGGLE], 0)
        self.assertEqual(cpu.stack, [])
        self.assertEqual(cpu.pc, RET_CALLER + 1)

    def test_half_space_at_boundary_makes_a_blank_column(self):
        cpu, seen = machine(0xF8, 0x24, toggle=0)
        calls = run(cpu)
        self.assertEqual(
            calls, [hook.ENG_PLANES, hook.ENG_BLANK_COLS, hook.ENG_REWIND, hook.ENG_REWIND]
        )
        self.assertEqual(cpu.m[hook.ENG_TOGGLE], 1)

    def test_half_space_eaten_at_wrapped_line_start(self):
        cpu, _seen = machine(0xF8, 0x24, flag=1)
        calls = run(cpu)
        self.assertEqual(calls, [])  # 아무것도 안 한다 — 줄 머리 공백은 안 먹는다
        self.assertEqual(cpu.m[hook.ENG_COL_COUNT], 5)
        self.assertEqual(cpu.m[hook.REM_ADDR], 0)
        self.assertEqual(cpu.stack, [])
        self.assertEqual(cpu.pc, RET_CALLER + 1)

    def test_three_halves_make_one_column(self):
        cpu, _ = machine(0xF8, 0x24, toggle=1)
        for _ in range(3):
            cpu.stack = [RET_CALLER >> 8, RET_CALLER & 0xFF, RET_IN >> 8, RET_IN & 0xFF]
            cpu.m[hook.ENG_TOGGLE] = 1
            cpu.run(hook.NARROW_ENTRY)
        self.assertEqual((cpu.m[hook.REM_ADDR], cpu.m[hook.ENG_COL_COUNT]), (0, 6))

    def test_rstz_zeroes_both(self):
        cpu = MiniCPU({hook.NARROW_ADDR: hook.hook_narrow()})
        cpu.m[hook.ENG_COL_COUNT] = 9
        cpu.m[hook.REM_ADDR] = 8
        cpu.stack = [RET_CALLER >> 8, RET_CALLER & 0xFF]
        cpu.run(hook.RSTZ_ADDR)
        self.assertEqual((cpu.m[hook.ENG_COL_COUNT], cpu.m[hook.REM_ADDR]), (0, 0))


class Punct(unittest.TestCase):
    CODES = [(ch, code_of(ch)) for ch in font.NARROW_PUNCT]

    def test_punct_from_a_column_boundary_fills_the_blank_column_with_ink(self):
        # 열 경계(토글 0)에서 시작 — 안 그리고(`$704A` 없음) 글리프를 받아 오른쪽 바이트 := 왼쪽 바이트, 면 버퍼 → 빈 열 쓰기(토글 1)
        for ch, (lead, trail) in self.CODES:
            cpu, seen = machine(lead, trail, toggle=0)
            calls = run(cpu)
            self.assertEqual(
                calls,
                [
                    hook.ENG_FETCH,
                    hook.ENG_PLANES,
                    hook.ENG_BLANK_COLS,
                    hook.ENG_REWIND,
                    hook.ENG_REWIND,
                ],
                ch,
            )
            self.assertEqual(seen["fetch_at"], hook.ENG_GLYPH_BUF, ch)
            buf = seen["buf_at_planes"]
            self.assertEqual(
                [buf[2 * k + 1] for k in range(12)], [0xA0 + k for k in range(12)], ch
            )  # 오른쪽 := 왼쪽
            self.assertEqual(cpu.m[hook.ENG_COL_COUNT], 5, ch)  # 글자 칸을 안 센다
            self.assertEqual(cpu.m[hook.REM_ADDR], 4, ch)
            self.assertEqual(cpu.m[hook.ENG_TOGGLE], 1, ch)  # 열 가운데
            self.assertEqual(cpu.stack, [], ch)
            self.assertEqual(cpu.pc, RET_CALLER + 1, ch)

    def test_punct_from_mid_column_ors_ink_into_the_half_column(self):
        # 열 가운데(토글 1)에서 시작 — 새 글자 왼쪽 바이트를 4px 오른쪽으로 앞 글자 오른쪽 바이트(반쪽 열)에 겹쳐 쓰고 열 경계(토글 0)
        for ch, (lead, trail) in self.CODES:
            cpu, seen = machine(lead, trail, toggle=1, rem=4)
            calls = run(cpu)
            self.assertEqual(calls, [hook.ENG_FETCH, hook.ENG_PLANES, hook.ENG_COLWRITE], ch)
            self.assertEqual(seen["fetch_at"], hook.ENG_GLYPH_BUF + 0x20, ch)
            self.assertEqual(cpu.calls[1][2], 0x20, ch)  # X = $20
            self.assertEqual(seen["colwrite_y"], 1, ch)  # 오른쪽 바이트로 열 하나
            for base in (hook.ENG_PLANE_A, hook.ENG_PLANE_B, hook.ENG_PLANE_C):
                for k in range(12):
                    want = (0xE0 + k) | (((0xF0 + k) >> 4) & 0xFF)
                    self.assertEqual(cpu.m[base + 2 * k + 1], want, (ch, base, k))
            self.assertEqual(cpu.m[hook.ENG_TOGGLE], 0, ch)
            self.assertEqual(cpu.m[hook.REM_ADDR], 8, ch)
            self.assertEqual(cpu.m[hook.ENG_COL_COUNT], 5, ch)

    def test_three_puncts_carry_a_column(self):
        lead, trail = code_of(".")
        cpu, _ = machine(lead, trail, toggle=1)
        for _ in range(3):
            cpu.stack = [RET_CALLER >> 8, RET_CALLER & 0xFF, RET_IN >> 8, RET_IN & 0xFF]
            cpu.m[hook.ENG_TOGGLE] = 1
            cpu.run(hook.NARROW_ENTRY)
        self.assertEqual((cpu.m[hook.REM_ADDR], cpu.m[hook.ENG_COL_COUNT]), (0, 6))

    def test_punct_never_calls_the_normal_draw(self):
        for ch, (lead, trail) in self.CODES:
            for toggle in (0, 1):
                cpu, _ = machine(lead, trail, toggle=toggle)
                self.assertNotIn(hook.ENG_DRAW, run(cpu), (ch, toggle))


class Encode(unittest.TestCase):
    def table(self):
        canon = font._order_canon()
        return {c: font.code_of(i) for i, c in enumerate(canon)}

    def test_item_names_fold_the_space_into_a_variant(self):
        table = self.table()
        for text, n in (
            ("성스러운 지팡이", 14),
            ("다이아의 지팡이", 14),
            ("고대의 검의 책", 12),
            ("길모아의 무지개", 14),
        ):
            b = font.encode(text, table, half_space=True)
            self.assertEqual(len(b), n, text)
            self.assertEqual(
                len([i for i in range(0, len(b), 2) if b[i] >= font.VARIANT_LEAD0]), text.count(" ")
            )
            plain = font.encode(text.replace(" ", ""), table)
            undone = bytes(
                v - (font.VARIANT_LEAD0 - font.LEAD0)
                if i % 2 == 0 and v >= font.VARIANT_LEAD0
                else v
                for i, v in enumerate(b)
            )
            self.assertEqual(undone, plain, text)
        # 글리프 뒤가 아닌 공백은 전각 그대로(제어 바이트 뒤 · 앞 공백)
        self.assertEqual(font.encode(" 가", table, True)[:2], b"\x81\x40")
        self.assertTrue(
            font.encode("가\n 나", table, True).startswith(table["가"] + b"\x01\x81\x40")
        )

    def test_message_spaces_are_half(self):
        table = self.table()
        b = font.encode("가 나", table, msg=True)
        self.assertEqual(b, table["가"] + font.HALF_SPACE + table["나"])
        self.assertEqual(font.encode("가 나", table), table["가"] + b"\x81\x40" + table["나"])


if __name__ == "__main__":
    unittest.main()
