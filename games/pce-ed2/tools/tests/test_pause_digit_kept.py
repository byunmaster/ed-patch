"""멈춤 `11 nn nn` 바로 뒤 ASCII 숫자 한 글자(원판 `11 31 32 30` 의 `30`)는 원판이 찍는 보이지 않는 한 글자다 — 멈춤 표에 붙어 보존돼야 한다(11-07 실험)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ctrllines
import dialog


class PauseDigitKept(unittest.TestCase):
    def test_frame_marks_keep_digit(self):
        # 「…。」 + 멈춤 `11 31 32` + 숫자 `30` — 원판 3자리 꼴
        line = b"\x10\x30" + b"\x82\xa0\x82\xa2\x81\x42" + b"\x11\x31\x32\x30" + b"\x00"[:0]
        fr = dialog.parse_frame(line)
        self.assertIsNotNone(fr)
        blobs = [m[1] for m in fr.marks]
        self.assertIn(b"\x11\x31\x32\x30", blobs)

    def test_ctrl_marks_keep_digit(self):
        raw = b"\x82\xa0\x82\xa2\x11\x31\x32\x30\x82\xa4"
        marks, _n = ctrllines._jp_marks(raw, False)
        self.assertIn(b"\x11\x31\x32\x30", [m[1] for m in marks])

    def test_two_digit_pause_unchanged(self):
        raw = b"\x82\xa0\x11\x36\x30\x82\xa4"
        marks, _n = ctrllines._jp_marks(raw, False)
        self.assertEqual([m[1] for m in marks], [b"\x11\x36\x30"])


if __name__ == "__main__":
    unittest.main()
