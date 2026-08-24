"""한글 인코딩 회귀 — **원본 없이 돈다**(합성 배정표).

🔴 여기가 잡는 사고: **제어코드를 직접 인코딩하는 것.** `"\\n".encode("shift_jis")` 는
   `0x0A` 를 내는데 게임 개행은 `0x0D` 다. **길이가 같아 모든 검사를 통과하고 화면에서만
   조판이 깨진다** — 2026-08-24 에 실제로 물려서 회귀로 못 박는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hangul_map as H
import mapfile as M


class TestSyllables(unittest.TestCase):
    def test_완성형_2350자(self):
        syl = H.ksc_syllables()
        self.assertEqual(len(syl), 2350)
        self.assertEqual(syl[0], "가")
        self.assertEqual(sorted(syl), syl)  # 코드 순서 = 가나다순
        self.assertNotIn("힣", syl)  # 완성형 밖(조합형 전용)

    def test_배정은_빈_슬롯을_앞에서부터(self):
        table = H.assign(free=range(1000, 1000 + 2350))
        self.assertEqual(table["가"], 1000)
        self.assertEqual(len(set(table.values())), 2350)  # 겹치는 슬롯이 없다

    def test_슬롯이_모자라면_운다(self):
        self.assertRaises(SystemExit, H.assign, free=range(10))


class TestEncode(unittest.TestCase):
    def setUp(self):
        self.t = H.assign(free=range(1410, 1410 + 2350))

    def test_한글은_슬롯_SJIS_로(self):
        from shared.text import sjis

        self.assertEqual(H.encode_kr("가", self.t), sjis.sjis_of_index(1410))

    def test_개행은_0x0D_페이지는_0x0F(self):
        """🔴 SJIS 로 직접 인코딩하면 `0x0A`·`0x0C` 가 나간다 — 길이가 같아 안 걸린다."""
        b = H.encode_kr("가\nナ\f다", self.t)
        self.assertIn(0x0D, b)
        self.assertIn(0x0F, b)
        self.assertNotIn(0x0A, b)
        self.assertNotIn(0x0C, b)

    def test_제어_규약이_mapfile_과_같다(self):
        """규약이 두 곳에 있으면 갈린다 — `encode_kr` 은 `mapfile` 을 쓴다."""
        self.assertEqual(H.encode_kr("ナ\nナ\fナ", self.t), M.encode_text("ナ\nナ\fナ"))

    def test_일본어와_공백은_그대로(self):
        self.assertEqual(H.encode_kr("ナ　 ", self.t), "ナ　 ".encode("shift_jis"))

    def test_바이트_길이가_예측대로다(self):
        """길이 보존 재삽입의 뿌리 — 한글도 전각과 같은 2B 다."""
        self.assertEqual(len(H.encode_kr("가나다", self.t)), 6)
        self.assertEqual(len(H.encode_kr("가\n나", self.t)), 5)

    def test_SJIS_밖_글자는_운다(self):
        """⚠ `·`(U+00B7)처럼 게임 글자와 비슷하게 생긴 것에 잘 걸린다."""
        with self.assertRaises(KeyError) as cm:
            H.encode_kr("·", self.t)
        self.assertIn("U+00B7", str(cm.exception))

    def test_배정에_없는_음절은_운다(self):
        small = {"가": 1410}
        with self.assertRaises(KeyError):
            H.encode_kr("나", small)


if __name__ == "__main__":
    unittest.main()
