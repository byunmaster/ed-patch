"""조판 전수(`check_layout`) — 축별 양성·음성 대조."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_layout as cl


def f(s, orig=False):
    return cl.findings(s, orig)


class Axes(unittest.TestCase):
    def test_first_space(self):
        self.assertEqual(f("{16}병사{14}↵ 안녕하십니까↵왕자님.⏎")["first_space"], 1)
        self.assertEqual(f("{16}병사{14}↵안녕하십니까↵왕자님.⏎")["first_space"], 0)

    def test_first_space_band_is_exempt(self):
        self.assertEqual(f("  루디아마을")["first_space"], 0)  # 한 줄짜리 띠는 가운데 맞춤

    def test_orphan_punct(self):
        self.assertEqual(f("{16}병사{14}↵왕자님↵, 안녕하세요.⏎")["orphan_punct"], 1)
        self.assertEqual(f("{16}병사{14}↵왕자님,↵안녕하세요.⏎")["orphan_punct"], 0)

    def test_blank_line(self):
        self.assertEqual(f("{16}병사{14}↵안녕↵↵하세요.⏎")["blank_line"], 1)
        self.assertEqual(f("{16}병사{14}↵안녕↵하세요.⏎")["blank_line"], 0)
        self.assertEqual(f("{16}병사{14}↵안녕↵{name}↵하세요.⏎")["blank_line"], 0)  # 변수 자리만 든 줄은 빈 줄이 아니다

    def test_last_page_single_word(self):
        self.assertEqual(f("{16}병사{14}↵안녕하세요.↵반갑습니다.⏎↵이만⏎")["last_page"], 1)
        self.assertEqual(f("{16}병사{14}↵안녕하세요.↵반갑습니다.⏎↵이만 가네.⏎")["last_page"], 0)

    def test_page_orphan_mid_sentence(self):
        self.assertEqual(f("{16}병사{14}↵왕자님,↵어찌하여⏎↵그리 다치셨습니까?⏎")["page_orphan"], 1)
        self.assertEqual(f("{16}병사{14}↵왕자님,↵안녕하세요.⏎↵그리 다치셨습니까?⏎")["page_orphan"], 0)

    def test_overflow(self):
        self.assertEqual(f("{16}병사{14}↵가나다라마바사아자차카타파하가나↵왕자님.⏎")["overflow"], 1)


class Colors(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(cl.color_findings("{06}{16}ABC{04}가", "ABC가")["color_missing"], 1)
        self.assertEqual(cl.color_findings("{06}{16}ABC{04}가", "{06}{16}ABC{04}가")["color_missing"], 0)

    def test_unclosed(self):
        self.assertEqual(cl.color_findings("{16}병사{14}↵안녕", "{16}병사↵안녕")["color_unclosed"], 1)
        self.assertEqual(cl.color_findings("{16}병사{14}↵안녕", "{16}병사{14}↵안녕")["color_unclosed"], 0)

    def test_midword(self):
        self.assertEqual(cl.color_findings("x", "아{16}프로스{14}")["color_midword"], 1)
        self.assertEqual(cl.color_findings("x", "아 {16}프로스{14}")["color_midword"], 0)

    def test_center_skew(self):
        o = "\u3000\u3000AB\u3000\u3000"
        self.assertEqual(cl.center_findings(o, "\u3000\u3000제１장\u3000\u3000")["center_skew"], 0)
        self.assertEqual(cl.center_findings(o, "\u3000제１장\u3000\u3000\u3000\u3000")["center_skew"], 1)  # 24px 차
        g = cl.center_findings(o, "\u3000 제１장\u3000  ")  # 16 vs 20 — 4px 격자 한계
        self.assertEqual((g["center_skew"], g["center_grid"]), (0, 1))
        self.assertEqual(cl.center_findings(o, "\u3000\u3000제１장.\u3000")["center_skew"], 0)  # 줄 끝 부호는 오른쪽 여백(12 + 부호 폭 ≈ 24)

    def test_center_one_sided_exempt(self):
        self.assertEqual(cl.center_findings("\u3000\u3000AB\u3000", " 루디아마을")["center_skew"], 0)  # 왼쪽 맞춤 지명 칸

    def test_one_line(self):
        self.assertEqual(cl.one_line_findings("{16}병사{14}↵네, 여기↵있습니다."), 1)
        self.assertEqual(cl.one_line_findings("{16}병사{14}↵네, 여기 있습니다.↵감사합니다."), 0)
        self.assertEqual(cl.one_line_findings("{16}병사{14}↵왕자님께서 그렇게 말씀하셨기에↵저도 따랐습니다."), 0)  # 한 줄을 넘는 문장
        self.assertEqual(cl.one_line_findings("{01}삽니다　↵{01}팝니다　"), 0)  # 메뉴

    def test_reward(self):
        o = "↵ＥＰ\u3000{15 85}{name}ポイント獲得↵"
        self.assertEqual(cl.reward_findings(o, "↵ＥＰ{15 85}{name} 포인트 획득↵"), 0)
        self.assertEqual(cl.reward_findings(o, "↵ＥＰ {15 85}{name} 포인트 획득↵"), 1)  # 수 앞 공백
        self.assertEqual(cl.reward_findings(o, "ＥＰ{15 85}{name} 포인트 획득↵"), 1)  # 앞 개행 없음

    def test_chapter_gap(self):
        self.assertEqual(cl.chapter_gap_findings("제３장\u3000용의 알"), 0)
        self.assertEqual(cl.chapter_gap_findings("제３장   용의 알"), 0)  # 공백 셋 = 12px
        self.assertEqual(cl.chapter_gap_findings("제３장  용의 알"), 1)  # 8px
        self.assertEqual(cl.chapter_gap_findings("제３장 용의 알"), 1)

    def test_banner_center(self):
        o = "{06}\u3000{0E}ルディア{0F}の町"
        self.assertEqual(cl.banner_skew(o, "  루디아마을"), 0)  # 5음절 60px · 앞 공백 8px → 글 가운데 271(양성 대조)
        self.assertEqual(cl.banner_skew(o, " 루디아마을"), -4)  # 원판식 한 칸 — 4px 왼쪽
        self.assertEqual(cl.banner_skew(o, "루디아마을"), -8)
        self.assertEqual(cl.banner_skew("{08}{08}{0E}ルディア城", "{08}{08} 루디아성"), -2)  # 머리 `{08}` 하나 4px
        self.assertIsNone(cl.banner_skew("{10 30}\u3000{0E}ロンド{0F}の港\u3000{11 33 30}", "{10 30}론도항구{11 33 30}"))  # 목록 줄은 틀이 아니다
        self.assertIsNone(cl.banner_skew("毒鉱石", "독광석"))  # 몬스터 이름

    def test_window_short(self):
        o = "{16}병사{14}↵왕자님, 엘아스타를 지키겠습니다.⏎↵안심하십시오.⏎"
        self.assertEqual(cl.window_short(o, "{16}병사{14}↵왕자님, 엘아스타를 지키겠습니다.↵안심하십시오.⏎"), 1)  # 두 창을 한 창으로 합침
        self.assertEqual(cl.window_short(o, "{16}병사{14}↵왕자님, 엘아스타를 지키겠습니다.⏎↵안심하십시오.⏎"), 0)

    def test_window_extra(self):
        o = "{16}女{14}↵あら　これは　王子さま。↵竜の卵を　戻したのは↵王子さまだとききましたわよ。⏎ "
        self.assertEqual(cl.window_extra(o, "{16}여자{14}↵어머, 왕자님.⏎↵용의 알을 되돌린 게↵왕자님이시라고 들었어요.⏎"), 1)  # 짧은 감탄이 따로 창
        self.assertEqual(cl.window_extra(o, "{16}여자{14}↵어머, 왕자님.↵용의 알을 되돌린 게↵왕자님이시라고 들었어요.⏎"), 0)  # 한 창
        long_ = "{16}여자{14}↵" + "이 문장은 아주 길어서 한 창에 도저히 들어가지 않습니다. " * 4 + "⏎"
        self.assertEqual(cl.window_extra(o, long_.replace(". ", ".⏎↵")), 0)  # 길어서 부득이 — 안 센다

    def test_comma_conn(self):
        self.assertEqual(cl.comma_findings("{16}병사{14}↵저는 가고, 집에 왔어요."), 1)
        self.assertEqual(cl.comma_findings("{16}병사{14}↵마시고, 놀고, 먹고."), 0)  # 나열
        self.assertEqual(cl.comma_findings("{16}병사{14}↵아이고, 왕자님."), 0)  # 말머리
        self.assertEqual(cl.comma_findings("{16}병사{14}↵저는 가고 집에 왔어요."), 0)
        self.assertEqual(cl.comma_findings("{16}노인{14}↵광산도 그럭저럭 복구됐고, 몬스터도 사라져서 한시름 놓았다네."), 0)  # 대구(마스터 11-06)


class HeadRows(unittest.TestCase):
    def test_after_head_only_four_rows(self):
        prev = "{16}병사{14}↵"
        self.assertEqual(cl.head_rows(prev, "a↵b↵c⏎", "가↵나↵다↵라⏎"), 1)
        self.assertEqual(cl.head_rows(prev, "a↵b↵c⏎", "가↵나↵다⏎"), 0)
        self.assertEqual(cl.head_rows("{16}병사{14}↵가↵나⏎", "a⏎", "가↵나↵다↵라⏎"), 0)


class BannerPad(unittest.TestCase):
    def test_box_line_too_wide(self):
        self.assertEqual(cl.banner_pad("642:14:3", "x", "{10 30}\u3000\u3000낫슈마을\u3000\u3000{11 33 30}"), 1)
        self.assertEqual(cl.banner_pad("642:14:5", "x", "{10 30}\u3000 스엘마을\u3000  {11 33 30}"), 0)
        self.assertEqual(cl.banner_pad("642:14:5", "x", "일반 대사"), 0)


    def test_pause_sp(self):
        self.assertEqual(cl.pause_sp_findings("없을… {12} 터이니"), 1)
        self.assertEqual(cl.pause_sp_findings("없을…{12} 터이니"), 0)
        self.assertEqual(cl.pause_sp_findings("없을 {12}터이니"), 0)

    def test_color_lead_sp(self):
        self.assertEqual(cl.color_lead_sp_findings("{17} 안녕↵본문"), 1)
        self.assertEqual(cl.color_lead_sp_findings("본문↵{15 81}\u3000"), 1)
        self.assertEqual(cl.color_lead_sp_findings("{17}안녕{14} 다음"), 0)


if __name__ == "__main__":
    unittest.main()
