"""정본 문안 → 토큰 골격이 원본과 같은가. 셋 다 **인게임에서 물린** 회귀다(2026-09-07).

1. 인자 딸린 제어코드(`<0900>`)가 태그로 안 잡혀 글자로 흘렀다.
2. 화자가 스트림 안에 있는 자리에서 1쪽이 이름 칸에 박히고 마지막 쪽이 사라졌다.
3. `\\f` 뒤에 제어코드가 오면 쪽 넘김(`<05>`)이 통째로 없어졌다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import ps1_reuse
import scene
import textmap


def tok(raw: bytes, kind: str, code: int | None = None, target: int | None = None):
    t = scene.Token(0, raw, kind, code)
    if target is not None:
        t.target = target
    return t


def text(s: str):
    return tok(s.encode("cp932"), "text")


class ParseOurs(unittest.TestCase):
    def test_multibyte_control_is_a_tag(self):
        got = textmap.parse_ours("<0900><01>가나")
        self.assertEqual(got[0], ("ctl", (0x09, None, b"\x09\x00")))
        self.assertEqual(got[1], ("ctl", (0x01, None, b"\x01")))
        self.assertEqual(got[2], ("text", "가나"))


class OursFor(unittest.TestCase):
    def _stream(self, tokens):
        st = scene.Stream.__new__(scene.Stream)
        st.tokens = tokens
        st.start = 0
        return st

    def test_inline_speaker_keeps_pages(self):
        """`<1e>이름<04><01>` + 본문 2쪽 — 이름은 이름 자리에, 본문은 쪽대로."""
        st = self._stream(
            [
                tok(b"\x1e", "ctl", 0x1E),
                text("ライアス"),
                tok(b"\x04", "ctl", 0x04),
                tok(b"\x01", "ctl", 0x01),
                text("あ"),
                tok(b"\x01", "ctl", 0x01),
                text("い"),
                tok(b"\x05", "ctl", 0x05),
                text("う"),
                tok(b"\x00", "end", 0x00),
            ]
        )
        got = ps1_reuse.ours_for(st, ["첫 쪽", "둘째 쪽"], ["라이아스"])
        self.assertEqual(got, "<1e>라이아스<04><01>첫 쪽\f둘째 쪽<00>")

    def test_line_break_after_name_insert_survives(self):
        """`<0900><01>` 의 `<01>` 은 이름과 본문을 가르므로 살린다(본문 안의 것은 버린다)."""
        st = self._stream(
            [
                tok(b"\x09\x00", "ctl", 0x09),
                tok(b"\x01", "ctl", 0x01),
                text("あ"),
                tok(b"\x01", "ctl", 0x01),
                text("い"),
                tok(b"\x00", "end", 0x00),
            ]
        )
        self.assertEqual(ps1_reuse.ours_for(st, ["본문"]), "<0900><01>본문<00>")


class BuildStream(unittest.TestCase):
    class FakeCharset:
        def encode(self, s: str) -> bytes:
            return s.encode("utf-8")

    def test_page_break_before_control_survives(self):
        """`\\f` 뒤가 제어코드여도 `<05>` 가 나와야 한다."""
        st = scene.Stream.__new__(scene.Stream)
        st.tokens = [
            tok(b"\x09\x00", "ctl", 0x09),
            text("あ"),
            tok(b"\x05", "ctl", 0x05),
            tok(b"\x1e", "ctl", 0x1E),
            text("兵士"),
            tok(b"\x04", "ctl", 0x04),
            text("い"),
            tok(b"\x00", "end", 0x00),
        ]
        st.start = 0
        out = build.build_stream(st, "<0900>가\f<1e>병사<04>나", self.FakeCharset())
        self.assertIn(0x05, [t.code for t in out])

    def _blank_stream(self, ours, tail):
        st = scene.Stream.__new__(scene.Stream)
        st.tokens = [tok(b"\x0b", "ctl", 0x0B), tok(b"\x0e", "ctl", 0x0E)] + tail
        st.start = 0
        return build.build_stream(st, ours, self.FakeCharset())

    def test_blank_fragment_between_variables_survives(self):
        """`<ebf0> <0e>` — 훅과 품목 이름 사이 공백 하나짜리 조각이 조판기에 버려져 「일행은약초」로 붙었다."""
        out = self._blank_stream(
            "<0b><ebf0> <0e><ec02> 발견했다.<07>",
            [tok(b"\x07", "end", 0x07)],
        )
        raws = [t.raw for t in out]
        self.assertIn(b" ", raws)

    def test_trailing_space_before_variable_survives(self):
        """`제 이름은 <0e>입니다` — 조각 끝 공백도 조판기가 지워 「이름은류난」으로 붙었다(10-19 전수 검수)."""
        out = self._blank_stream(
            "<0b>제 이름은 <0e>입니다.<07>",
            [tok(b"\x07", "end", 0x07)],
        )
        texts = [t.raw for t in out if t.kind == "text"]
        self.assertTrue(texts[0].endswith(b" "), texts)

    def test_blank_fragment_before_final_end_is_dropped(self):
        out = self._blank_stream("<0b><ebf0> <00>", [tok(b"\x00", "end", 0x00)])
        self.assertNotIn(b" ", [t.raw for t in out])

    def test_blank_fragment_before_return_end_survives(self):
        """`<0b><ebf0> <06>` — 되돌림 끝(06) 조각의 공백은 호출한 쪽 글과의 이음새라 남긴다(「세리오스는이상한」)."""
        out = self._blank_stream("<0b><ebf0> <06>", [tok(b"\x06", "end", 0x06)])
        self.assertIn(b" ", [t.raw for t in out])


class Typeset(unittest.TestCase):
    def test_lead_space_survives(self):
        """조사 훅 뒤의 공백을 조판기가 지우면 안 된다 — 「눈물이들어 있었습니다」가 된다."""
        self.assertEqual(build.typeset(" 들어 있었습니다.", " "), [[" 들어 있었습니다."]])
        self.assertEqual(build.typeset(" 들어 있었습니다."), [["들어 있었습니다."]])


class MultiSpeaker(unittest.TestCase):
    def _stream(self, tokens):
        st = scene.Stream.__new__(scene.Stream)
        st.tokens = tokens
        st.start = 0
        return st

    def test_two_speakers_get_their_own_names(self):
        st = self._stream(
            [
                tok(b"\x1e", "ctl", 0x1E),
                text("A"),
                tok(b"\x04", "ctl", 0x04),
                text("あ"),
                tok(b"\x05", "ctl", 0x05),
                tok(b"\x1e", "ctl", 0x1E),
                text("B"),
                tok(b"\x04", "ctl", 0x04),
                text("い"),
                tok(b"\x00", "end", 0x00),
            ]
        )
        self.assertEqual(ps1_reuse.stream_pages(st), (["A", "B"], ["あ", "い"]))
        self.assertFalse(ps1_reuse.name_changes_midpage(st))
        got = ps1_reuse.ours_for(st, ["가", "나"], ["갑", "을"])
        self.assertEqual(got, "<1e>갑<04>가\f<1e>을<04>나<00>")

    def test_name_change_without_page_break_is_flagged(self):
        st = self._stream(
            [
                text("あ"),
                tok(b"\x1e", "ctl", 0x1E),
                text("B"),
                tok(b"\x04", "ctl", 0x04),
                text("い"),
                tok(b"\x00", "end", 0x00),
            ]
        )
        self.assertTrue(ps1_reuse.name_changes_midpage(st))


if __name__ == "__main__":
    unittest.main()
