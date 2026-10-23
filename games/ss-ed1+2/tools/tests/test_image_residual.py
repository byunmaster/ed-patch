"""이미지 잔존 게이트(`check_image_residual`)의 계수기 — 반각 가나 이름이 **센다**, 노이즈는 안 센다.

실측 근거: 반각 몬스터 이름 5칸이 포인터 기반 게이트를 조용히 통과했다(2026-10-18). 이 테스트가 그 꼴을 지킨다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_image_residual as R


class Count(unittest.TestCase):
    def test_half_width_name_counts(self):
        name = "ﾄﾞﾗｽﾄｺﾞｰｽﾄ".encode("cp932") + "Ａ".encode("cp932")
        data = b"\x00\x00" + name + b"\x00\x00"
        self.assertEqual(R.count_runs(data), (0, 1))

    def test_half_width_inside_code_is_noise(self):
        data = b"\x2f\x86" + bytes.fromhex("bbb2dadd") + b"\x6e\xf3"  # 앞뒤가 명령 바이트
        self.assertEqual(R.count_runs(data), (0, 0))

    def test_full_width_sentence_counts(self):
        t = "新しい町長は見たこともない".encode("cp932")
        self.assertEqual(R.count_runs(b"\x00" + t + b"\x00"), (1, 0))

    def test_short_sentence_counts(self):
        """🔴 짧은 문장(11자 안팎)도 센다 — 런 최소 길이가 길어 「…が現れた。」 꼴이 샌 사고(md-ed1)."""
        t = "ガンスが現れた。".encode("cp932")  # 8자
        self.assertEqual(R.count_runs(b"\x00" + t + b"\x00"), (1, 0))
        t = "が現れた。".encode("cp932")  # 5자 — 문턱 경계
        self.assertEqual(R.count_runs(b"\x00" + t + b"\x00"), (1, 0))

    def test_japanese_before_known_span_counts(self):
        """🔴 알려진(번역된) 구간 앞에 일본어가 붙어도 센다 — 겹침이 아니라 **바이트**로 세므로 구멍이 없다(sfc-ed2 발견)."""
        known = bytes.fromhex("88dc8a488ce08a4988b88983")  # 우리 한글 슬롯 코드
        t = "メタルスチームが".encode("cp932")
        self.assertEqual(R.count_runs(b"\x00" + t + known + b"\x00"), (1, 0))
        self.assertEqual(R.count_runs(b"\x00" + known + b"\x00"), (0, 0))

    def test_kanji_only_noise_not_counted(self):
        t = "慰壱宴雅咽蔭凱茜".encode("cp932")  # 가나 없는 한자 런 = 그림 노이즈
        self.assertEqual(R.count_runs(t), (0, 0))

    def test_hangul_slot_codes_not_counted(self):
        # 우리 한글 슬롯 코드(88dc 8a48 …)는 한자 영역이지만 가나가 아니다
        self.assertEqual(R.count_runs(bytes.fromhex("88dc8a488ce08a4988b88983") * 2), (0, 0))


if __name__ == "__main__":
    unittest.main()
