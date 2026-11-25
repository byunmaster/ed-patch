"""음성 감사(voice_audit · voice_envelope) 단위 — 원문 없이 만든 가짜 문장·가짜 파형으로."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import voice_audit as A
import voice_editor_data as V
import voice_envelope as E


class ReadingTest(unittest.TestCase):
    def test_kana_fold(self):
        self.assertEqual(A.reading("アクダム！"), A.reading("あくだむ"))

    def test_robust_first_ignores_lone_hit(self):
        # 멀리 떨어진 우연한 한 글자(3.0)는 닻으로 안 삼는다
        self.assertEqual(A.robust_first([3.0, 20.0, 20.4, 20.9, 21.3]), 20.0)

    def test_hallucination(self):
        self.assertTrue(A.is_hallu("ご視聴ありがとうございました"))
        self.assertFalse(A.is_hallu("きょうはいい天気ですね"))


class MapPagesTest(unittest.TestCase):
    def rows(self, krs):
        return [{"kr": k} for k in krs]

    def test_one_to_one(self):
        self.assertEqual(A.map_pages(self.rows(["가나다", "라마바"]), ["あいう", "えおか"]), [(0, 1), (1, 2)])

    def test_split_page(self):
        m = A.map_pages(self.rows(["가나다라마바사아", "자차카타파하", "거너더러머버"]), ["あいうえおかきくけ" + "こさしすせそたちつてと", "なにぬねのはひふ" + "へほまみむめも"])
        self.assertEqual(len(m), 3)
        self.assertEqual(m[2][:2], (1, 2))


class EnvelopeTest(unittest.TestCase):
    def test_assign_follows_anchor(self):
        runs = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]
        res = E.assign(runs, [10, 10, 10, 10], [1.0, None, 5.0, None], GB=4, AS=1)
        self.assertAlmostEqual(res[0][0], 1.0)
        self.assertAlmostEqual(res[2][0], 5.0)
        self.assertTrue(res[1][0] < res[2][0])

    def test_runs_find_speech(self):
        db = np.full(1000, -50.0)
        db[200:400] = -20.0
        runs, _ = E.runs(db)
        self.assertEqual(len(runs), 1)
        self.assertAlmostEqual(runs[0][0], 2.0, delta=0.15)


class AnnotateTest(unittest.TestCase):
    def test_drop_keeps_idx(self):
        rows = [{"clip": "c", "key": "k", "page": p, "idx": p} for p in (1, 2, 3)]
        clips = [{"clip": "c", "rows": 3}]
        old = (V.AUDIT, V.AUDIT_MASTER)
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            V.AUDIT = Path(d) / "a.json"
            V.AUDIT_MASTER = Path(d) / "none.json"
            V.AUDIT.write_text(
                json.dumps({"rows": [{"clip": "c", "key": "k", "page": 2, "voice_match": "없음", "why": "x"}, {"clip": "c", "key": "k", "page": 3, "voice_match": "있음", "why": "y", "cand_start": 5.0, "cand_end": 7.0, "sync_conf": True}]}),
                "utf-8",
            )
            try:
                n = V.annotate_audit(rows, clips, {})
            finally:
                V.AUDIT, V.AUDIT_MASTER = old
        self.assertEqual(n, 1)
        self.assertEqual([r["idx"] for r in rows], [1, 3])  # 번호는 당기지 않는다
        self.assertEqual(rows[1]["t_start"], 5.0)
        self.assertEqual(clips[0]["dropped_idx"], [2])


class OnFlowAbsentTest(unittest.TestCase):
    """씬 41 시각표의 「없음」 쪽(voice_audit)이 비모달 자막 명세에서 빠진다 — 앞 쪽은 제 끝까지, 다음 쪽은 시각표의 자기 시작(앞 쪽 끝)에서 연다."""

    def test_scene41_drops_absent_page(self):
        import os

        import gwin_rt as G

        absent = G.audit_absent(41)
        if not absent:
            self.skipTest("씬 41 의 없음 쪽이 감사 결과에 없다")
        os.environ.pop("ED_GWIN_ABSENT", None)
        pages = G.on_flow_spec(41)["pages"]
        self.assertEqual(len(pages), 18)  # 시각표 21쪽 − 한 창으로 합친 둘(「그래. …」·「나는 게일이라고…」, 11-05) − 없음 1쪽
        self.assertEqual(pages[0]["end"], 5.0)
        self.assertGreaterEqual(pages[1]["start"], pages[0]["end"])  # 쪽이 겹치지 않는다(마스터 편집으로 빈 구간은 없어졌다)


class TailJoinTest(unittest.TestCase):
    """같은 창 이어쓰기 조각을 이어 읽는다(11-03 씬 18 #3 「제 이름은」에서 끊김) — 이음 사이의 `81 42`(。)는 「.」, 줄바꿈 `01` 은 공백."""

    def test_join_across_gap(self):
        import messages as M
        import voice_sched as VS

        blk = b"AAAA" + b"\x81\x42\x01" + b"BBBB"
        a = M.Message(0, 4, None, None, ["가"])  # 끝이 글자 → 뒷 조각이 이어진다
        b = M.Message(7, 11, None, None, ["나", ("op", 5)])
        tr = {a.key: {"t": "앞 말"}, b.key: {"t": "뒷 말"}}
        self.assertEqual(VS.tail_join(blk, [a, b], 0, tr), "앞 말. 뒷 말")
        # 앞 조각이 쪽 넘김으로 끝나면 이음이 아니다
        a2 = M.Message(0, 4, None, None, ["가", ("op", 5)])
        self.assertIsNone(VS.tail_join(blk, [a2, b], 0, {a2.key: {"t": "앞 말"}, b.key: {"t": "뒷 말"}}))


if __name__ == "__main__":
    unittest.main()
