"""줄·쪽 나눔 전면 규칙(번역 규칙 2-16) — 조판기 규칙 ①~④ 와 지표(linemetrics) 자신을 지킨다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import linemetrics
import typeset

DM: dict[str, str] = {}
ML = {"D6": 48, "D7": 48, "D8": 64, "D9": 64, "DB": 64, "DC": 24, "DD": 64}


def wrap(kr: str) -> str:
    return typeset.wrap(kr, DM, ML, rules=True)


class LineRules(unittest.TestCase):
    def test_문장_중간_손_개행은_공백으로_읽는다(self):
        kr = "이야기할\n수 있는 사람이다."
        self.assertEqual(wrap(kr), "이야기할 수 있는 사람이다.")

    def test_문장_끝_개행과_화자_머리_개행은_둔다(self):
        self.assertEqual(wrap("첫째 줄이다.\n둘째 줄이다."), "첫째 줄이다.\n둘째 줄이다.")
        self.assertEqual(wrap("<E3>{D0:07}\n<E1>안녕"), "<E3>{D0:07}\n<E1>안녕")
        self.assertEqual(typeset.soften("{D0:81}\n아니"), "{D0:81}\n아니")  # 파티 화자 표지 줄

    def test_장_제목_카드는_손대지_않는다(self):
        kr = "<FF>제１장\n왕자의 여행\n                끝<FF>"
        self.assertEqual(wrap(kr), kr)

    def test_절째_내린다(self):
        # 17칸(136px)을 넘는 자리에서 이 줄에서 시작한 절이 다음 줄에 통째로 들어가면 절째 내린다
        kr = "아무리 찾아봐도 소용없었지만, 그래도 끝까지 포기하지 않았다."
        res = wrap(kr)
        self.assertIn("아무리 찾아봐도 소용없었지만,\n", res)
        self.assertEqual(typeset.wrap(kr, DM, ML, rules=False).count("\n"), res.count("\n"))

    def test_고유명사는_한_줄(self):
        res = wrap("오늘은 이제 슬라임 괴롭히기 같은 놀이는 그만두시오.")
        self.assertNotIn("슬라임\n괴롭히기", res)

    def test_경계_세기(self):
        self.assertEqual(typeset.bclass("끝났다."), 3)
        self.assertEqual(typeset.bclass("찾았지만,"), 2)
        self.assertEqual(typeset.bclass("오,"), 0)  # 두 음절 이하 쉼표
        self.assertEqual(typeset.bclass("그리고"), 0)  # 문장 머리 접속어
        self.assertEqual(typeset.bclass("놓치고", "말아서"), 0)  # 본용언+보조용언

    def test_쪽_끝_고아는_앞_줄_어절을_내려_메운다(self):
        kr = "그분을 찾아내신다면 분명 힘이 되어 주실\n것입니다.<FF>"
        res = wrap(kr)
        self.assertFalse(linemetrics.orphan_pages(res)[0], res)

    def test_명사구_판정(self):
        self.assertTrue(typeset.noun_noun("노예", "상인"))
        self.assertFalse(typeset.noun_noun("가는", "상인"))  # 관형형
        self.assertFalse(typeset.noun_noun("노예를", "상인"))  # 조사
        self.assertFalse(typeset.noun_noun("정말", "상인"))  # 부사
        self.assertEqual(typeset._stem("상인이"), "상인")

    def test_퇴행_금지_한_줄이던_문장을_쪼개지_않는다(self):
        # 관리자 표본 10-26: 「…기다리고⏎있었네. 수고했네.」 — 보조용언을 가르고 한 줄 문장을 쪼갰다
        res = typeset.wrap("오오, {D0:01}. 기다리고 있었네. 수고했네.", {"D0:01": "가이"}, ML, rules=True)
        self.assertNotIn("기다리고\n있었네", res)
        self.assertIn("기다리고 있었네.", res)

    def test_관형사는_줄_끝에_홀로_남기지_않는다(self):
        self.assertTrue(typeset._bad_break("이런", "물건이"))
        self.assertTrue(typeset.bonded("해", "줬잖아"))
        self.assertTrue(typeset.bonded("50000", "GOLD군요."))
        res = typeset.wrap("앗 그래 그래, 마을에 있던 괴물을 쓰러뜨리니 이런 물건이 나왔어.", DM, ML, rules=True)
        self.assertNotIn("이런\n", res)

    def test_절_경계를_잃는_변형은_거부한다(self):
        # 관리자 재표본 10-26: 줄 끝이 연결어미(-련만)이던 손 개행을 공백으로 읽어 목적어·주어가 줄 끝에 남았다
        kr = "아직 살아 있으면 좋으련만\n마물들한테 잡혀갔다면\n이제쯤은…\n"
        res = typeset.wrap(kr, DM, ML, rules=True)
        self.assertIn("좋으련만\n", res)  # 줄 끝 절 경계는 지킨다
        self.assertEqual(typeset.orphan_count(res), 0)  # 쪽 끝 한 어절 고아(2-16 ③)가 절 경계(②)보다 앞선다 — 마스터 10-31, 고아를 없애며 절 경계 하나를 치른다
        self.assertEqual(typeset.bclass("좋으련만"), 1)
        self.assertEqual(typeset.soften("말이다만\n검을 손에"), "말이다만\n검을 손에")  # 앞 어절이 절 경계면 손 개행을 둔다

    def test_마지막_창에_한_어절만_남지_않게_창_경계를_앞으로_당긴다(self):
        res = "첫째 줄은 이렇게 길다 정말,\n둘째 줄도 이어서 갑니다,\n그래서<FF>끝\n<E0>"
        h, _h2 = typeset.window_issues(res)
        self.assertEqual(len(h), 1)
        bal = typeset._balance_windows(res)
        self.assertEqual(typeset.window_issues(bal)[0], [])
        self.assertTrue(typeset._same_text(res, bal))  # 글·창 수 그대로, `<FF>` 위치만

    def test_새_화자_창과_제어_코드_줄은_옮기지_않는다(self):
        res = "가나다 라마바\n사아자 차카타<FF><E3>누구\n<E1>네.\n<E0>"
        self.assertEqual(typeset._balance_windows(res), res)  # 뒤 창이 새 화자
        res2 = "가나다 라마바\n<F0:12>사아자 차카타<FF>끝\n<E0>"
        self.assertEqual(typeset._balance_windows(res2), res2)  # 옮길 줄에 제어 코드

    def test_제어_조각_줄의_손_개행은_불가침(self):
        kr = "{D5:13}\n{D5:14}\n{D5:15}\n"
        self.assertEqual(typeset.wrap(kr, DM, ML, rules=True), kr)
        self.assertEqual(typeset.token_nl_lost(kr, kr.replace("\n", " ")), 3)

    def test_관형형_의존명사와_기로_되다는_갈리지_않는다(self):
        self.assertTrue(typeset.bonded("늘어놓는", "쪽이"))
        self.assertTrue(typeset.bonded("혼인하기로", "되어"))
        self.assertFalse(typeset.bonded("가는", "사람"))

    def test_지표가_고아와_손_개행을_센다(self):
        a, b = linemetrics.orphan_pages("가나다 라마바 사아자\n차카\n타<FF>")
        self.assertEqual((len(a), len(b)), (1, 1))
        self.assertEqual(len(linemetrics.orphan_pages("가나다 라마바\n끝났다.<FF>")[1]), 0)
        self.assertEqual(len(linemetrics.orphan_pages("제１장\n부제 있음\n                끝<FF>")[0]), 0)

    def test_한_줄에_들어가는_문장은_새_줄에서_시작한다(self):
        # 2-10 — 「…올랐다. MP가 / 5포인트 올랐다.」 → 문장을 새 줄에. 줄 수는 안 늘고 글자는 그대로
        page = "레벨이 올랐다. 힘이\n5포인트 올랐다."
        out = typeset.one_line_sentences(page)
        self.assertEqual(out, "레벨이 올랐다.\n힘이 5포인트 올랐다.")
        self.assertEqual(out.replace("\n", " "), page.replace("\n", " "))

    def test_한_줄_문장_규칙은_줄머리_조각과_토큰_줄을_건드리지_않는다(self):
        for page in ("<E3>이름\n<E1>레벨이 올랐다.\n끝", "{D6}가 먼저\n간다.", " 들여쓴\n줄이다.", "가 나\n<EE:A3FD05>다.", "{D5:14}\n{D5:15}"):
            self.assertEqual(typeset.one_line_sentences(page), page)  # 런타임 변수 든 문장 · 토큰만으로 된 줄(관리자 10-26)은 그대로

    def test_사전_토큰은_펼친_폭으로_한_줄_문장을_합친다(self):
        self.assertEqual(typeset.one_line_sentences("{D0:01}가 먼저\n간다."), "{D0:01}가 먼저 간다.")
        self.assertEqual(typeset.expand_static("{D5:29}"), "나타났다.")

    def test_한_줄_문장_규칙은_쪽_끝_고아를_늘리지_않는다(self):
        # 뒤 글이 길어 문장 뒤에 이을 수 없고 새 줄로 가면 마지막 줄이 한 어절이 된다 → 안 한다
        page = "어머, 성으로\n돌아가셨다지요. 경하드리옵니다."
        self.assertEqual(typeset.one_line_sentences(page), page)


if __name__ == "__main__":
    unittest.main()
