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



def test_ellipsis_spacing_rule_2_11():
    import typeset

    assert typeset.spaced("그대도…잊었다") == "그대도… 잊었다"
    assert typeset.spaced("그래………프레이아님!!") == "그래……… 프레이아님!!"
    # 문장 맨 앞 `…` 는 붙인다(마스터 10-13) — 앞말 뒤의 말줄임이 아니다
    assert typeset.spaced("………프레이아님!!") == "………프레이아님!!"
    assert typeset.spaced("…라우엘까지… 알겠어요") == "…라우엘까지… 알겠어요"
    assert typeset.spaced("어라?! …아트라스 왕자님?") == "어라?! …아트라스 왕자님?"
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


class PostCtrl(unittest.TestCase):
    def test_화자_뒤_멈춤_인자의_0F_는_지우지_않는다(self):
        # `11 37 0F` 는 인자 둘 — 가나 모드 짝 `0F` 단독만 지운다(옛 바이트 치환은 인자를 먹어 뒤 글 첫 바이트가 인자가 됐다)
        raw = bytes.fromhex("1030160e6765140d103411370f6fb3bcc3") + b"\x11\x31\x30"
        f = dialog.parse_frame(raw)
        self.assertIsNotNone(f)
        self.assertIn(b"\x11\x37\x0f", f.post)
        raw2 = bytes.fromhex("160e6765140f0d6fb3bc")  # 단독 0F 는 지운다
        self.assertNotIn(b"\x0f", dialog.parse_frame(raw2).post)

if __name__ == "__main__":
    unittest.main()


class TestMarkArgs(unittest.TestCase):
    def test_멈춤_인자가_숫자가_아니면_0으로_고친다(self):
        """원문 `11 35 74`(둘째 인자가 숫자가 아님) — 한글 앞에 낱자가 찍히던 것."""
        import dialogue
        import font

        tab = font.GlyphTable()
        tab.map = {c: i for i, c in enumerate("가나다")}
        out = dialogue._encode([["가나다"]], [(1, b"\x115t")], 3, tab)
        self.assertNotIn(b"t", out)
        self.assertIn(b"\x1150", out)


class TestEngineWrap(unittest.TestCase):
    def test_줄_끝_부호가_168px_에_닿으면_엔진이_부호만_다음_줄로_꺾는다(self):
        """실측: `가`×12 + 공백 + `가` + `.` 은 168px 인데 엔진은 반각 부호도 12px 한 칸으로 재 `.` 만 떨어뜨린다 — 조판이 먼저 꺾는다."""
        import typeset

        for t in ("배 고장은 이제 다 고쳤습니다.", "사시겠어요? 역시 그러시군요."):
            for pg in typeset.pages(t):
                for line in pg:
                    self.assertFalse(typeset.engine_wraps(line), line)
