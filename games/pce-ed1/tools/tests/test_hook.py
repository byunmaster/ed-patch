"""후킹 루틴 검산 — **HuC6280 미니 인터프리터**로 조립 결과를 돌린다.

파이썬 로직만 맞고 인코딩이 틀리면 통과하던 구멍을 막는다(PS1 의 `patch_josa_hook --selftest` 와 같은 이유).
여기서 도는 건 우리가 낸 바이트 그 자체다 — 표 오프셋·분기 거리·조사 선택까지 실물로 확인한다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import hook


class CPU:
    """루틴이 쓰는 명령만 구현한 최소 인터프리터. 모르는 옵코드를 만나면 그 자리에서 죽는다.

    MPR3($6000~$7FFF) 은 **글리프 뱅크 창**이라 값에 따라 다른 8KB 를 보여 준다 — 그걸 흉내 내야
    「뱅크를 바꿔 읽는다」까지 검산된다(안 하면 첫 8KB 안 글자만 맞고 넘어간다).
    """

    def __init__(self, mem: bytearray, pc: int, glyph_bank: bytes = b"", bank0: int = 0x85):
        self.m = mem
        self.glyph = glyph_bank
        self.bank0 = bank0
        self.pc = pc
        self.a = self.x = self.y = 0
        self.c = self.z = 0
        self.stack = []
        self.mpr = [0] * 8
        self.done = False
        self.bios_called = False

    ZP = 0x2000  # HuC6280 의 제로페이지는 MPR1 창($2000~) 에 있다 — 시뮬도 그렇게 읽는다

    def zp(self, z):
        return self.ZP + (z & 0xFF)

    def rd(self, a):
        a &= 0xFFFF
        if 0x6000 <= a < 0x8000 and self.glyph:
            off = (self.mpr[3] - self.bank0) * 0x2000 + (a - 0x6000)
            return self.glyph[off] if 0 <= off < len(self.glyph) else 0
        return self.m[a]

    def wr(self, a, v):
        self.m[a & 0xFFFF] = v & 0xFF

    def setz(self, v):
        self.z = 1 if (v & 0xFF) == 0 else 0
        return v & 0xFF

    def step(self):
        op = self.rd(self.pc)
        p = self.pc
        self.pc += 1

        def imm():
            v = self.rd(self.pc)
            self.pc += 1
            return v

        def abs_():
            v = self.rd(self.pc) | self.rd(self.pc + 1) << 8
            self.pc += 2
            return v

        def rel():
            d = self.rd(self.pc)
            self.pc += 1
            return self.pc + (d - 256 if d > 127 else d)

        if op == 0xA5:
            self.a = self.setz(self.rd(self.zp(imm())))
        elif op == 0xA9:
            self.a = self.setz(imm())
        elif op == 0xAD:
            self.a = self.setz(self.rd(abs_()))
        elif op == 0xBD:
            self.a = self.setz(self.rd(abs_() + self.x))
        elif op == 0xB9:
            self.a = self.setz(self.rd(abs_() + self.y))
        elif op == 0xB1:
            z = self.zp(imm())
            self.a = self.setz(self.rd((self.rd(z) | self.rd(z + 1) << 8) + self.y))
        elif op == 0x85:
            self.wr(self.zp(imm()), self.a)
        elif op == 0x8D:
            self.wr(abs_(), self.a)
        elif op == 0x91:
            z = self.zp(imm())
            self.wr((self.rd(z) | self.rd(z + 1) << 8) + self.y, self.a)
        elif op == 0x64:
            self.wr(self.zp(imm()), 0)
        elif op == 0xC9:
            v = imm()
            self.c = 1 if self.a >= v else 0
            self.z = 1 if self.a == v else 0
        elif op == 0xC0:
            v = imm()
            self.c = 1 if self.y >= v else 0
            self.z = 1 if self.y == v else 0
        elif op == 0x90:
            t = rel()
            self.pc = t if not self.c else self.pc
        elif op == 0xB0:
            t = rel()
            self.pc = t if self.c else self.pc
        elif op == 0xD0:
            t = rel()
            self.pc = t if not self.z else self.pc
        elif op == 0xF0:
            t = rel()
            self.pc = t if self.z else self.pc
        elif op == 0x80:
            self.pc = rel()
        elif op == 0x4C:
            t = abs_()
            if (
                t == 0xE060
            ):  # ⚠ BIOS 로 나가는 것만 종료다 — 내부 JMP 는 pc 이동(처음에 이걸 틀렸다)
                self.bios_called = True
                self.done = True
            else:
                self.pc = t
        elif op == 0x60:
            self.done = True
        elif op == 0x48:
            self.stack.append(self.a)
        elif op == 0x68:
            self.a = self.setz(self.stack.pop())
        elif op in (0x08, 0xDA, 0x5A):  # PHP PHX PHY
            self.stack.append({0x08: self.c, 0xDA: self.x, 0x5A: self.y}[op])
        elif op in (0x28, 0xFA, 0x7A):  # PLP PLX PLY
            v = self.stack.pop()
            if op == 0x28:
                self.c = v
            elif op == 0xFA:
                self.x = v
            else:
                self.y = v
        elif op == 0x78:
            pass  # SEI
        elif op == 0x18:
            self.c = 0
        elif op == 0x38:
            self.c = 1
        elif op == 0x62:
            self.a = self.setz(0)
        elif op == 0xC2:
            self.y = 0
        elif op == 0xA0:
            self.y = imm()
        elif op == 0x9C:
            self.wr(abs_(), 0)
        elif op == 0xAA:
            self.x = self.a
        elif op == 0xA8:
            self.y = self.a
        elif op == 0x98:
            self.a = self.setz(self.y)
        elif op == 0x8A:
            self.a = self.setz(self.x)
        elif op == 0xC8:
            self.y = (self.y + 1) & 0xFF
        elif op == 0xE8:
            self.x = (self.x + 1) & 0xFF
        elif op == 0xCA:
            self.x = (self.x - 1) & 0xFF
        elif op == 0x1A:
            self.a = self.setz(self.a + 1)
        elif op == 0x3A:
            self.a = self.setz(self.a - 1)
        elif op == 0x0A:
            self.c = self.a >> 7
            self.a = self.setz(self.a << 1)
        elif op == 0x4A:
            self.c = self.a & 1
            self.a = self.setz(self.a >> 1)
        elif op == 0x06:
            z = self.zp(imm())
            v = self.rd(z)
            self.c = v >> 7
            self.wr(z, self.setz(v << 1))
        elif op == 0x46:
            z = self.zp(imm())
            v = self.rd(z)
            self.c = v & 1
            self.wr(z, self.setz(v >> 1))
        elif op == 0x26:
            z = self.zp(imm())
            v = self.rd(z) << 1 | self.c
            self.c = v >> 8
            self.wr(z, self.setz(v))
        elif op == 0x66:
            z = self.zp(imm())
            v = self.rd(z)
            nc = v & 1
            self.wr(z, self.setz(v >> 1 | self.c << 7))
            self.c = nc
        elif op == 0x69:
            v = imm() + self.c
            self.c = 1 if self.a + v > 255 else 0
            self.a = self.setz(self.a + v)
        elif op == 0x65:
            v = self.rd(self.zp(imm())) + self.c
            self.c = 1 if self.a + v > 255 else 0
            self.a = self.setz(self.a + v)
        elif op == 0x7D:
            v = self.rd(abs_() + self.x) + self.c
            self.c = 1 if self.a + v > 255 else 0
            self.a = self.setz(self.a + v)
        elif op == 0xE9:
            v = imm()
            r = self.a - v - (1 - self.c)
            self.c = 1 if r >= 0 else 0
            self.a = self.setz(r)
        elif op == 0x29:
            self.a = self.setz(self.a & imm())
        elif op == 0x09:
            self.a = self.setz(self.a | imm())
        elif op == 0x43:
            self.a = self.mpr[imm().bit_length() - 1]
        elif op == 0x53:
            self.mpr[imm().bit_length() - 1] = self.a
        else:
            raise AssertionError(f"모르는 옵코드 {op:02X} @{p:04X}")

    def run(self, limit=20000):
        n = 0
        while not self.done and n < limit:
            self.step()
            n += 1
        assert self.done, "루틴이 안 끝났다"
        return n


class Hook(unittest.TestCase):
    def setup_mem(self, chars):
        table, bank = font.build_table(chars)
        mem = bytearray(0x10000)
        payload = bytearray(hook.hook_routine())
        payload += b"\0" * (hook.JOSA_OFF_ADDR - hook.HOOK_ADDR - len(payload))
        payload += font.josa_offsets(table)
        payload += b"\0" * (hook.BATCHIM_ADDR - hook.HOOK_ADDR - len(payload))
        has, rieul = font.batchim_tables(font.build_table.order)
        payload += has
        payload += b"\0" * (hook.RIEUL_ADDR - hook.HOOK_ADDR - len(payload))
        payload += rieul
        mem[hook.HOOK_ADDR : hook.HOOK_ADDR + len(payload)] = payload
        return table, bank, mem

    def draw(self, mem, code: bytes, out=0x4000, bank=b""):
        mem[0x20F9], mem[0x20F8] = code[0], code[1]
        mem[0x20FA], mem[0x20FB] = out & 0xFF, out >> 8
        mem[out : out + 32] = b"\0" * 32
        cpu = CPU(mem, hook.HOOK_ADDR, bank, hook.GLYPH_BANK0)
        cpu.mpr[3] = 0x11  # 아무 값 — 루틴이 복원하는지 본다
        cpu.run()
        self.assertEqual(cpu.mpr[3], 0x11, "MPR3 를 안 되돌렸다")
        return bytes(mem[out : out + 32]), cpu

    def test_보통_글자(self):
        table, bank, mem = self.setup_mem("가한")
        got, cpu = self.draw(mem, table["한"], bank=bank)
        self.assertFalse(cpu.bios_called)
        self.assertEqual(got[:24], font.glyph("한"))
        self.assertEqual(got[24:], b"\0" * 8)

    def test_bios_폴백(self):
        _t, _b, mem = self.setup_mem("가")
        _got, cpu = self.draw(mem, b"\x82\xa0", bank=_b)  # SJIS 'あ'
        self.assertTrue(cpu.bios_called)

    def test_조사_받침_유무(self):
        for word, expect in (("검", "은"), ("칼", "은"), ("나", "는")):
            table2, bank2, mem2 = self.setup_mem("검칼나")
            self.draw(mem2, table2[word], bank=bank2)  # 앞말을 먼저 그린다
            got, _c = self.draw(mem2, font.josa_code("은/는"), bank=bank2)
            self.assertEqual(got[:24], font.glyph(expect), f"{word} 뒤 조사")

    def test_조사_으로_로(self):
        for word, expect in (("검", "으"), ("칼", "로"), ("나", "로")):
            table, bank, mem = self.setup_mem("검칼나으로")
            self.draw(mem, table[word], bank=bank)
            got, _c = self.draw(mem, font.josa_code("으로/로"), bank=bank)
            self.assertEqual(got[:24], font.glyph(expect), f"{word} 뒤 으로/로")

    def test_한글이_아니면_받침_있음(self):
        _table, bank, mem = self.setup_mem("가은는")
        self.draw(mem, b"\x82\xa0", bank=bank)  # BIOS 로 간 글자 — LAST 는 안 바뀐다
        got, _c = self.draw(mem, font.josa_code("은/는"), bank=bank)
        self.assertEqual(got[:24], font.glyph("은"))


if __name__ == "__main__":
    unittest.main()
