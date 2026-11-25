"""조판 축 전수 게이트(`check_typeset_axes`) — 양성 대조가 통과하고 예외 조건이 지켜진다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_typeset_axes as c


class Axes(unittest.TestCase):
    def test_양성_대조는_못_세는_축이_없다(self):
        self.assertEqual(c.selftest(), [])

    def test_원판도_부호만_있는_줄은_고아가_아니다(self):
        self.assertTrue(c.axes_of("가\n!?\n", "가\n!?\n")["고아부호"] == [])
        self.assertTrue(c.axes_of("가\n!?\n", "가\n나\n")["고아부호"])

    def test_색_수가_원판과_다르면_걸린다(self):
        self.assertTrue(c.color_axes("가", "<COLOR_C>가<COLOR_POP>")["색불일치"])
        self.assertFalse(c.color_axes("<E3>가<E1>", "<COLOR_C>가<COLOR_POP>")["색불일치"])

    def test_가운데_맞춘_원판_줄은_우리도_가운데다(self):
        jp = "가나다\n" + "\u3000" * 7 + "가나다라"  # 원판: 창 폭 17칸 안에서 앞 7 · 뒤 6칸
        self.assertTrue(c.center_axes("가나다\n가나다", jp))  # 왼쪽에 붙이면 걸린다
        self.assertFalse(c.center_axes("가나다\n" + " " * 14 + "가나다", jp))  # 반각 공백 14칸 = 56px, 글 24px → 좌우 56px
        self.assertTrue(c.center_axes("가나다\n" + " " * 13 + "가나다", jp))  # 4px 어긋남

    def test_가운데_폭은_줄_끝_부호를_뺀다(self):
        jp = "가나다\n" + "\u3000" * 7 + "가나다라"
        self.assertFalse(c.center_axes("가나다\n" + " " * 14 + "가나다…", jp))

    def test_쉼표는_규칙_예시_꼴만_명백으로_센다(self):
        self.assertTrue(c.comma_candidates("파렌 왕국은, 가난한 나라였다.")[0])  # 주제 뒤
        self.assertTrue(c.comma_candidates("처음에는, 평화로웠다.")[0])  # 부사어 뒤
        self.assertTrue(c.comma_candidates("문을 열고, 밖으로 나갔다.")[0])  # 짧은 연결 어미
        for keep in ("아트라스, 어서 와라.", "그래, 알았다.", "란도, 플로라, 모두 모였다.", "그건 그렇고, 돈은 있나?", "「마시려면 들지 말고, 들려면 마시지."):
            self.assertFalse(c.comma_candidates(keep)[0], keep)

    def test_긴_연결_절은_쉼표를_남긴다(self):
        self.assertFalse(c.comma_candidates("튼튼한 천을 쓰면 올이 성글어서 바람이 새어 나가고, 바람이 안 든다.")[0])

    def test_사전_토큰은_펼쳐서_센다(self):
        self.assertEqual(c.typeset.expand_static("{D5:29}"), "나타났다.")
        self.assertEqual(c.typeset.expand_static("{D5:2D}{을/를}"), "주문을")
        self.assertEqual(c.typeset.expand_static("{D6}{을/를}"), "{D6}{을/를}")  # 런타임 변수는 폭을 몰라 남긴다
        self.assertTrue(c.oneline_axes("어머!! 이것 참,\n과연 {D0:46}이시군요.\n"))
        self.assertFalse(c.oneline_axes("어머!! 이것 참,\n과연 {D6}이시군요.\n"))
        self.assertTrue(c.orphan_axes(c.typeset.expand_static("가나다 라마바 사아자\n{D5:29}"), "")[0])

    def test_말로는_쉼표는_뺀다_감탄_머리는_센_절이_아니다(self):
        self.assertTrue(c.comma_candidates("{D1:2D}{D1:01}에서 온 {D0:4B} 말로는, 우두머리가 있다더군.")[0])
        self.assertFalse(c.comma_candidates("<E3>{D0:27}\n<E1>아이고, 왕자님! 마침내 왔군요.")[0])


if __name__ == "__main__":
    unittest.main()
