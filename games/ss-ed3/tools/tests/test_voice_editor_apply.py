"""편집기 반영 — 얼굴 불가 장면 거부 · 캐시 한도 · 기본값 되돌림 · wait 재계산 (원본 없이 돈다)."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import voice_editor_apply as A

DOC = {
    "V03": {
        "clock": {"off": 1, "len": 6, "preload": {"off": 0, "len": 6, "wait": 54}},
        "hooks": [],
        "items": [
            {"t": 0.0, "who": "가", "speaker": 0, "lines": ["하나"], "dur": 1.0},
            {"t": 2.0, "who": "나", "speaker": 1, "lines": ["둘"], "dur": 1.0},
        ],
    },
    "V02": {
        "clock": {"off": 1, "len": 6},
        "hooks": [],
        "items": [{"t": 0.0, "who": "가", "speaker": 0, "lines": ["하나"], "dur": 1.0}],
    },
}


class Apply(unittest.TestCase):
    def test_no_face_scene_rejects_face(self):
        with self.assertRaises(SystemExit):
            A.apply(copy.deepcopy(DOC), [{"scene": "V02", "idx": 1, "face": 1}])

    def test_text_edit_allowed_without_preload(self):
        d = copy.deepcopy(DOC)
        n, _ = A.apply(d, [{"scene": "V02", "idx": 1, "kr": "수정\n두 줄"}])
        self.assertEqual((n, d["V02"]["items"][0]["lines"]), (1, ["수정", "두 줄"]))

    def test_pos_top_then_back_to_bottom(self):
        d = copy.deepcopy(DOC)
        n, _ = A.apply(
            d, [{"scene": "V02", "idx": 1, "pos": "top"}]
        )  # 미리 싣기 없는 장면도 위치는 된다
        self.assertEqual((n, d["V02"]["items"][0]["pos"]), (1, "top"))
        n, _ = A.apply(d, [{"scene": "V02", "idx": 1, "pos": "bottom"}])
        self.assertEqual((n, "pos" in d["V02"]["items"][0]), (1, False))

    def test_expr_only_edit_keeps_speaker_face(self):
        # 표정만 바꾼 편집을 「얼굴 기본값으로 되돌림」으로 읽으면 표정이 통째로 버려진다(10-20 실측: 71건)
        d = copy.deepcopy(DOC)
        n, _ = A.apply(d, [{"scene": "V03", "idx": 2, "expr": 8}])
        it = d["V03"]["items"][1]
        self.assertEqual((n, it["face"], it["expr"]), (1, 1, 8))

    def test_expr_only_edit_skipped_without_preload(self):
        d = copy.deepcopy(DOC)
        n, notes = A.apply(d, [{"scene": "V02", "idx": 1, "expr": 8}])
        self.assertEqual((n, "face" in d["V02"]["items"][0], bool(notes)), (0, False, True))

    def test_pos_rejects_unknown(self):
        with self.assertRaises(SystemExit):
            A.apply(copy.deepcopy(DOC), [{"scene": "V03", "idx": 1, "pos": "middle"}])

    def test_default_roundtrip_changes_nothing(self):
        d = copy.deepcopy(DOC)
        n, _ = A.apply(d, [{"scene": "V03", "idx": 1, "face": "default"}])
        self.assertEqual(n, 0)

    def test_wait_recounted(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [{"scene": "V03", "idx": 1, "face": 2}])
        self.assertEqual(d["V03"]["clock"]["preload"]["wait"], 12 * 2 + 30)

    def test_cache_limit(self):
        d = copy.deepcopy(DOC)
        d["V03"]["items"] = [
            {"t": float(i), "who": "x", "speaker": 0, "lines": ["a"], "dur": 1.0} for i in range(9)
        ]
        with self.assertRaises(SystemExit):
            A.apply(d, [{"scene": "V03", "idx": i + 1, "face": i} for i in range(9)])

    def test_bad_inputs(self):
        for e in (
            {"scene": "V03", "idx": 9},
            {"scene": "V03", "idx": 1, "kr": "a\n"},
            {"scene": "V03", "idx": 1, "face": 99},
        ):
            with self.assertRaises(SystemExit):
                A.apply(copy.deepcopy(DOC), [e])


class Adds(unittest.TestCase):
    ADD = {"aid": "a1", "scene": "V03", "kr": "새 줄\n둘째", "ts": 1.0, "te": 1.8, "spk_id": 1, "spk_name": "나", "face": None}

    def test_inserted_in_time_order(self):
        d = copy.deepcopy(DOC)
        n, _ = A.apply(d, [], [self.ADD])
        self.assertEqual(n, 1)
        it = d["V03"]["items"]
        self.assertEqual([x["t"] for x in it], [0.0, 1.0, 2.0])
        self.assertEqual((it[1]["lines"], it[1]["dur"], it[1]["speaker"]), (["새 줄", "둘째"], 0.8, 1))

    def test_edit_on_added_row_overlays(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [{"scene": "V03", "idx": "a1", "kr": "고침", "pos": "top", "te": 2.5}], [self.ADD])
        x = d["V03"]["items"][1]
        self.assertEqual((x["lines"], x["pos"], x["dur"]), (["고침"], "top", 1.5))

    def test_existing_idx_unshifted_by_add(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [{"scene": "V03", "idx": 2, "kr": "둘째 고침"}], [self.ADD])
        self.assertEqual([x["lines"][0] for x in d["V03"]["items"]], ["하나", "새 줄", "둘째 고침"])

    def test_empty_text_add_is_skipped_with_note(self):
        d = copy.deepcopy(DOC)
        n, notes = A.apply(d, [], [{**self.ADD, "kr": ""}])
        self.assertEqual(n, 0)
        self.assertTrue(any("받아쓰기 필요" in x for x in notes))

    def test_rejects_hooks_scene_and_faceless(self):
        for bad in (
            {**self.ADD, "scene": "V01"},
            {**self.ADD, "scene": "V02", "face": 1},
            {**self.ADD, "te": 0.5},
        ):
            with self.assertRaises(SystemExit):
                A.apply(copy.deepcopy(DOC), [], [bad])

    def test_remove_line_by_comment(self):
        d = copy.deepcopy(DOC)
        before = len(d["V03"]["items"])
        n, notes = A.apply(d, [{"scene": "V03", "idx": 1, "kr": "", "comment": "제거"}])
        self.assertEqual(len(d["V03"]["items"]), before - 1)
        self.assertTrue(any("지웠다" in x for x in notes))

    def test_empty_text_without_remove_comment_still_rejected(self):
        with self.assertRaises(SystemExit):
            A.apply(copy.deepcopy(DOC), [{"scene": "V03", "idx": 1, "kr": ""}])

    def test_face_on_add_recounts_wait(self):
        d = copy.deepcopy(DOC)
        A.apply(d, [], [{**self.ADD, "face": 2}])  # 얼굴 0·1 에 2 가 더해져 3 종
        self.assertEqual(d["V03"]["clock"]["preload"]["wait"], 20 * 3 + 10)


if __name__ == "__main__":
    unittest.main()
