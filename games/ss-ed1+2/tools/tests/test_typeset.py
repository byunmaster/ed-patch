"""조판기 회귀 — **함정마다 하나**. 원본 없이 돈다(정본 표만 쓴다).

전부 2026-08-27 정적 QA 가 빌드 이미지에서 **실제로 잡아낸 것**이다.
"""

import os
import sys
import unittest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(TOOLS)), "..", "shared"))

import typeset_scn as T

NAMES = {"兵士": "병사", "ゲイル": "게일", "ソニア": "소니아", "ナイフ": "나이프"}


class Typeset(unittest.TestCase):
    def t(self, jp, kr, names=None):
        return T.typeset(jp, kr, NAMES if names is None else names)

    def test_speaker_newline_survives(self):
        """🔴 화자와 본문을 가르는 개행을 지우면 본문이 화자 줄에 붙는다(8,657블록)."""
        got, bad = self.t("%c兵士%c\n本文だ。%c", "본문이다.")
        self.assertIsNone(bad)
        self.assertEqual(got, "%c병사%c\n본문이다.%c")

    def test_whitespace_only_slot_is_kept(self):
        """공백만 든 자리도 안 비운다 — 그 공백이 곧 구분자다(`%cA%c\\n%cB%c…`)."""
        got, bad = self.t("%cゲイル%c\n%cソニア%cという 者だ。%c", "라는 자다.")
        self.assertIsNone(bad)
        self.assertEqual(got, "%c게일%c\n%c소니아%c라는 자다.%c")

    def test_name_slots_are_translated_not_blanked(self):
        """🔴 본문 아닌 이름 자리를 비우면 화면에서 이름이 사라진다(176블록)."""
        got, bad = self.t("%cソニア%cが 仲間になりました。%c%c", "이(가) 동료가 되었다.")
        self.assertIsNone(bad)
        self.assertEqual(got, "%c소니아%c이(가) 동료가 되었다.%c%c")

    def test_unknown_name_slot_rejects_the_block(self):
        """정본에 없는 이름 자리가 있으면 버린다 — 우리 문안이 그걸 이미 품고 있다."""
        got, bad = self.t("%cゲイル%cは%c謎の靴%cを 見つけた。%c", "은(는) 신발을 찾았다.")
        self.assertIsNone(got)
        self.assertIn("정본에 없는", bad)

    def test_ps1_markup_is_converted(self):
        """🔴 저본은 PS1 표기를 품는다 — 안 옮기면 `{p}` 가 글자로 찍힌다(89블록)."""
        self.assertEqual(T.to_saturn("가{n}나"), "가\n나")
        self.assertEqual(T.to_saturn("가{p}나"), "가%c나")
        self.assertEqual(T.to_saturn("\x1a은(는)"), "%s은(는)")
        self.assertEqual(T.to_saturn("\x1b점"), "%d점")

    def test_unknown_control_char_rejects(self):
        """옮기고도 제어문자가 남으면 버린다 — 화면에 그대로 나간다."""
        self.assertIsNone(T.to_saturn("가\x1c나"))
        self.assertIsNone(T.to_saturn("가{zz}나"))

    def test_fullwidth_alnum_becomes_halfwidth(self):
        """같은 몬스터가 대사와 전투에서 갈리면 안 된다(`카자즘Ｂ` vs `카자즘B`)."""
        self.assertEqual(T.to_saturn("카자즘Ｂ１"), "카자즘B1")

    def test_duplicate_arg_at_body_head_is_dropped(self):
        """원문 `%s は …` + 저본 `\\x1a은(는) …` → `%s%s` 가 되면 계약이 깨진다."""
        got, bad = self.t("%sは 読みました。%c", "\x1a은(는) 읽었다.")
        self.assertIsNone(bad)
        self.assertEqual(got, "%s은(는) 읽었다.%c")

    def test_sentence_in_speaker_slot_is_not_kept(self):
        """🔴 화자 자리에 인용문이 들면 원문을 남길 수 없다 — 두 번 나온다."""
        jp = "%c『長い 引用文が ここに 入ります』%c\nと 言った。%c"
        got, bad = self.t(jp, "「긴 인용문이 여기 들어갑니다」라고 말했다.")
        self.assertIsNone(got)
        self.assertIn("정본에 없는", bad)

    def test_name_like_speaker_survives_without_canon(self):
        """정본에 없어도 **이름꼴이면** 원문을 남긴다 — 빈 이름표보다 낫다."""
        got, bad = self.t("%cトッド%c\nＺ ｚ ｚ%c", "Z z z…")
        self.assertIsNone(bad)
        self.assertEqual(got, "%cトッド%c\nZ z z…%c")

    def test_body_in_single_slot_is_not_mistaken_for_speaker(self):
        """`%c본문%c%c` 은 화자가 아니다 — 개행이 없으면 화자가 아니다(203블록)."""
        got, bad = self.t("%c粘土の型を渡しました。%c%c", "점토 거푸집을 건넸다.")
        self.assertIsNone(bad)
        self.assertEqual(got, "%c점토 거푸집을 건넸다.%c%c")

    def test_over_window_is_rejected(self):
        """창 총량(전각 15×5)을 넘으면 뒷줄이 잘린다 — 넣지 않는다."""
        got, bad = self.t("%c兵士%c\n本文。%c", "가" * 80)
        self.assertIsNone(got)
        self.assertEqual(bad, "창을 넘는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
