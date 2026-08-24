"""`KANJI12.FON` 기하·색인 회귀 — **원본 없이 돈다**(순수 계산 + 합성 글리프).

🔴 여기가 지키는 것: **18B 밀착 패킹**과 **JIS 순차 색인**. 둘 중 하나만 틀려도 화면에
   엉뚱한 글자가 나오는데 **빌드도 테스트도 통과한다** — 그래서 짝을 코드로 못 박는다.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import font as F


class TestGeometry(unittest.TestCase):
    def test_기하_상수(self):
        self.assertEqual(F.STRIDE * F.GLYPHS, 140_544)  # 실측 파일 크기
        self.assertEqual(F.ROWS * F.CELL, F.STRIDE * 8)  # 144비트 = 18바이트, 남는 비트 없음

    def test_pack18_unpack_왕복(self):
        rng = np.random.default_rng(20260824)  # 고정 시드 — 빌드는 결정적이어야 한다
        for _ in range(50):
            bits = rng.integers(0, 2, (F.ROWS, F.CELL), dtype=np.uint8)
            packed = F.pack18(bits)
            self.assertEqual(len(packed), F.STRIDE)
            np.testing.assert_array_equal(F.unpack(packed, 0), bits)

    def test_경계를_안_지키는_패킹(self):
        """12비트 행이 바이트에 안 떨어진다 — 둘째 행은 첫 바이트 중간에서 시작한다."""
        bits = np.zeros((F.ROWS, F.CELL), dtype=np.uint8)
        bits[1, 0] = 1  # 둘째 행 첫 픽셀 = 전체 12번 비트 → 1번 바이트의 다섯째 자리
        self.assertEqual(F.pack18(bits)[1], 0b0000_1000)


class TestIndex(unittest.TestCase):
    def test_jis_색인(self):
        # 구/점 → (구-1)*94 + (점-1)
        self.assertEqual(F.jis_index("亜"), (16 - 1) * 94 + (1 - 1))
        self.assertEqual(F.jis_index("あ"), (4 - 1) * 94 + (2 - 1))
        self.assertEqual(F.jis_index("ア"), (5 - 1) * 94 + (2 - 1))
        self.assertIsNone(F.jis_index("가"))  # EUC-JP 밖

    def test_sjis_왕복(self):
        for ch in "あアい亜一水城村王":
            i = F.jis_index(ch)
            self.assertEqual(F.sjis_of_index(i), ch.encode("shift_jis"), ch)

    def test_한자_구역_시작(self):
        self.assertEqual(F.jis_index("亜"), (F.KANJI_KU - 1) * 94)


if __name__ == "__main__":
    unittest.main()
