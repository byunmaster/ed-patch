"""전투 「나타났다」 줄 — 원판이 첫 이름을 색(`16`)으로 칠한 줄은 색 제어를 그대로 낸다(4-6)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle


class Tab:
    def enc(self, s: str) -> bytes:
        return s.encode("utf-8")


class AppearColor(unittest.TestCase):
    def test_colored_name_keeps_start_and_name_buffer(self):
        raw = bytes.fromhex("160edab2bcb11a0f618cbbdac013")  # {16}{0E}레이시아{name}{0F}가 나타났다 ⏎
        out = battle._appear(raw, Tab(), set())
        self.assertTrue(out.startswith(b"\x16" + "레이시아".encode() + b"\x1a"))
        self.assertTrue(out.endswith(b"\x13"))
        self.assertNotIn(b"\x0e", out)

    def test_plain_line_unchanged(self):
        # 색 시작이 없는 줄(앞 제어가 말 속도뿐)은 종전대로 글만 바뀐다
        raw = bytes.fromhex("0edab2bcb11a0f618cbbdac013")
        out = battle._appear(raw, Tab(), set())
        self.assertNotIn(b"\x16", out)


if __name__ == "__main__":
    unittest.main()
