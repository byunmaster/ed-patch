"""영상 자막 편집기 반영 — 문안·시각·추가·확정 시각 이동·거부 (원본 없이 돈다)."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import movie_editor_apply as A

DOC = {
    "_fixed": {"M01": [5.0]},
    "M01": [[1.0, 3.0, "하나"], [5.0, 7.0, "둘"], [9.0, 11.0, "셋"]],
    "M02": [],
}
ADD = {"aid": "a1", "scene": "M01", "kr": "새 줄\n둘째", "ts": 3.5, "te": 4.5}


class Apply(unittest.TestCase):
    def test_text_and_time(self):
        d = copy.deepcopy(DOC)
        n, _ = A.apply(d, [{"scene": "M01", "idx": 1, "kr": "고침", "te": 3.4}])
        self.assertEqual((n, d["M01"][0]), (1, [1.0, 3.4, "고침"]))

    def test_no_change_counts_zero(self):
        d = copy.deepcopy(DOC)
        self.assertEqual(A.apply(d, [{"scene": "M01", "idx": 2, "ts": 5.0, "kr": "둘"}])[0], 0)

    def test_fixed_follows_start(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [{"scene": "M01", "idx": 2, "ts": 5.4}])
        self.assertEqual(d["_fixed"]["M01"], [5.4])

    def test_add_in_order_and_idx_unshifted(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [{"scene": "M01", "idx": 3, "kr": "셋 고침"}], [ADD])
        self.assertEqual([r[2] for r in d["M01"]], ["하나", "새 줄\n둘째", "둘", "셋 고침"])

    def test_edit_on_added_overlays(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [{"scene": "M01", "idx": "a1", "kr": "고침", "te": 4.0}], [ADD])
        self.assertEqual(d["M01"][1], [3.5, 4.0, "고침"])

    def test_trailing_newline_is_stripped(self):
        self.assertEqual(A._text("M18", "#14", "한 줄\n"), "한 줄")
        self.assertEqual(A._text("M18", "#14", " 가 \n 나 "), "가\n나")
        with self.assertRaises(SystemExit):
            A._text("M18", "#14", "가\n\n나")

    def test_rejects(self):
        for edits, adds in (
            ([{"scene": "M01", "idx": 9}], []),
            ([{"scene": "M01", "idx": 1, "kr": "a\n\nb"}], []),
            ([{"scene": "M01", "idx": 1, "te": 0.5}], []),
            ([{"scene": "M09", "idx": 1}], []),
            ([], [{**ADD, "kr": ""}]),
            ([], [{**ADD, "scene": "M02"}]),
            ([], [{**ADD, "te": 3.0}]),
        ):
            with self.assertRaises(SystemExit):
                A.apply(copy.deepcopy(DOC), edits, adds)


if __name__ == "__main__":
    unittest.main()
