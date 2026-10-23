import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import narrow


class TestNarrow(unittest.TestCase):
    def test_스텁은_뱅크_끝_0xFF_런_안이다(self):
        self.assertLessEqual(narrow.STUB_OFF + len(narrow.STUB), 0x2000)
        self.assertEqual(len(narrow.STUB), 14)

    def test_스텁_분기가_맞다(self):
        s = narrow.STUB
        # TAX; BNE +8(LDA $F9; CMP #$60; BCS +2; LDX #4 = 8B) ; JMP ($67B9,X)
        self.assertEqual(s[0], 0xAA)
        self.assertEqual((s[1], s[2]), (0xD0, 8))
        self.assertEqual(s[3 + 8 :], bytes([0x7C, 0xB9, 0x67]))
        self.assertEqual((s[7], s[8]), (0xB0, 2))  # BCS +2 — LDX #4 를 건너뛴다
        self.assertEqual(s[9:11], bytes([0xA2, 0x04]))

    def test_원본_처리기_분기는_같은_표를_쓴다(self):
        self.assertEqual(narrow.SEAM_OLD, bytes([0xAA, 0x7C, 0xB9, 0x67]))  # TAX; JMP ($67B9,X)
        self.assertEqual(narrow.STUB[-3:], bytes([0x7C, 0xB9, 0x67]))


if __name__ == "__main__":
    unittest.main()
