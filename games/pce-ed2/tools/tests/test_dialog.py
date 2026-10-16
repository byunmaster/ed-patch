import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dialog


class ParseFrame(unittest.TestCase):
    def test_simple_speaker(self):
        f = dialog.parse_frame(b"\x16\x8e\x98\x14\x0d\xa1\xa2\x13")
        self.assertEqual((f.head, f.speaker, f.post, f.tail), (b"", b"\x8e\x98", b"\x0d", b"\x13"))

    def test_staging_controls_kept_outside_text(self):
        f = dialog.parse_frame(b"\x10\x30\x16\x8e\x98\x14\x0d\x10\x33\xa1\xa2\x11\x33\x30\xa3\x11\x33\x30")
        self.assertEqual(f.head, b"\x10\x30")
        self.assertEqual(f.post, b"\x0d\x10\x33")
        self.assertEqual(f.tail, b"\x11\x33\x30")  # 본문 한복판의 `11` 은 버린다 — 꼬리의 것만 남는다

    def test_style_toggle_inside_text_is_rejected(self):
        self.assertIsNone(dialog.parse_frame(b"\xa1\x06\xa2\x04\xa3"))

    def test_two_speakers_rejected(self):
        self.assertIsNone(dialog.parse_frame(b"\x16\x8e\x98\x14\xa1\x16\x8e\x98\x14\xa2"))


if __name__ == "__main__":
    unittest.main()


def test_ellipsis_spacing_rule_2_11():
    import typeset

    assert typeset.spaced("그대도…잊었다") == "그대도… 잊었다"
    assert typeset.spaced("………프레이아님!!") == "……… 프레이아님!!"
    assert typeset.spaced("말이지…") == "말이지…"
    assert typeset.spaced("그래…?!") == "그래…?!"
    assert typeset.spaced("그래…」") == "그래…」"


def test_ellipsis_syllable_split_exception():
    import typeset

    assert typeset.spaced("세…리…오…스… 이런") == "세…리…오…스… 이런"
    assert typeset.spaced("세…리…오…스…님") == "세…리…오…스…님"
    assert typeset.spaced("사고였…네…") == "사고였…네…"
    assert typeset.spaced("미안하네… 자네들을… 오해") == "미안하네… 자네들을… 오해"


def test_ellipsis_onomatopoeia_and_brackets():
    import typeset

    assert typeset.spaced("흑…흑…흑…") == "흑…흑…흑…"
    assert typeset.spaced("으흑…으흑… 그래") == "으흑…으흑… 그래"
    assert typeset.spaced("그래…(웃음)") == "그래…(웃음)"
    assert typeset.spaced("그래…「응」") == "그래…「응」"
    assert typeset.spaced('그래…"') == '그래…"'
    assert typeset.spaced("그대도…잊었다") == "그대도… 잊었다"
