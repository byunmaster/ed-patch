"""한글 창을 원판 창 경계에 맞추는 함수(`dialogue.align_windows`, 번역 규칙 2-17) — 양성·음성 대조."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import dialogue


class Align(unittest.TestCase):
    def test_sentence_boundary(self):
        out = dialogue.align_windows("왕자님, 역시 평화가 좋군요. 이제야 마음 놓고 살 수 있겠습니다.", "가。{13}\n나나。")
        self.assertEqual(out, "왕자님, 역시 평화가 좋군요.\f이제야 마음 놓고 살 수 있겠습니다.")

    def test_mid_sentence_boundary_uses_comma(self):
        out = dialogue.align_windows(
            "이렇게 팔린 건 처음이라 기쁜 것도 같습니다만, 아무래도 마음 놓고 기뻐할 수가 없군요.",
            "ああああああああ、{13}\nいいいいいいいい。",
        )
        self.assertEqual(out, "이렇게 팔린 건 처음이라 기쁜 것도 같습니다만,\f아무래도 마음 놓고 기뻐할 수가 없군요.")

    def test_orphan_last_window_stays_merged(self):
        # 원판 경계대로 가르면 마지막 창에 한 어절(「안심하십시오.」)만 남는다 — 2-17 이 막는다
        txt = "왕자님, 엘아스타는 무슨 일이 있어도 지켜 내겠습니다. 안심하십시오."
        self.assertEqual(dialogue.align_windows(txt, "あ。{13}\nい。"), txt)

    def test_count_mismatch_uses_ratio_when_no_marks(self):
        out = dialogue.align_windows("하나 둘 셋. 넷 다섯 여섯.", "あ。い。{13}\nう。え。")
        self.assertEqual(out, "하나 둘 셋.\f넷 다섯 여섯.")  # 문장 수가 다르고 쪽 가름이 없는 한 덩이는 원판 비율에 가까운 문장 끝에 가른다

    def test_count_mismatch_with_marks_left_alone(self):
        txt = "하나.\f둘. 셋. 넷."
        self.assertEqual(dialogue.align_windows(txt, "あ。{13}\nい。{13}\nう。"), txt)  # 한글 문장 수와 원판 문장 수가 다르고 쪽 가름이 이미 있으면 안 건드린다

    def test_enough_windows_unchanged(self):
        txt = "가나.\f다라."
        self.assertEqual(dialogue.align_windows(txt, "あ。{13}\nい。"), txt)


if __name__ == "__main__":
    unittest.main()
