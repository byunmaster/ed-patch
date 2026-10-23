"""조각 펴기(`stream_join`) — 흐름 모양: call 은 끼우고 goto 는 넘기고 조건 꼬리는 갈래 둘."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stream_join as S


def run(table, off=0):
    return S.paths(lambda o: table.get(o), off)


class StreamJoin(unittest.TestCase):
    def test_call_inserts_and_returns(self):
        t = {0: [("t", "가"), ("call", 1), ("t", "다"), ("end",)], 1: [("t", "나"), ("end",)]}
        self.assertEqual(run(t), ["가나다"])

    def test_goto_is_tail(self):
        t = {0: [("t", "가"), ("goto", 1, False), ("t", "버림")], 1: [("t", "나"), ("end",)]}
        self.assertEqual(run(t), ["가나"])

    def test_cond_tail_is_two_paths_not_concat(self):
        t = {0: [("t", "가"), ("goto", 1, True), ("t", "다"), ("end",)], 1: [("t", "나"), ("end",)]}
        self.assertEqual(run(t), ["가나", "가다"])

    def test_missing_piece_is_none_path(self):
        t = {0: [("t", "가"), ("call", 9), ("end",)]}
        self.assertEqual(run(t), [None])

    def test_loop_does_not_hang(self):
        t = {0: [("t", "가"), ("goto", 0, False)]}
        self.assertEqual(run(t), [None])

    def test_kr_items_parse_tail_and_end(self):
        it = S.kr_items("가<10:0b5c>나<f27>")
        self.assertEqual(it[1], ("call", 0xB5C))
        it = S.kr_items("가<120068><0f:056a>")
        self.assertEqual(it[-1], ("goto", 0x56A, True))
        it = S.kr_items("가<f827><84>?<0f:0be0>")
        self.assertEqual(it[-1], ("goto", 0xBE0, True))
        self.assertEqual(S.kr_items("가<06>")[-1], ("end",))


if __name__ == "__main__":
    unittest.main()
