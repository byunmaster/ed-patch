"""「」 반각 — 도안 D판 글리프 · 11×11 묶음의 한 행 내림 플래그 · 진행 stub(시뮬레이터)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dis6280
import font
import kagi
import sim6280
from test_hook import machine, synthetic

CODES = [bytes([0xF1, 0x30]), bytes([0xF2, 0x31]), bytes([0xF3, 0x32]), bytes([0xF4, 0x33])]


class Kagi(unittest.TestCase):
    def test_글리프가_도안과_같다(self):
        for ch, k in (("「", 0), ("」", 1), ("『", 2), ("』", 3)):
            g = font.pool_glyph(ch)
            for r, row in enumerate((font.KAGI_ART, font.KAGI_ART2)[k // 2]):
                v = int.from_bytes(g[2 * r : 2 * r + 2], "big")
                want = "".join("#" if v & (0x8000 >> c) else "." for c in range(8))
                self.assertEqual(want, row[(k % 2) * 8 : (k % 2) * 8 + 8], f"{ch} 행 {r}")

    def test_내림_플래그_묶기_풀기(self):
        for ch in "」』":
            g = font.pool_glyph(ch)
            self.assertTrue(any(g[22:24]), "행 11 에 가로줄이 있다")
            self.assertEqual(font.unpack(font.pack(g, font.flags(ch))), g)
        for ch in "「『":
            g = font.pool_glyph(ch)
            self.assertEqual(font.unpack(font.pack(g, font.flags(ch))), g)
        self.assertEqual(font.flags("「"), 0)

    def test_훅이_내림_플래그를_따른다(self):
        gl = synthetic(10)
        gl[4] = font.pool_glyph("」")
        flags = [0] * 10
        flags[4] = font.FLAG_DOWN
        sim = machine(gl, flags)
        lead, trail = divmod(4, font.PER_LEAD)
        sim.wr(0x20F9, font.LEAD0 + lead)
        sim.wr(0x20F8, font.TRAIL0 + trail)
        sim.sp = 0xFF
        import hook

        r = sim.run(0x6000 + hook.HOOK_OFF)
        while r not in (-1, hook.ORIG_CHECK):
            r = sim.run(r, base_sp=0xFF)
        self.assertEqual(bytes(sim.ram[0x109B : 0x109B + 24]), gl[4])

    def test_stub_디스어셈블(self):
        b = kagi.stub(CODES)
        lines = dis6280.disasm(b, kagi.STUB_ORG, 0, 32)
        txt = "\n".join(lines)
        for want in ("LDX #$03", "CMP $F8", "CMP $F9", "JMP $67C4", "BBS3 $84", "DEC $73", "DEC $71"):
            self.assertIn(want, txt.replace("$67c4", "$67C4"))

    def _run(self, code, bit3, wrap=False):
        bank = bytearray(b"\xff" * 8192)
        bank[kagi.STUB_OFF : kagi.STUB_OFF + kagi.LEN] = kagi.stub(CODES)
        h = 0x67C4 - 0x6000
        cur = 0x71 if bit3 else 0x73
        # 가짜 처리기: 커서 += 3(줄넘김이면 0)
        bank[h : h + 9] = bytes([0xA5, cur, 0x18, 0x69, 3, 0x85, cur, 0x60, 0xEA])
        if wrap:
            bank[h : h + 9] = bytes([0xA9, 0, 0x85, cur, 0x60, 0xEA, 0xEA, 0xEA, 0xEA])
        sim = sim6280.Sim({0x71: bank}, [0xFF, 0xF8, 0x68, 0x71, 0x75, 0x76, 0x77, 0x87], bytearray(8192))
        sim.wr(0x2000 + 0x84, 0x08 if bit3 else 0)
        sim.wr(0x2000 + cur, 10)
        return sim

    @staticmethod
    def _go(sim):
        r = sim.run(kagi.STUB_ORG)
        while r not in (None, -1):  # JMP 를 따라간다
            r = sim.run(r, base_sp=0xFF)

    def test_stub_진행(self):
        for bit3 in (0, 1):
            cur = 0x71 if bit3 else 0x73
            for code, want in ((CODES[0], 12), (CODES[3], 12), (bytes([0xF1, 0x31]), 13), (bytes([0xF5, 0x30]), 13)):
                sim = self._run(code, bit3)
                sim.wr(0x2000 + 0xF9, code[0])
                sim.wr(0x2000 + 0xF8, code[1])
                sim.sp = 0xFF
                self._go(sim)
                self.assertEqual(sim.rd(0x2000 + cur), want, f"bit3={bit3} {code.hex()}")

    def test_stub_줄넘김이면_건드리지_않는다(self):
        sim = self._run(CODES[0], 0, wrap=True)
        sim.wr(0x2000 + 0xF9, CODES[0][0])
        sim.wr(0x2000 + 0xF8, CODES[0][1])
        sim.sp = 0xFF
        self._go(sim)
        self.assertEqual(sim.rd(0x2000 + 0x73), 0)


if __name__ == "__main__":
    unittest.main()
