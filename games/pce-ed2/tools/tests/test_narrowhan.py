"""좁은 글꼴 한글(디버그 마을 목록) — 부호화·도안·후킹 루틴 모양."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import dis6280
import hook
import narrowhan


class NarrowHan(unittest.TestCase):
    def test_부호화는_리드_FA_와_번호(self):
        cs = narrowhan.chars()
        c = cs[0]
        self.assertEqual(narrowhan.enc(c), bytes([narrowhan.LEAD, narrowhan.TRAIL0]))
        self.assertEqual(narrowhan.enc("a" if False else " "), b"\x60")  # 공백 4px
        self.assertEqual(narrowhan.enc("\n"), b"\x0d")
        with self.assertRaises(KeyError):
            narrowhan.enc("쀏")  # 틀에 없는 글자

    def test_도안은_12행_8열_16B_간격(self):
        t = narrowhan.table()
        self.assertEqual(len(t), narrowhan.STRIDE * len(narrowhan.chars()))
        g = narrowhan.rows(narrowhan.chars()[0])
        self.assertEqual(len(g), 12)
        self.assertEqual(t[:12], g)
        self.assertEqual(t[12 : narrowhan.STRIDE], bytes(narrowhan.STRIDE - 12))
        self.assertTrue(all(b & 1 == 0 for b in g))  # 7px 글자 — 오른쪽 한 열은 비어 있다(전진 8)

    def test_후킹_루틴은_FA_를_가르고_창에_표를_건다(self):
        a = hook._routine(hook.MAX_RUNS)
        b = a.bytes()
        text = "\n".join(dis6280.disasm(b, a.org, a.labels["ascii"] - a.org, 6))
        self.assertIn(f"CMP #${narrowhan.LEAD:02X}", text)
        n = "\n".join(dis6280.disasm(b, a.org, a.labels["narrowh"] - a.org, 55))
        self.assertIn("TMA #$10", n)
        self.assertIn("TAM #$10", n)
        self.assertIn(f"SBC #${narrowhan.TRAIL0:02X}", n)
        self.assertIn("LDA $26F3", n)  # 장면 번호로 표 위치를 고른다(디버그 마을 2 · 배틀 테스트 마을 16~19)
        self.assertGreaterEqual(len(re.findall(r"ADC \$[0-9A-F]{4},X", n)), 2)  # 뱅크 오프셋 표 · 쪽 오프셋 표(장면 색인)
        self.assertIn("RTS", n)


if __name__ == "__main__":
    unittest.main()
