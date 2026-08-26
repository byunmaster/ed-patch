"""SJIS ↔ JIS 좌표 회귀 — **원본 없이 돈다**(순수 계산).

🔴 여기가 틀리면 화면에만 엉뚱한 글자가 나오고 **빌드도 테스트도 통과한다.**
그래서 왕복을 못 박는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.text.sjis import decode, jis_index, kanji_start, ku_ten, sjis_of_index


class TestIndex(unittest.TestCase):
    def test_알려진_자리(self):
        self.assertEqual(jis_index("亜"), (16 - 1) * 94)  # 한자 1급 첫 글자
        self.assertEqual(jis_index("あ"), (4 - 1) * 94 + 1)
        self.assertEqual(jis_index("ア"), (5 - 1) * 94 + 1)

    def test_JIS_밖은_None(self):
        self.assertIsNone(jis_index("가"))  # 한글
        self.assertIsNone(jis_index("😀"))

    def test_ku_ten_왕복(self):
        for i in (0, 1, 93, 94, 1410, 7807):
            ku, ten = ku_ten(i)
            self.assertEqual((ku - 1) * 94 + (ten - 1), i)

    def test_한자_구역_시작(self):
        self.assertEqual(kanji_start(), jis_index("亜"))


class TestSjis(unittest.TestCase):
    def test_왕복이_원래_바이트와_같다(self):
        """🔴 색인 → SJIS 가 어긋나면 화면만 깨지고 아무도 못 잡는다."""
        for ch in "あアい亜一水城村王人力口日月木火土金":
            i = jis_index(ch)
            self.assertEqual(sjis_of_index(i), ch.encode("shift_jis"), ch)

    def test_홀수구_짝수구_경계(self):
        """구가 홀/짝일 때 둘째 바이트 공식이 갈린다 — 경계를 못 박는다."""
        for ku in (1, 2, 15, 16, 47, 48, 62, 63, 84):
            for ten in (1, 63, 64, 94):
                i = (ku - 1) * 94 + (ten - 1)
                b = sjis_of_index(i)
                try:
                    ch = b.decode("shift_jis")
                except UnicodeDecodeError:
                    continue  # 미정의 자리는 건너뛴다
                self.assertEqual(jis_index(ch), i, f"구{ku} 점{ten} {b.hex()}")

    def test_전_구역_왕복(self):
        """디코드되는 모든 슬롯이 제자리로 돌아온다."""
        bad = []
        for i in range(84 * 94):
            try:
                ch = sjis_of_index(i).decode("shift_jis")
            except UnicodeDecodeError:
                continue
            if jis_index(ch) != i:
                bad.append(i)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()


class Decode(unittest.TestCase):
    """🔴 **인코더의 짝**. 디코더가 없어서 디버깅 때마다 인라인으로 다시 짰다(2026-08-26)."""

    def setUp(self):
        self.TABLE = {"가": kanji_start(), "나": kanji_start() + 1}

    def test_round_trip_through_slots(self):
        """문자 → 슬롯 SJIS → 문자. 왕복이 안 맞으면 화면에만 엉뚱한 글자가 나온다."""
        for ch, idx in self.TABLE.items():
            b = sjis_of_index(idx)
            self.assertEqual(decode(b, self.TABLE), ch)

    def test_falls_back_to_cp932(self):
        """슬롯에 없는 2바이트는 원문 그대로 읽는다 — 미번역 자리를 눈으로 가른다."""
        self.assertEqual(decode("の攻撃".encode("cp932"), self.TABLE), "の攻撃")

    def test_keeps_control_bytes_visible(self):
        """⚠ `%c` 색코드가 1바이트로 들어앉는다 — 지우면 색이 갈리는 이유를 못 본다."""
        self.assertEqual(decode(b"\x01A\x02", self.TABLE), "<01>A<02>")

    def test_stops_at_nul_by_default(self):
        b = sjis_of_index(self.TABLE["가"]) + b"\x00" + b"XY"
        self.assertEqual(decode(b, self.TABLE), "가")
        self.assertEqual(decode(b, self.TABLE, stop_at_nul=False), "가<00>XY")

    def test_works_without_a_table(self):
        """표가 없어도 cp932 로는 읽힌다 — 원본만 볼 때 쓴다."""
        self.assertEqual(decode("の".encode("cp932")), "の")
