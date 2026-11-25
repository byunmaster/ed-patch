"""문자열 칸 안쪽에 박힌 코드가 읽는 데이터 표(`layout.PINNED_DATA`)는 비우지도·덮지도 않는다 — 11-07 퀵메뉴(SELECT)의 워프의 날개·횃불이 안 됐다
(뱅크 0x6A `+0x258` 문자열 칸 안의 사용 가능 표 `$625D,X` 의 `01` 넷이 옮긴 문자열 자리에 새 글로 덮였다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout


PIN = [(0x6A, 0x25E, 1, "시험"), (0x6A, 0x26A, 1, "시험"), (0x6A, 0x283, 7, "시험")]


def fake_prog():
    orig = bytearray(b"\xff" * (layout.NBANKS * layout.BANK))
    for b, o, n, _l in layout.PINNED_DATA:
        s = (b - layout.BANK0) * layout.BANK + o
        orig[s : s + n] = b"\x01" * n
    for b, o, n in layout.ZERO_PADDING:
        z = (b - layout.BANK0) * layout.BANK + o
        orig[z : z + n] = bytes(n)
    return layout.Prog(orig=bytes(orig))


class PinnedData(unittest.TestCase):
    def setUp(self):
        self._old = layout.PINNED_DATA
        layout.PINNED_DATA = PIN

    def tearDown(self):
        layout.PINNED_DATA = self._old

    def test_vacate_keeps_pinned(self):
        p = fake_prog()
        p.vacate(0x6A, 0x258, 0x30)  # 옛 문자열 칸 — 안쪽에 표 바이트 넷
        free = [r for r in p.free_runs.get(0x6A, [])]
        for b, o, n, lab in layout.PINNED_DATA:
            if b == 0x6A:
                for r in free:
                    self.assertFalse(r[0] < o + n and o < r[1], f"{lab} 이 자유 공간에 들어갔다")
        self.assertTrue(
            all(not (o2 <= 0x25E < o2 + n2) for b, o2, n2 in p.vacated if b == 0x6A),
            "표 바이트가 0xFF 로 비워진다",
        )

    def test_put_rejects_overwrite(self):
        p = fake_prog()
        with self.assertRaises(ValueError):
            p.put(0x6A, 0x257, b"\x01\x02\x03\x04\x05\x06\x07\x08", "시험")

    def test_put_same_bytes_ok(self):
        p = fake_prog()
        p.put(0x6A, 0x25E, b"\x01", "시험")


if __name__ == "__main__":
    unittest.main()
