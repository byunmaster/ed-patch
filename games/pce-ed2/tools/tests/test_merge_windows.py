"""원문 창 수 되돌리기(dialogue.merge_short_windows, 번역 규칙 2-10·2-17 맨 앞, 마스터 11-05)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "text"))
import dialogue


class Merge(unittest.TestCase):
    def test_short_exclamation_joined(self):
        t = "어머, 왕자님.\f용의 알을 되돌린 게 왕자님이시라고 들었어요."
        self.assertEqual(dialogue.merge_short_windows(t, True, 1), "어머, 왕자님. 용의 알을 되돌린 게 왕자님이시라고 들었어요.")

    def test_keep_when_target_is_two(self):
        t = "어머, 왕자님.\f용의 알을 되돌린 게 왕자님이시라고 들었어요."
        self.assertEqual(dialogue.merge_short_windows(t, True, 2), t)  # 원문도 두 창이면 그대로

    def test_too_long_stays_split(self):
        t = "첫째 문장은 꽤 길어서 한 창을 거의 채웁니다 정말로 그렇습니다.\f" + "둘째 문장도 길어서 한 창을 거의 채워 버립니다 그렇고말고요. " * 3
        self.assertGreater(dialogue.merge_short_windows(t, False, 1).count("\f"), 0)  # 한 창에 안 들어가면 문장 경계(쪽 가름)를 남긴다

    def test_split_to_original_windows(self):
        t = "왕자님, 엘아스타는 무슨 일이 있어도 지켜 내겠습니다. 안심하십시오."
        self.assertEqual(dialogue.split_to_windows(t, True, 2), "왕자님, 엘아스타는 무슨 일이 있어도 지켜 내겠습니다.\f안심하십시오.")  # 원문 두 창 → 두 창(2-17)
        self.assertEqual(dialogue.split_to_windows(t, True, 1), t)  # 원문도 한 창이면 그대로
        self.assertEqual(dialogue.split_to_windows(t, True, 2).count("\f"), 1)

    def test_split_needs_spots(self):
        self.assertEqual(dialogue.split_to_windows("네", True, 2), "네")  # 가를 자리 없음 — 그대로


class BlankParticleTest(unittest.TestCase):
    def test_blank_item_particle(self):
        import ctrllines

        self.assertEqual(ctrllines.blank_item_particle(bytes.fromhex("0d1d6b60f14c")), bytes.fromhex("0d1d60f14c"))  # 1D 6B(だ) 60 → 1D 60
        self.assertEqual(ctrllines.blank_item_particle(bytes.fromhex("0c1dcaf924")), bytes.fromhex("0c1d60f924"))  # 조사 훅이 오는 꼴도 가나 자리를 빈 칸(60)으로
        self.assertEqual(ctrllines.blank_item_particle(bytes.fromhex("0c1dcafff924")), bytes.fromhex("0c1d60fff924"))  # 사이에 채움(FF)이 껴도
        self.assertEqual(ctrllines.blank_item_particle(bytes.fromhex("0d1da60d")), bytes.fromhex("0d1d600d"))  # 줄 끝·글 앞은 공백(60)
        self.assertEqual(ctrllines.blank_item_particle(bytes.fromhex("1d601d6b0d")), bytes.fromhex("1d601d600d"))  # 이미 60 이면 그대로
        self.assertEqual(ctrllines.blank_item_particle(bytes.fromhex("f21d601d6b60")), bytes.fromhex("f21d601d6b60")[:0] + bytes.fromhex("f21d60") + bytes.fromhex("1d60"))  # 2바이트 글자 안의 1D 는 제어가 아니다


class LatinWidthTest(unittest.TestCase):
    def test_match_width(self):
        import systext

        self.assertEqual(systext.match_width("ＳＡＶＥ", "SAVE"), "ＳＡＶＥ")
        self.assertEqual(systext.match_width("ＬＯＣＡＬ", "LOCAL"), "LOCAL")  # 마스터 10-28 반각
        self.assertEqual(systext.match_width("システム", "시스템"), "시스템")


if __name__ == "__main__":
    unittest.main()
