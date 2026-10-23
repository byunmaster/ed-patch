"""이미지 잔존 게이트(`check_image_residue.py`) — 합성 멤버로 센다. 원본 없이 돈다."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_image_residue as R


def blob(*runs):
    out = b""
    for r in runs:
        out += struct.pack(f"<{len(r)}H", *r) + struct.pack("<H", 0xFFFF)
    return out


KANA = list(range(0x40, 0x40 + R.MIN_LEN + 3))  # 카나 대역 — 텍스트 런으로 판정된다


class ResidueTest(unittest.TestCase):
    def test_unchanged_long_run_is_counted(self):
        o = blob(KANA)
        self.assertEqual(R.residue(o, o), 1)

    def test_translated_run_is_not_counted(self):
        o = blob(KANA)
        b = blob([c + 0x1000 for c in KANA])
        self.assertEqual(R.residue(o, b), 0)

    def test_run_shorter_than_window_is_not_counted(self):
        short = KANA[: R.MIN_LEN - 1]
        self.assertEqual(R.residue(blob(short), blob(short)), 0)

    def test_short_sentence_is_counted(self):
        """12코드 미만의 짧은 문장이 남아도 센다(md-ed1 발견: 최소 길이가 길면 샌다)."""
        s = list(range(0x40, 0x40 + R.MIN_LEN + 2))  # 7코드
        self.assertEqual(R.residue(blob(s + [0x41]), blob(s)), 1)

    def test_partly_translated_run_is_counted(self):
        """앞에 한글(번역)이 붙어 런이 원본과 달라져도, 원문 조각이 남았으면 센다(sfc-ed2 구멍: 겹침만 보면 통과)."""
        o = blob(KANA)
        b = blob([0x500, 0x501, 0x502] + KANA[3:])
        self.assertEqual(R.residue(o, b), 1)

    def test_control_or_zero_data_is_not_counted(self):
        z = [0] * 10
        self.assertEqual(R.residue(blob(KANA, z), blob(z)), 0)

    def test_judge_ratchet(self):
        up, down = R.judge({"a": 2, "b": 1}, {"a": 1, "b": 1, "c": 3})
        self.assertEqual(len(up), 1)
        self.assertEqual(down, ["c"])


if __name__ == "__main__":
    unittest.main()
