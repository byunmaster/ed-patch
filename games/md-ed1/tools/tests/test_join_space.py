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
        t = texts("내 힘으로 <01>가자<00>", [tok(b"\x01", "ctl", 1), tok(b"\x00", "end", 0)])
        self.assertEqual(t[0], "내 힘으로".encode())


if __name__ == "__main__":
    unittest.main()
