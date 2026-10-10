"""필드 square 창 가운데 정렬(`build.square_center`) — 줄마다 앞 여백이 마스터 규칙대로(6.5 · 1.5 · 1 · 1.5칸)이고 덩어리 안에 든다."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build

OFF, N = build.SQUARE["ed3"]
SP = 0x77


def enc(t):
    return [SP] if t == " " else [0x100 + ord(c) % 0x80 for c in t]


def orig_image():
    exe = bytearray(OFF + 2 * (N + 1) + 8)
    words = [1] * 7 + [0x8000] + [1] * 7 + [0x8000] + [1] * 7 + [0x8000] + [0, 1, 1, 1, 1, 0x8002]
    struct.pack_into(f"<{len(words)}H", exe, OFF, *words)
    return exe


class TestSquareCenter(unittest.TestCase):
    def test_lines_are_centered_in_halves(self):
        orig = orig_image()
        exe = bytearray(orig)
        build.square_center(exe, bytes(orig), "ed3", enc, {})
        w = list(struct.unpack_from(f"<{N}H", exe, OFF))
        lines, cur = [], []
        for x in w:
            cur.append(x)
            if x >= 0x8000:
                lines.append(cur)
                cur = []
                if x == 0x8002:
                    break

        def width(line):  # 칸 수 — 0 코드 1칸 · 반 칸 공백 0.5 · 글자 1
            return sum(1 if x == 0 or 0x100 <= x < 0x8000 else 0.5 for x in line if x < 0x8000)

        self.assertEqual([width(ln) for ln in lines], [5, 6, 5.5, 5])  # 상태보기·퇴각하기 앞 1(+4글자) · 자동전투선택 6 · 키설정변경 앞 반 칸 + 5
        self.assertEqual(struct.unpack_from("<H", exe, OFF + 2 * N)[0], struct.unpack_from("<H", orig, OFF + 2 * N)[0])  # 30번째 워드는 건드리지 않는다
        for ln in lines:
            self.assertLessEqual(len([x for x in ln if x < 0x8000]), 6)  # 글자 수가 열을 넘으면 줄이 접힌다

    def test_stops_on_foreign_layout(self):
        orig = bytearray(orig_image())
        struct.pack_into("<H", orig, OFF, 0x8000)
        with self.assertRaises(AssertionError):
            build.square_center(bytearray(orig), bytes(orig), "ed3", enc, {})


if __name__ == "__main__":
    unittest.main()


class TestYesNoCenter(unittest.TestCase):
    def test_first_line_blank_yes_blank(self):
        off = build.YESNO["ed3"]
        orig = bytearray(off + 16)
        struct.pack_into("<4H", orig, off, 0x6D, 0, 0x42, 0x8000)
        exe = bytearray(orig)
        build.yesno_center(exe, bytes(orig), "ed3", lambda t: [0x274], {})
        self.assertEqual(list(struct.unpack_from("<4H", exe, off)), [0, 0x274, 0, 0x8000])

    def test_stops_on_foreign_layout(self):
        off = build.YESNO["ed3"]
        orig = bytearray(off + 16)
        with self.assertRaises(AssertionError):
            build.yesno_center(bytearray(orig), bytes(orig), "ed3", lambda t: [1], {})
