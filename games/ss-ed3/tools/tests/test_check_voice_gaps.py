import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_voice_gaps as G


def doc(*items):
    return {"V02": {"items": [dict(t=t, dur=d, lines=["가"]) for t, d in items]}}


class Gaps(unittest.TestCase):
    def test_small_gap_flagged(self):
        self.assertEqual([g[:2] for g in G.gaps(doc((0, 1.0), (1.3, 1.0)))], [("V02", 1)])

    def test_joined_and_wide_gap_ok(self):
        self.assertEqual(G.gaps(doc((0, 1.0), (1.0, 1.0), (2.0, 1.0), (4.0, 1.0))), [])

    def test_boundary_half_second_ok(self):
        self.assertEqual(G.gaps(doc((0, 1.0), (1.5, 1.0))), [])

    def test_allow_list(self):
        self.assertEqual(G.gaps(doc((0, 1.0), (1.3, 1.0)), {"V02": [1]}), [])

    def test_same_pos_overlap_flagged_other_pos_listed(self):
        d = doc((0, 2.0), (1.5, 1.0))
        self.assertEqual(len(G.gaps(d)), 1)
        d["V02"]["items"][1]["pos"] = "top"
        other = []
        self.assertEqual(G.gaps(d, None, other), [])
        self.assertEqual(len(other), 1)

    def test_hook_scene_reads_t_string(self):
        d = {"V17": {"hooks": [{"preload": True}, {"_t": "2.0초", "dur": 1.0, "lines": ["가"]}, {"_t": "3.2초", "dur": 1.0, "lines": ["나"]}]}}
        self.assertEqual(len(G.gaps(d)), 1)


if __name__ == "__main__":
    unittest.main()
