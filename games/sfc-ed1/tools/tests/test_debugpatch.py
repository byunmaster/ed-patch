"""디버그 진입 트램펄린의 분기 거리 — 손인코딩 기계어 검산(원본 롬 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import debugpatch as d


class Tramp(unittest.TestCase):
    def test_분기가_의도한_자리로_간다(self):
        b = d.TRAMP_BYTES
        pc = lambda i: d.TRAMP + i  # noqa: E731
        # 0 LDA 3 CMP 5 BNE 7 LDA 10 BNE 12 JMP(A) 15 LDA 18 CMP 20 BNE 22 LDA 25 CMP 27 BNE 29 JMP(B) 32 JMP(cont)
        self.assertEqual(b[5], 0xD0)
        self.assertEqual(pc(5 + 2 + b[6]), pc(15))  # 둘째 조합이 아니면 원본 비교로
        self.assertEqual(b[10], 0xD0)
        self.assertEqual(pc(10 + 2 + b[11]), pc(15))
        self.assertEqual(b[20], 0xD0)
        self.assertEqual(pc(20 + 2 + b[21]), pc(32))  # 원본 조합이 아니면 원래 흐름으로
        self.assertEqual(b[27], 0xD0)
        self.assertEqual(pc(27 + 2 + b[28]), pc(32))
        self.assertEqual(b[12], 0x4C)
        self.assertEqual(b[13] | b[14] << 8, d.MENU_A & 0xFFFF)
        self.assertEqual(b[29], 0x4C)
        self.assertEqual(b[30] | b[31] << 8, d.MENU_B & 0xFFFF)
        self.assertEqual(b[32], 0x4C)
        self.assertEqual(b[33] | b[34] << 8, d.CONT & 0xFFFF)
        self.assertEqual(len(b), 35)

    def test_원본_비교_17바이트가_조합_L_R_Y_와_같다(self):
        o = d.SITE_ORIG
        self.assertEqual((o[4], o[11]), (0x30, 0x40))
        self.assertEqual(o[-3:], bytes([0x4C, 0x4D, 0xFB]))  # → 메뉴 B


if __name__ == "__main__":
    unittest.main()
