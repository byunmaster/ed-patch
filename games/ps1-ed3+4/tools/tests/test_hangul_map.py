"""글리프 자리 정본의 계약 — 원본 없이 도는 회귀.

🔴 이 파일이 지키는 건 하나다: **자리가 밀리지 않는다.** 소재를 하나 더 열면 「빈 자리」가
   통째로 밀리는데, 그러면 이미 넣은 문안이 **전부 다른 글자로 읽힌다**(새턴 ED3 의 교훈).
   그래서 배정은 파생물이 아니라 커밋되는 정본이고, 여기서 그 모양을 박는다.
   원본과 부딪히나는 `hangul_map.py --check` 가 게이트에서 본다.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hangul_map

DISCS = ("ed3", "ed4")


class TestHangulMap(unittest.TestCase):
    def test_syllable_set_is_2350(self):
        syl = hangul_map.ksc_syllables()
        self.assertEqual(len(syl), 2350)
        self.assertEqual(syl[0], "가")
        self.assertEqual(len(set(syl)), 2350)
        self.assertEqual(syl, sorted(syl), "완성형 코드 순서가 곧 가나다순이다")

    def test_canon_exists_and_covers_everything(self):
        for disc in DISCS:
            t = hangul_map.load(disc)
            self.assertEqual(len(t), 2350 + len(hangul_map.EXTRA), disc)
            for ch in hangul_map.EXTRA:
                self.assertIn(ch, t, f"{disc}: 코드표에 없는 글자는 자리를 받아야 한다")
            for ch in ("가", "힘", "쓰", "왔"):
                self.assertIn(ch, t, disc)

    def test_no_two_chars_share_a_code(self):
        """🔴 한 자리에 두 글자면 화면에서 하나가 다른 글자로 보인다."""
        for disc in DISCS:
            codes = list(hangul_map.load(disc).values())
            self.assertEqual(len(codes), len(set(codes)), disc)

    def test_discs_have_their_own_map(self):
        """🔴 ED3·ED4 는 쓰는 한자가 달라서 한 벌로 묶으면 한쪽이 남의 글자를 덮는다."""
        self.assertNotEqual(hangul_map.load("ed3"), hangul_map.load("ed4"))

    def test_codes_avoid_the_kana_block(self):
        """카나·기호 대역은 시스템이 우리 덤프 밖에서 쓸 수 있다 — 안 건드린다."""
        import textenc

        for disc in DISCS:
            first = max(textenc.kana_map(disc)) + 1
            self.assertTrue(all(c >= first for c in hangul_map.load(disc).values()), disc)

    def test_canon_file_shape(self):
        for disc in DISCS:
            with open(hangul_map.map_path(disc), encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(doc["disc"], disc)
            self.assertEqual(len(doc["chars"]), len(doc["codes"]))
