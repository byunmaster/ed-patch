"""check_typeset_rom 양성 대조 — 축마다 일부러 깨뜨린 칸이 걸리는지, 정상·원판 동일은 안 걸리는지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_typeset_rom as C


def row(kr: str, jp: str = "あ") -> str:
    return f"C20000\t{jp}\t{kr}\t"


def hit(kr: str, jp: str = "あ") -> set[str]:
    _, bad = C.scan([row(kr, jp)])
    return {k for k, v in bad.items() if v}


class T(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(hit("안녕하세요.↵반갑습니다.⏎또 만나요."), set())

    def test_axes(self):
        self.assertEqual(hit("안녕↵ 하세요."), {"A"})
        self.assertEqual(hit("안녕하세요↵, 반갑습니다."), {"B"})
        self.assertEqual(hit("안녕하세요.↵↵반갑습니다."), {"C"})
        self.assertEqual(hit("안녕하세요.반갑습니다."), {"D"})
        self.assertEqual(hit("여기 있는 사람을 만나↵을 때"), {"E"})
        self.assertEqual(hit("가" * 17), {"F"})
        self.assertIn("G1", hit("이것은 아주 길어서 다음 쪽으로 넘어가는 말이고⏎좋았다"))
        self.assertIn(
            "G2",
            hit(
                "이것은 아주 길어서 다음 쪽으로↵넘어가는 말이고 계속된다⏎다음 쪽 문장."[:0]
                + "문장이 아직 안 끝난 채로 계속되는 말이라서↵갑자기⏎다음 쪽입니다."
            ),
        )

    def test_same_as_original(self):
        self.assertEqual(hit("안녕↵ 하세요.", "あ↵ い"), set())


if __name__ == "__main__":
    unittest.main()
