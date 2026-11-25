"""조판 축 전수 게이트(`check_typeset_axes`) — 축마다 양성(잡힌다) · 음성(안 잡힌다) 대조. 검사기가 눈을 감지 않았음을 보인다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_typeset_axes as C
import scene


def T(s):
    return scene.Token(0, s.encode("cp932"), "text")


def K(code):
    return scene.Token(0, bytes([code]), "ctl", code)


NL, PG = K(1), K(5)


def axes(tokens, ours="", **kw):
    return {a for a, _ in C.analyze(tokens, ours, **kw)}


class Axes(unittest.TestCase):
    def test_first_cell_space(self):
        self.assertIn("첫칸공백", axes([T("ab"), NL, T(" cd")]))
        self.assertNotIn(
            "첫칸공백", axes([T("ab"), NL, T(" cd")], "ab<01> cd")
        )  # 문안에 박은 들여쓰기
        self.assertNotIn("첫칸공백", axes([T("ab"), NL, T("cd")]))

    def test_orphan_punct(self):
        self.assertIn("고아부호", axes([T("hello world"), NL, T(".")]))
        self.assertNotIn("고아부호", axes([T("hello world."), NL, T("...")]))  # 앞 줄이 문장 끝
        self.assertNotIn(
            "고아부호", axes([K(0x1E), T("guard"), K(4), NL, T("...")])
        )  # 이름표 다음 말줄임 한 줄

    def test_blank_line(self):
        self.assertIn("빈줄개행", axes([T("aa"), NL, NL, T("bb")]))
        self.assertNotIn("빈줄개행", axes([T("aa"), NL, T("bb")]))

    def test_punct_space(self):
        self.assertIn("부호뒤공백", axes([T("ab,cd")]))
        self.assertNotIn("부호뒤공백", axes([T("ab, cd"), NL, T("1,000")]))

    def test_word_fold(self):
        self.assertIn("낱말속접힘", axes([T("abc"), NL, T("def")], "abcdef"))
        self.assertNotIn("낱말속접힘", axes([T("abc"), NL, T("def")], "abc def"))

    def test_width_and_line_count(self):
        self.assertIn("줄폭넘침", axes([T("x" * 40)]))
        self.assertIn("줄수넘침", axes([T("a"), NL, T("b"), NL, T("c")], cap=2))
        self.assertNotIn("줄수넘침", axes([T("a"), NL, T("b")], cap=2))

    def test_last_window_one_word(self):
        ax = axes([T("hello world and"), PG, T("again")])
        self.assertIn("끝창한어절", ax)
        self.assertNotIn(
            "끝창한어절", axes([T("hello world and"), PG, T("again")], ret_end=True)
        )  # 되돌림 조각
        self.assertNotIn(
            "끝창한어절", axes([T("hello world."), PG, T("again")])
        )  # 앞 창이 문장을 끝냈다

    def test_page_end_orphan_and_skew(self):
        self.assertIn("쪽끝고아", axes([T("aa bb"), NL, T("cc"), PG, T("dd ee")]))
        self.assertNotIn(
            "쪽끝고아", axes([T("aa bb"), NL, T("cc"), PG, T("dd ee")], "aa bb cc\f dd ee")
        )  # 박은 쪽 나눔
        sk = axes([T("aa bb"), NL, T("cc dd"), NL, T("ee ff"), PG, T("g h")])
        self.assertIn("창치우침", sk)

    def test_color_span(self):
        self.assertIn(
            "색범위낱말", axes([T("ab"), K(0x1C), T("cd"), K(4)])
        )  # 낱말 한가운데서 색이 바뀐다
        self.assertIn("색범위낱말", axes([K(0x1C), T(" xy "), K(4)]))  # 공백이 칠해진다
        self.assertNotIn("색범위낱말", axes([T("ab "), K(0x1C), T("cd"), K(4), T("e")]))

    def test_punct_before_space(self):
        self.assertIn("부호앞공백", axes([T("ab ,cd")]))
        self.assertNotIn(
            "부호앞공백", axes([T("ab, "), K(0x10), T("!")])
        )  # 호출이 끼면 이어 찍히지 않는다

    def test_ellipsis_rules_on_text(self):
        # cp932 에는 「…」(U+2026) 가 있다 — 문자열로 직접 푼다
        self.assertIn("말줄임뒤공백", {a for a, _ in C.analyze([_tok_u("ab…cd")], "")})
        self.assertNotIn("말줄임뒤공백", {a for a, _ in C.analyze([_tok_u("ab… cd")], "")})
        # 2-11 예외 — 한 낱말을 음절마다 끊어 말함 · 같은 소리 되풀이는 붙여도 「통과」(마스터 10-12·13)
        for ok in ("세…리…오…스…", "조…심…해…라…", "없…다…", "불…가…능…하다…", "흑…흑…흑…"):
            self.assertNotIn("말줄임뒤공백", {a for a, _ in C.analyze([_tok_u(ok)], "")}, ok)
        # 낱말이 바뀌면 띄운다 — 붙었으면 잡는다
        for bad in ("하지만…나를", "아…그래", "몸이…인간"):
            self.assertIn("말줄임뒤공백", {a for a, _ in C.analyze([_tok_u(bad)], "")}, bad)
        self.assertIn("부호순서", {a for a, _ in C.analyze([_tok_u("ab?…")], "")})
        self.assertNotIn("부호순서", {a for a, _ in C.analyze([_tok_u("ab…?")], "")})


def _tok_u(s):
    """한글은 정본 글자 코드(2B)로, 나머지는 cp932 로 — 빌드 롬이 내는 토큰 꼴."""
    fwd = {v: k for k, v in C.REV.items()}
    raw = b"".join(fwd[ch].to_bytes(2, "big") if ch in fwd else ch.encode("cp932") for ch in s)
    return scene.Token(0, raw, "text")


class WindowMoreRatchet(unittest.TestCase):
    """창많음(2-17) 래칫 — 기준선 항목은 우리 창 수가 같거나 줄면 통과, 늘거나 기준선에 없으면 실패."""

    BASE = ["씬 100:0abc 원판 3창 → 우리 4창"]

    def test_same_or_fewer_passes(self):
        self.assertTrue(C._within_base("씬 100:0abc 원판 3창 → 우리 4창", self.BASE))
        self.assertTrue(C._within_base("씬 100:0abc 원판 3창 → 우리 3창", self.BASE))

    def test_more_or_unknown_fails(self):
        self.assertFalse(C._within_base("씬 100:0abc 원판 3창 → 우리 5창", self.BASE))
        self.assertFalse(C._within_base("씬 101:0abc 원판 3창 → 우리 4창", self.BASE))


if __name__ == "__main__":
    unittest.main()


class RuleBand(unittest.TestCase):
    """2-13 쉼표 · 2-10 한 줄 문장 · 2-8 가운데 정렬 — 한글을 그대로 토큰에 싣고(`dec` 를 utf-8 로 바꿔) 센다."""

    def setUp(self):
        self._dec = C.dec
        C.dec = lambda raw: raw.decode("utf-8")

    def tearDown(self):
        C.dec = self._dec

    @staticmethod
    def U(s):
        return scene.Token(0, s.encode("utf-8"), "text")

    def comma(self, s):
        return [d for a, d in C.comma_axis([self.U(s)])]

    def test_comma_short_connective_flagged(self):
        self.assertTrue(self.comma("파렌 왕국은, 작았다."))  # 주제 뒤
        self.assertTrue(self.comma("문을 열고, 안으로 들어갔다."))  # 짧은 연결 어미(7음절)
        self.assertTrue(self.comma("배가 고팠는데, 먹을 것이 없었다."))  # ⑨ 앞 절 짧음

    def test_comma_geureom_rule10(self):
        self.assertTrue(self.comma("그럼, 이 나이프를 지니십시오."))  # ⑩ 문장 앞 접속
        self.assertFalse(self.comma("그럼, 왕자님."))  # 부르는 말 앞
        self.assertFalse(self.comma("그럼, 몸조리 잘해."))  # 작별

    def test_comma_kept_classes_pass(self):
        self.assertFalse(self.comma("아트라스, 이리 와라."))  # 부르는 말
        self.assertFalse(self.comma("그래, 알았다."))  # 감탄·응답
        self.assertFalse(
            self.comma(
                "이 마을에서 가장 오래된 집에 살고 있는 노인이 말하기를, 아주 오래전의 이야기다."
            )
        )  # 앞 절이 길다
        self.assertFalse(self.comma("어디 보자고, 이 열쇠 구멍에"))  # 인용형 어미
        self.assertFalse(self.comma("뭐냐 네놈은, 고든의 부하냐?"))  # 눈으로 판정한 도치

    def sent(self, lines, scene_mode=True):
        toks = []
        for i, ln in enumerate(lines):
            if i:
                toks.append(NL)
            toks.append(self.U(ln))
        return {a for a, _ in C.oneline_axis(toks, scene_mode)}

    def test_one_line_sentence_split_flagged_when_room(self):
        self.assertIn("한줄문장쪼갬", self.sent(["하지만 이제", "괜찮아. 고마워."]))  # 빈 줄이 있다
        self.assertEqual(
            self.sent(["하지만 이제 괜찮아.", "고마워."]), set()
        )  # 이미 새 줄에서 시작

    def test_one_line_sentence_split_allowed_when_full(self):
        full = ["하지만 이제", "괜찮아. 고마워.", "세 번째 줄이다."]
        self.assertEqual(self.sent(full), {"한줄문장쪼갬허용"})  # 쪽이 꽉 참 — 2-17

    def test_long_sentence_not_flagged(self):
        self.assertEqual(
            self.sent(["아주 오래전 어느 먼 나라에 살던 왕자가", "용을 물리쳤다고 한다."]), set()
        )

    def test_center_gap(self):
        self.assertAlmostEqual(
            C._center_lines("        제목 글")[0][0], 48 + 21
        )  # 앞 공백 8칸(48px) + 글 폭(42px)의 절반
        # 장 제목: 사이 반각 2칸 고정(마스터 11-03), 줄 시작 위치로만 맞춘다 — 반 칸(3px) 이하 쏠림은 허용
        for t in ("        제１장  왕자의 여행", "       제１장  왕자의 여행"):
            self.assertLessEqual(abs(C._center_lines(t)[0][0] - C.CENTER_REF), C.CENTER_TOL)
        self.assertGreater(
            abs(C._center_lines("      제１장  왕자의 여행")[0][0] - C.CENTER_REF), C.CENTER_TOL
        )  # 앞 6칸이면 9px 쏠려 걸린다


class BannerCenter(unittest.TestCase):
    def test_banner_center(self):
        import field_names as fn

        ents = [("t", kr, len(e)) for _i, kr, e, _j in fn.ENTRIES]
        # 지금 배너: 보이는 상자 안쪽 중심 대비 잉크 최근접 → 통과
        self.assertEqual(C.banner_center_items(ents, ink_px=fn.BANNER_INK_PX), [])
        # 양성 대조: 한 바이트(7.5px) 어긋난 목표(−7.5)면 짝수 본문이 걸린다
        self.assertTrue(C.banner_center_items(ents, ink_px=fn.BANNER_INK_PX - 7.5))
        # 목적지 칸은 틀 보정 0 — 대칭이면 통과
        self.assertEqual(C.banner_center_items(ents), [])
