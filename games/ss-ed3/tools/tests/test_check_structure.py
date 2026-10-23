"""구조 대조 — 10-22 사고 꼴(종결 뒤 `FF FF` 끼움)을 가짜 바이트로 만들어 검사가 우는지 (원본 없이 돈다)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_structure as S
import mapfile as M


def _sjis(s):
    return s.encode("cp932")


def _map(text_a, tail, text_b=b""):
    """가짜 맵 — 헤더(매직 + 포인터표 + 맵 이름) 뒤에 대사 둘. 글은 가짜 문장이다."""
    h = bytearray(M.NAME_OFF)
    h[: len(M.MAGIC)] = M.MAGIC
    name = _sjis("あいうえお") + b"\x00" * 24
    return bytes(h) + name + b"\xff\x00" + text_a + tail + b"\xff\x00" + text_b + b"\x10\x00\x09\x00\x00"


TAIL = b"\x10\x00\xff\x02\x00\x00\xff\x07"
A = _sjis("かきくけこさしすせそ")  # 20B


class Structure(unittest.TestCase):
    def check(self, built):
        orig = _map(A, TAIL, _sjis("たちつてと"))
        self.assertEqual(len(orig), len(built))
        return S.compare_map("MAPT", orig, built, {})[0]

    def test_same_controls_pass(self):
        # 글 바이트만 다른 번역 — 제어 열은 같다
        built = _map(_sjis("なにぬねのはひふへほ"), TAIL, _sjis("まみむめも"))
        self.assertEqual(self.check(built), [])

    def test_ff_ff_after_terminator_fails(self):
        # 🔴 사고 꼴 — 글이 짧아지고 종결 뒤에 `FF FF` 가 끼며 다음 화자 전환(`FF 02`) 앞이 달라진다
        short = _sjis("なにぬねの")  # 10B
        built = _map(short + b"\x10\x00" + b"\xff\xff" * 4, b"\xff\xff" + TAIL[2:], _sjis("まみむめも"))
        self.assertTrue(self.check(built))

    def test_one_a_fill_is_allowed_kind(self):
        built = _map(_sjis("なにぬねの") + b"\x1a" * 10, TAIL, _sjis("まみむめも"))
        self.assertEqual(self.check(built), [])

    def test_inject_token_must_match(self):
        orig_a = _sjis("かきくけこ") + b"\x01\x07" + _sjis("さしす") + b"\x00"
        orig = _map(orig_a, TAIL, _sjis("たちつてと"))
        built = _map(_sjis("なにぬねの") + b"\x01\x08" + _sjis("はひふ") + b"\x00", TAIL, _sjis("まみむめも"))
        self.assertTrue(S.compare_map("MAPT", orig, built, {})[0])


if __name__ == "__main__":
    unittest.main()
