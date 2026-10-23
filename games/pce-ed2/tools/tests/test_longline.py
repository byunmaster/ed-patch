import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import longline


class TestLongline(unittest.TestCase):
    def test_자리에_들어가고_이음매가_어긋나지_않는다(self):
        b = longline.code()
        self.assertLessEqual(len(b), 196)  # 뱅크 0x6E 의 0xFF 패딩(+0x1F3C 부터 196B)
        L = longline.labels()
        self.assertEqual(L["h13"], longline.ORG)
        for k in ("tail", "tail2", "resume"):
            self.assertTrue(longline.ORG <= L[k] < longline.ORG + len(b), k)

    def test_한도_검사_모드에서만_끊는다(self):
        # 한도 검사 모드 표시 `LDA $7F1D` 가 들어 있다 — 한도 없는 입구($7DCD)의 호출부는 건드리지 않는다
        self.assertIn(bytes([0xAD, 0x1D, 0x7F]), longline.code())

    def test_끊는_기준은_다음_쪽이_안_넘치는_자리(self):
        # 버퍼 `$30E5` 부터 256B. 쪽 하나 최대 102B → 끊는 문턱(`$3178` = 147B 사용) + 102 + 여유 < 256
        used = (longline.FLUSH_HI << 8 | longline.FLUSH_LO) - 0x30E5
        self.assertLess(used + 102 + 6, 256)


if __name__ == "__main__":
    unittest.main()
