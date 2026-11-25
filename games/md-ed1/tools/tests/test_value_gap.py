"""값 이음 줄 공백 검사가 **실제로 우는가** — 옛 「민첩성이 1내려갔다」 꼴(꼬리 조각이 값에 붙음)을 가짜로 넣는다(마스터 10-22)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_value_gap as g


def run(ours: str):
    return g.check([("battlej:test", "", ours, "dialog")])[1]


class ValueGap(unittest.TestCase):
    def test_canon_shape_passes(self):
        self.assertEqual(run("{name}의 민첩성이 {n} 내려갔다!!"), [])

    def test_tail_glued_to_value_is_caught(self):
        self.assertTrue(run("{name}의 민첩성이 {n}내려갔다!!"))

    def test_missing_space_before_value_is_caught(self):
        self.assertTrue(run("{name}에게{n}의 피해!!"))

    def test_point_tail_has_no_space_in_canon(self):
        self.assertEqual(run("{name}의 눈에 들어가고 말았다!!\n민첩성이 {n}포인트 내려갔다!!"), [])
        self.assertTrue(run("{name}의 눈에 들어가고 말았다!!\n민첩성이 {n} 포인트 내려갔다!!"))


class SlotGlue(unittest.TestCase):
    """변수 칸 앞 공백 — pce-ed1 10-30 「상자에는{아이템}이」 부류."""

    @staticmethod
    def glue(ours: str):
        return g.check_glue([("scene:test", "", ours, "dialog")])[1]

    def test_space_before_slot_passes(self):
        self.assertEqual(self.glue("상자에는 <0e>이 들어 있었다."), [])
        self.assertEqual(self.glue("<0b>는 <0e>를 얻었다."), [])

    def test_glued_slot_is_caught(self):
        self.assertTrue(self.glue("상자에는<0e>이 들어 있었다."))
        self.assertTrue(self.glue("보물{name}을 얻었다."))

    def test_josa_after_slot_and_opening_quote_pass(self):
        self.assertEqual(self.glue("<02>의 주문"), [])
        self.assertEqual(self.glue("이름은 「<02>」다."), [])


if __name__ == "__main__":
    unittest.main()
