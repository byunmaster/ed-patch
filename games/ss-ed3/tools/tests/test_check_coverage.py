"""구운 이미지 잔존 검사 — 짧은 문장이 길이 하한에 안 새는가(10-18, sfc-ed2·md-ed1 의 구멍과 같은 모양)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_coverage as K


def blk(s):
    return {"body": s.encode("shift_jis")}


class UntouchedBlocks(unittest.TestCase):
    def test_short_sentence_left_in_image_is_caught(self):
        """가나 덩이가 2 자(「ティ」)뿐이라 연속 길이 3 자↑ 게이트가 놓치는 문장도 센다."""
        orig = [blk("ティ変更"), blk("はい"), blk("こんにちは世界")]
        self.assertEqual(K.kana_runs("ティ変更".encode("shift_jis")), [])  # 옛 게이트는 못 본다
        self.assertEqual(K.untouched_blocks(orig, orig), 3)

    def test_translated_block_is_not_counted(self):
        orig = [blk("ティ変更"), blk("はい")]
        new = [{"body": "변경".encode("shift_jis", "ignore") or b"\x00"}, blk("はい")]
        self.assertEqual(K.untouched_blocks(orig, new), 1)

    def test_block_without_kana_is_ignored(self):
        self.assertEqual(K.untouched_blocks([blk("ABC")], [blk("ABC")]), 0)


class OutsideUnitList(unittest.TestCase):
    def test_kana_outside_any_block_is_seen_by_byte_scan(self):
        """번역 단위(블록) 목록 밖에 있는 일본어 — 맵 이름 표 같은 자리 — 도 바이트 훑기는 본다(단위 목록과 무관한 눈)."""
        junk = b"\x00\x21\x71\x28" + "ホルクの砦".encode("shift_jis") + b"\x00\x00"
        self.assertTrue(K.kana_runs(junk))


if __name__ == "__main__":
    unittest.main()
