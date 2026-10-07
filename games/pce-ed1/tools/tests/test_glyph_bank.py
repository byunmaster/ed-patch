"""글리프 뱅크 — 18B 묶음 저장(10-07)을 뱅크 꼬리의 풀기 루틴이 **모든 순번에서** 24B 로 되돌리나. 원본 없이 돈다.

🔴 옛 24B 저장에선 8192 ÷ 24 가 안 떨어져 순번 341(「십」)이 뱅크 경계에 걸려 **조용히 깨졌다**(2026-09-16,
마스터 캡처에서 발각). 18B 로 묶으며 뱅크 하나에 리드 둘(220자 × 18B × 2 = 7,920B)이 딱 들게 해서 걸치는
글자 자체를 없앴다 — 그래도 「한 자리를 확인」하지 않고 **상한까지 전부** 돌린다. 자리 계산(짝 × 3,960 +
순번 × 18)이 어긋나면 다른 글자가 조용히 깨지기 때문이다.

손인코딩 루틴(`hook.unpack_asm`)은 미니 인터프리터로 **실제로 돌려** 검산한다(루트 CLAUDE.md 「빌드 규율」).
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook

BANK = 0x2000
WIN = hook.GLYPH_WINDOW_HI << 8  # $6000
DST = 0x3000
ZP = 0x2000


class CPU:
    """`unpack_asm` 이 쓰는 명령만."""

    def __init__(self, m):
        self.m = m
        self.a = self.x = self.y = 0
        self.c = self.z = 0
        self.stack = []

    def run(self, pc, a):
        m = self.m
        self.a, self.c, self.pc = a, a, pc
        self.stack.append(None)

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

        def zp16(z):
            return m[ZP + z] | m[ZP + z + 1] << 8

        for _ in range(200000):
            op = b()
            if op == 0x48:
                self.stack.append(self.a)
            elif op == 0x68:
                self.a = nz(self.stack.pop())
            elif op == 0x60:
                ret = self.stack.pop()
                if ret is None:
                    return
                self.pc = ret
            elif op == 0x20:
                t = w()
                self.stack.append(self.pc)
                self.pc = t
            elif op == 0xA5:
                self.a = nz(m[ZP + b()])
            elif op == 0xA9:
                self.a = nz(b())
            elif op == 0x85:
                m[ZP + b()] = self.a
            elif op == 0x84:
                m[ZP + b()] = self.y
            elif op == 0x64:
                m[ZP + b()] = 0
            elif op == 0x8D:
                m[w()] = self.a
            elif op == 0x0D:
                self.a = nz(self.a | m[w()])
            elif op == 0xB2:
                self.a = nz(m[zp16(b())])
            elif op == 0x91:
                m[zp16(b()) + self.y] = self.a
            elif op == 0xA0:
                self.y = nz(b())
            elif op == 0xC2:
                self.y = 0
            elif op == 0x62:
                self.a = 0
            elif op == 0xA6:
                self.x = nz(m[ZP + b()])
            elif op == 0xE0:
                v = b()
                self.c = int(self.x >= v)
                nz(self.x - v)
            elif op == 0xAA:
                self.x = nz(self.a)
            elif op == 0xE8:
                self.x = nz(self.x + 1)
            elif op == 0xCA:
                self.x = nz(self.x - 1)
            elif op == 0xC8:
                self.y = nz(self.y + 1)
            elif op == 0xE6:
                z = ZP + b()
                m[z] = nz(m[z] + 1)
            elif op == 0x38:
                self.c = 1
            elif op == 0x18:
                self.c = 0
            elif op == 0xE9:
                r = self.a - b() - (1 - self.c)
                self.c = int(r >= 0)
                self.a = nz(r)
            elif op == 0x69:
                r = self.a + b() + self.c
                self.c = int(r > 0xFF)
                self.a = nz(r)
            elif op == 0x29:
                self.a = nz(self.a & b())
            elif op == 0x0A:
                self.c = self.a >> 7
                self.a = nz(self.a << 1)
            elif op == 0x4A:
                self.c = self.a & 1
                self.a = nz(self.a >> 1)
            elif op == 0xC0:
                v = b()
                self.c = int(self.y >= v)
                nz(self.y - v)
            elif op == 0xF0:
                br(self.z)
            elif op == 0xD0:
                br(not self.z)
            elif op == 0x90:
                br(not self.c)
            elif op == 0x80:
                br(True)
            else:
                raise AssertionError(f"모르는 옵코드 {op:02X} @ {self.pc - 1:04X}")
        raise AssertionError("안 끝난다")


def synth(i: int) -> bytes:
    """순번마다 다른 24B 글리프(행마다 12비트, lo 아래 4비트 0)."""
    r = random.Random(i)
    out = bytearray()
    for _ in range(12):
        v = r.getrandbits(12) << 4
        out += bytes([v >> 8, v & 0xF0])
    return bytes(out)


class GlyphBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        banks = bytearray(font.GLYPH_NBANKS * BANK)
        for i in range(font.MAX_GLYPHS):
            at = font.glyph_at(i)
            banks[at : at + font.PACKED_BYTES] = font.pack(synth(i))
        code = hook.unpack_code()
        for k in range(font.GLYPH_NBANKS):
            at = k * BANK + font.BANK_GLYPH_END
            assert not banks[at : (k + 1) * BANK].strip(b"\0"), "글리프가 코드 자리를 덮는다"
            banks[at : at + len(code)] = code
        cls.banks = banks

    def fetch(self, idx: int) -> bytes:
        """훅의 `fetch` 를 흉내 — 리드로 뱅크를 골라 창에 걸고 꼬리 루틴을 부른다."""
        code = font.code_of(idx)
        g = code[0] - font.LEAD0
        bank = g >> 1
        m = bytearray(0x10000)
        m[WIN : WIN + BANK] = self.banks[bank * BANK : (bank + 1) * BANK]
        m[ZP + 0xEC] = code[1]
        m[ZP + 0xFA], m[ZP + 0xFB] = DST & 0xFF, DST >> 8
        m[DST : DST + 0x20] = b"\xaa" * 0x20
        CPU(m).run(hook.UNPACK_ADDR, g & 1)  # C 로 넘긴다(run 이 a·c 둘 다 채운다)
        self.assertEqual(m[DST + 24 : DST + 0x20], b"\0" * 8, f"순번 {idx}: 꼬리 0 채움")
        return bytes(m[DST : DST + 24])

    def test_every_glyph_unpacks(self):
        """상한(font.MAX_GLYPHS — 2뱅크 880자)까지 **모든** 순번이 자기 24B 를 그대로 받아야 한다."""
        for idx in range(font.MAX_GLYPHS):
            self.assertEqual(self.fetch(idx), synth(idx), f"순번 {idx} 가 어긋난다")

    def test_no_glyph_straddles(self):
        for idx in range(font.MAX_GLYPHS):
            at = font.glyph_at(idx) % BANK
            self.assertLessEqual(at + font.PACKED_BYTES, font.BANK_GLYPH_END, idx)

    def test_pack_roundtrip_real_font(self):
        for ch in "가힣십똠?!.,A0":
            g = font.glyph(ch)
            self.assertEqual(font.unpack(font.pack(g)), g, ch)

    def test_code_fits_tails(self):
        self.assertLessEqual(len(hook.unpack_code()), hook.UNPACK_ROOM)
        self.assertLessEqual(len(hook._wordck_asm().bytes()), hook.WORDCK_ROOM)
        self.assertLessEqual(len(hook._entry_asm().bytes()), hook.ENTRY_ROOM)
        self.assertEqual(hook.UNPACK_ADDR - WIN + hook.UNPACK_ROOM, BANK)
        # 마지막 뱅크 글리프 끝 칸들이 코드 자리 — 풀기 루틴 바로 앞에서 끝난다
        self.assertEqual(
            hook.WORDCK_ADDR + hook.WORDCK_ROOM, (hook.WORDCK_MPR << 13) + font.BANK_GLYPH_END
        )
        self.assertEqual(hook.ENTRY_ROOM + hook.WORDCK_ROOM, font.CODE_BYTES)

    def test_hook_routine_fits(self):
        self.assertLessEqual(len(hook.hook_routine()), hook.JOSA_OFF_ADDR - hook.HOOK_ADDR)

    def test_josa_table_is_codes(self):
        """조사 표 = (트레일, 리드) — 보통 글자 길(`fetch`)로 낸다."""
        table, _ = font.build_table(font._order_canon())
        t = font.josa_offsets(table)
        a, _b = font.JOSA_PAIRS[0].split("/")
        self.assertEqual(bytes([t[1], t[0]]), table[a[0]])


if __name__ == "__main__":
    unittest.main()
