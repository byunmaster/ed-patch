"""레벨업 창의 이름 폭 표 — 구운 이름 글자 수로 다시 쓰고, 원본이 다르면 선다(`build.fit_name_widths`)."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build

NAMES, WIDTHS, N = build.NAME_TABLE["ed3"]


def image(names):
    """이름 칸 14B(7워드, 글자 뒤 0·종결 0xFFFF) + 폭 표를 가진 빈 실행파일 — 폭은 글자 수."""
    exe = bytearray(WIDTHS + 2 * N + 16)
    for i, n in enumerate(names):
        w = [0x100 + k for k in range(n)] + [0] * (6 - n) + [0xFFFF]
        struct.pack_into("<7H", exe, NAMES + 14 * i, *w[:7])
        struct.pack_into("<H", exe, WIDTHS + 2 * i, n)
    return exe


class TestNameWidths(unittest.TestCase):
    def test_follows_baked_name_length(self):
        orig = image([4] * N)
        new = bytearray(orig)
        for i in range(N):  # 한글 이름이 세 글자로 줄었다
            struct.pack_into("<7H", new, NAMES + 14 * i, 0x200, 0x201, 0x202, 0, 0, 0, 0xFFFF)
        build.fit_name_widths(new, bytes(orig), "ed3", {})
        self.assertEqual(list(struct.unpack_from(f"<{N}H", new, WIDTHS)), [3] * N)

    def test_stops_when_original_width_is_not_name_length(self):
        orig = image([4] * N)
        struct.pack_into("<H", orig, WIDTHS, 9)
        with self.assertRaises(AssertionError):
            build.fit_name_widths(bytearray(orig), bytes(orig), "ed3", {})


if __name__ == "__main__":
    unittest.main()
