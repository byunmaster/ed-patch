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


class JumpTargets(unittest.TestCase):
    """pce-ed1 10-22 꼴 — 남의 점프가 들어오는 종료 바이트를 우리 스텁이 덮으면 울어야 한다."""

    def maps(self):
        pad = b"\x00" * 40
        body = b"\x41" * 8 + b"\x00" + b"\x41" * 8  # 종료 00 이 오프셋 8 + base
        base = M.NAME_OFF + 64
        orig = bytearray(base) + body + pad
        orig[:4] = b"\x00\x00\x00\x00"
        end = base + 8
        j = base + 30
        orig[j : j + 6] = b"\xfd\x00" + (S.BASE + end).to_bytes(4, "big")
        return orig, end

    def test_catches_overwritten_target(self):
        orig, end = self.maps()
        built = bytearray(orig)
        built[end : end + 6] = b"\xfd\x00\x00\x30\x00\x00"  # 스텁 주소가 종료 바이트를 덮었다
        # 목표가 트램펄린 시작이 아니면(놓은 p 가 아니다) 운다 — 여기서는 tramps 를 비워 호출한다
        self.assertTrue(S.target_damage(orig, built, []))

    def test_clean_build_passes(self):
        orig, _ = self.maps()
        self.assertEqual(S.target_damage(orig, bytearray(orig), []), [])
