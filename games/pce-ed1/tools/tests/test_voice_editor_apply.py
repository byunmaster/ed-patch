"""편집기 편집값 → voice_timing (열림, 닫힘) 쌍 — 원본 없이 도는 순수 계산만."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import voice_editor_apply as A
except Exception as e:  # 원본이 없는 트리에서는 import 단계에서 못 읽는 모듈이 있다
    A = None
    _why = str(e)


def row(idx, t0, t1, tpage, tkey="scn009@0x9", tbase=0.0):
    return {
        "clip": "scn009_g0",
        "idx": idx,
        "scene": 9,
        "key": "k",
        "page": idx,
        "kr": "",
        "t_start": t0,
        "t_end": t1,
        "tkey": tkey,
        "tpage": tpage,
        "tbase": tbase,
    }


@unittest.skipIf(A is None, "voice_editor_apply 를 못 읽는다")
class TimingItems(unittest.TestCase):
    def setUp(self):
        self.base = {
            ("scn009_g0", i): row(i, a, b, i - 1)
            for i, (a, b) in enumerate([(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)], 1)
        }

    def edited(self):
        return [dict(r) for r in self.base.values()]

    def test_close_only_edit_stays_a_plain_list(self):
        out = A.timing_items(self.edited(), self.base)
        self.assertEqual(out, {})  # 안 바꿨으면 쓰지 않는다
        rows = self.edited()
        rows[1]["t_end"] = 9.0
        rows[2]["t_start"] = 9.0
        self.assertEqual(
            A.timing_items(rows, self.base), {"scn009@0x9": [4.0, 9.0, 12.0]}
        )  # 열림 = 앞 닫힘(간격 0) → 닫힘만

    def test_gap_over_tolerance_becomes_a_pair(self):
        rows = self.edited()
        rows[2]["t_start"] = 10.0
        out = A.timing_items(rows, self.base)["scn009@0x9"]
        self.assertEqual(out, [[None, 4.0], [None, 8.0], [10.0, 12.0]])

    def test_first_page_lead_is_relative_to_the_gate_base(self):
        rows = self.edited()
        rows[0]["t_start"] = 3.0
        out = A.timing_items(
            [dict(r, tbase=1.0) for r in rows],
            {k: dict(b, tbase=1.0) for k, b in self.base.items()},
        )["scn009@0x9"]
        self.assertEqual(out[0], [2.0, 3.0])  # (3.0-1.0, 4.0-1.0)

    def test_merge_docs_overlays_ts_te_on_base_rows(self):
        rows = A.merge_docs([{"clip": "scn009_g0", "idx": 2, "ts": 4.5, "te": 7.5}], self.base)
        r = next(x for x in rows if x["idx"] == 2)
        self.assertEqual((r["t_start"], r["t_end"]), (4.5, 7.5))


@unittest.skipIf(A is None, "voice_editor_apply 를 못 읽는다")
class RowPos(unittest.TestCase):
    """편집기 행의 창 위치(`pos`)가 시각표 기본값(토막 `pos`)을 이긴다 — 항목 `pos` 꼴은 `gwin_rt.msg_top` 이 읽는 꼴."""

    def test_row_pos_beats_segment_default(self):
        seg, it = {"pos": "top"}, {"key": "k"}
        self.assertEqual(A.set_pos(seg, it, 0, "top"), 0)  # 기본값과 같으면 안 적는다
        self.assertNotIn("pos", it)
        self.assertEqual(A.set_pos(seg, it, 0, "bottom"), 1)
        self.assertEqual(it["pos"], "bottom")
        self.assertEqual(A.set_pos(seg, it, 0, "top"), 1)  # 되돌리면 지운다
        self.assertNotIn("pos", it)

    def test_per_page_list_and_no_leak_to_later_pages(self):
        seg, it = {}, {"key": "k"}
        self.assertEqual(A.set_pos(seg, it, 1, "top", npg=4), 1)  # 넷 중 둘째 쪽만 위 — 뒤쪽이 물려받지 않는다
        self.assertEqual(it["pos"], ["bottom", "top", "bottom"])
        self.assertEqual(A.set_pos(seg, it, 2, "top", npg=4) + A.set_pos(seg, it, 3, "top", npg=4), 2)
        self.assertEqual(it["pos"], ["bottom", "top"])  # 같은 값으로 끝나는 꼬리는 줄인다
        self.assertEqual(A.set_pos(seg, it, 0, "top", npg=4), 1)
        self.assertEqual(it["pos"], "top")  # 전 쪽이 같으면 문자열

    def test_bad_or_missing_value_is_ignored(self):
        seg, it = {}, {"key": "k"}
        self.assertEqual(A.set_pos(seg, it, 0, None) + A.set_pos(seg, it, 0, "middle"), 0)
        self.assertNotIn("pos", it)

    def test_item_pos_reads_back_per_page(self):
        import gwin_rt as R

        seg, it = {"pos": "top"}, {"key": "k"}
        A.set_pos(seg, it, 1, "bottom", npg=3)
        self.assertEqual([R.msg_top(seg, it, i) for i in range(3)], [True, False, True])
        self.assertEqual([R.msg_top({}, {"key": "k", "pos": ["bottom", "top"]}, i) for i in range(4)], [False, True, True, True])  # 모자란 뒤쪽은 마지막 값
        with self.assertRaises(R.GwinError):
            R.msg_top({}, {"key": "k", "pos": "middle"}, 0)


if __name__ == "__main__":
    unittest.main()
