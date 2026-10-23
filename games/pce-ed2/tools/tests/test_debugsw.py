"""디버그 메뉴 숨김 제스처(`debugsw`) — 가짜 본 프로그램(원본 없이)에 심어 자리·바이트가 맞는지 본다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import debugsw
import dis6280
import layout


def fake_prog() -> layout.Prog:
    orig = bytearray(b"\xff" * (layout.NBANKS * layout.BANK))
    for (b, o), data in ((debugsw.KEY, debugsw.KEY_ORIG), (debugsw.MENU_GATE, debugsw.MENU_GATE_ORIG), (debugsw.BATTLE_GATE, debugsw.BATTLE_GATE_ORIG), (debugsw.MENU_TEXT, debugsw.menu_text(debugsw.ROWS_OLD))):
        s = (b - layout.BANK0) * layout.BANK + o
        orig[s : s + len(data)] = data
    s = (debugsw.MENU_WIDTH[0] - layout.BANK0) * layout.BANK + debugsw.MENU_WIDTH[1]
    orig[s] = 0x8C
    for k in layout.ZERO_PADDING:
        b, o, n = k
        s = (b - layout.BANK0) * layout.BANK + o
        orig[s : s + n] = bytes(n)
    return layout.Prog(orig=bytes(orig))


class DebugSw(unittest.TestCase):
    def test_제스처_본체는_18B이고_I_II_둘_다일_때만_메뉴_입구로_간다(self):
        code = debugsw.stub()
        self.assertEqual(len(code), debugsw.STUB_LEN)
        lines = dis6280.disasm(code, debugsw.STUB_ADDR, 0, 8)
        text = "\n".join(lines)
        self.assertIn("TST #$01,$2228", text)  # I
        self.assertIn("TST #$02,$2228", text)  # II
        self.assertIn(f"JMP ${debugsw.OPEN:04X}", text)
        self.assertIn(f"JMP ${debugsw.KEEP_WAIT:04X}", text)
        # 어느 한 버튼이 안 눌렸으면 둘 다 「안 열림」 갈래로 간다 — BEQ 가 둘 다 마지막 JMP 로
        self.assertEqual(text.count(f"BEQ ${debugsw.STUB_ADDR + 15:04X}"), 2)

    def test_전투_설정_본체는_RUN을_쥐면_디버그_창으로_아니면_원래_창으로(self):
        code = debugsw.battle_stub()
        text = "\n".join(dis6280.disasm(code, debugsw.BATTLE_STUB_ADDR, 0, 5))
        self.assertIn("LDA $2228", text)
        self.assertIn("AND #$08", text)  # RUN
        self.assertIn(f"JMP ${debugsw.BATTLE_WINDOW:04X}", text)
        self.assertIn(f"JMP ${debugsw.BATTLE_NORMAL:04X}", text)

    def test_심은_자리와_길이(self):
        p = fake_prog()
        debugsw.reserve(p)
        debugsw.install(p)
        w = {k: d for k, (d, _lab) in p.writes.items()}
        self.assertEqual(w[(debugsw.STUB_BANK, debugsw.STUB_OFF)], debugsw.stub())
        self.assertEqual(w[debugsw.KEY][:3], bytes([0x4C, debugsw.STUB_ADDR & 0xFF, debugsw.STUB_ADDR >> 8]))
        self.assertEqual(w[debugsw.MENU_GATE], b"\xea\xea\xea")
        self.assertEqual(w[debugsw.BATTLE_GATE], bytes([0x4C, debugsw.BATTLE_STUB_ADDR & 0xFF, debugsw.BATTLE_STUB_ADDR >> 8]))
        self.assertEqual(w[debugsw.BATTLE_STUB[:2]], debugsw.battle_stub())
        self.assertEqual(w[debugsw.MENU_WIDTH], b"\x8e")

    def test_메뉴_글은_글자_수가_그대로이고_다섯_항목에_느낌표(self):
        self.assertEqual(len(debugsw.menu_text(debugsw.ROWS_OLD)), len(debugsw.menu_text(debugsw.ROWS_NEW)))
        new = debugsw.menu_text(debugsw.ROWS_NEW)
        for lab in (b"WARP!", b"LVL!", b"GOLD!", b"ITEM!", b"MAGIC!"):
            self.assertIn(lab, new)
        for lab in (b"PATH!", b"ENTRY!", b"MASK!", b"ENCNT!", b"SPOT!", b"VISUAL!"):  # 저장을 안 바꾸는 토글엔 안 붙인다
            self.assertNotIn(lab, new)

    def test_자리_원본이_다르면_멈춘다(self):
        p = fake_prog()
        s = (debugsw.KEY[0] - layout.BANK0) * layout.BANK + debugsw.KEY[1]
        bad = bytearray(p.orig)
        bad[s] = 0
        p2 = layout.Prog(orig=bytes(bad))
        debugsw.reserve(p2)
        with self.assertRaises(AssertionError):
            debugsw.install(p2)


if __name__ == "__main__":
    unittest.main()
