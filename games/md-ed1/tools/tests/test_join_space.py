"""build_stream — 이음새 공백(조각 끝 공백 복원 · 문장 끝 부호 뒤 이음 · 줄바꿈 앞은 안 남김)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import scene


def tok(raw, kind, code):
    return scene.Token(0, raw, kind, code)


class Cs:
    def encode(self, s):
        return s.encode("utf-8")


def texts(ours, tail):
    st = scene.Stream.__new__(scene.Stream)
    st.tokens = tail
    st.start = 0
    out = build.build_stream(st, ours, Cs())
    return [t.raw for t in out if t.kind == "text"]


class JoinSpace(unittest.TestCase):
    def test_sentence_end_before_return_end_gets_space(self):
        """`으음.<06>` — 되돌림 끝 뒤에 다음 조각이 이어 찍힌다."""
        t = texts("으음.<06>", [tok(b"\x06", "end", 6)])
        self.assertEqual(t, ["으음. ".encode()])

    def test_sentence_end_before_final_end_has_no_space(self):
        t = texts("끝이다.<00>", [tok(b"\x00", "end", 0)])
        self.assertEqual(t, ["끝이다.".encode()])

    def test_space_before_newline_is_dropped(self):
        t = texts("내 힘으로 간다. <01>가자<00>", [tok(b"\x01", "ctl", 1), tok(b"\x00", "end", 0)])
        self.assertEqual(t[0], t[0].rstrip())  # 줄바꿈 앞 공백은 안 남는다
        self.assertNotIn(b"  ", b"".join(t))


class DeadSeamSpace(unittest.TestCase):
    """`strip_dead_seam_space` — 뒤에 이어질 글이 없는 이음새 공백만 지운다(10-30 전수 촬영 줄끝 공백)."""

    def _run(self, toks):
        out = list(toks)
        build.strip_dead_seam_space(out)
        return [t.raw for t in out if t.kind == "text"]

    def test_space_before_sound_then_newline_is_dropped(self):
        t = self._run([tok(b"ab ", "text", -1), tok(b"\x0c\x01\x01", "ctl", 0x0C), tok(b"\x01", "ctl", 1)])
        self.assertEqual(t, [b"ab"])

    def test_space_before_return_end_is_kept(self):
        t = self._run([tok(b"ab ", "text", -1), tok(b"\x06", "end", 6)])
        self.assertEqual(t, [b"ab "])

    def test_space_before_text_is_kept(self):
        t = self._run([tok(b"ab ", "text", -1), tok(b"\x0c\x01\x01", "ctl", 0x0C), tok(b"cd", "text", -1)])
        self.assertEqual(t, [b"ab ", b"cd"])


class LetterBearing(unittest.TestCase):
    """몬스터 접미 A~D 글리프는 1~5열 안(양옆 여백 1열) — 앞 한글과 붙어 겹쳐 보이던 것(10-30 007)."""

    def test_ink_inside_columns_1_to_5(self):
        import hangul

        for c, rows in hangul.BEARING_R1.items():
            self.assertEqual(len(rows), 14, hex(c))
            for r in rows:
                self.assertEqual(len(r), 8)
                self.assertEqual(r[0] + r[6:], "." + "..", (hex(c), r))  # 0·6·7열은 비어야


if __name__ == "__main__":
    unittest.main()
