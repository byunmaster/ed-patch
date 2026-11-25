"""PCE I 오프닝 자막 — 낱말 사이 공백은 반각(4px)이고 줄 폭·줄바꿈 계산도 그 폭을 쓴다(공통 규칙 1-6, 11-06)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import opening_sub as O


class OpeningSpaceTest(unittest.TestCase):
    def test_space_is_half(self):
        self.assertEqual(O._adv(" "), 4)
        self.assertEqual(O._adv("가"), O.CELL)
        self.assertEqual(O._adv("a"), O.ADV_LATIN)  # 라틴 글자는 그대로 8px

    def test_line_width_uses_space(self):
        a = sum(O._advs("가 나"))
        self.assertEqual(a, O.CELL * 2 + 4)

    def test_wrap_keeps_legacy_space_for_line_breaks(self):
        # 줄 나눔은 종전 공백 폭(8px)으로 잰다 — 4px 로 재면 한 줄로 합쳐져 하단 자막 y 표가 넘친다(씬 쪽 7)
        w8 = sum(O._advs("가나")) + 8 + sum(O._advs("다라"))
        self.assertEqual(O.wrap("가나 다라", max_w=w8), ["가나 다라"])
        self.assertEqual(O.wrap("가나 다라", max_w=w8 - 1), ["가나", "다라"])
        self.assertEqual(O._adv(" "), 4)  # wrap 이 끝나면 그리는 폭으로 돌아온다


if __name__ == "__main__":
    unittest.main()
