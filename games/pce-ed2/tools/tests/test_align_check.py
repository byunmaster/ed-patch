"""짝 경계 검사 — 덧붙음·중복·구간 연장·문장 자르기 판정(합성 자료, 원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import align_check as ac


def world(blocks):
    """blocks = [(본문 정규화, 일문 문장들, 한글 문장들)] — 씬 1 의 연속 블록."""
    by = {(1, i): {"n": n, "jp_sents": js, "kr_sents": ks, "scn": 1, "id": i} for i, (n, js, ks) in enumerate(blocks)}
    order = {1: list(by)}
    pos = {k: (1, i) for i, k in enumerate(by)}
    return by, order, pos


class RefineTest(unittest.TestCase):
    def test_system_notice_block_is_extra(self):
        by, order, pos = world(
            [
                ("あおいほんをもらった", ["あおいほんをもらった。"], ["파란 책을 받았다."]),
                ("ひとりでたびにでると", ["ひとりでたびにでると"], ["혼자 여행을 떠나면"]),
                ("ごはんもたべられなくなる", ["ごはんもたべられなくなる。"], ["밥도 못 먹게 된다."]),
            ]
        )
        T = "ひとりでたびにでると" + "ごはんもたべられなくなる"
        new, why, _miss, _part = ac.refine(T, [(1, 0), (1, 1), (1, 2)], by, order, pos)
        self.assertEqual([r[1] for r in new], [1, 2])
        self.assertTrue(any("덧붙음" in w for w in why))

    def test_variant_pair_is_duplicate(self):
        by, order, pos = world(
            [
                ("あぶないからちかづくな", ["あぶないからちかづくな。"], ["위험하니."]),
                ("まだあぶないからちかづくな", ["まだあぶないからちかづくな。"], ["아직 위험하니."]),
            ]
        )
        T = "まだあぶないからちかづくな"
        new, why, _m, _p = ac.refine(T, [(1, 0), (1, 1)], by, order, pos)
        self.assertEqual([r[1] for r in new], [1])
        self.assertTrue(any("중복" in w for w in why))

    def test_span_extends_to_missing_tail_sentence(self):
        by, order, pos = world(
            [
                ("よしそれならまずおまえから", ["よし、それなら まず おまえから。"], ["좋다."]),
                ("かくごしろ", ["かくごしろ！"], ["각오해라!!"]),
            ]
        )
        T = "よしそれならまずおまえからかくごしろ"
        new, why, _m, _p = ac.refine(T, [(1, 0)], by, order, pos)
        self.assertEqual([r[1] for r in new], [0, 1])
        self.assertTrue(any("연장" in w for w in why))

    def test_leading_greeting_sentence_is_cut(self):
        by, order, pos = world(
            [("おいきみたちてつづきはすんだか", ["おい きみたち。", "てつづきは すんだか？"], ["이봐 거기.", "출국 수속은 끝났나?"])]
        )
        T = "てつづきはすんだか"
        new, why, _m, _p = ac.refine(T, [(1, 0)], by, order, pos)
        self.assertEqual(new, [[1, 0, 1, 2]])

    def test_short_tail_is_not_cut(self):
        # 값 자리표 뒤 꼬리(「だね。」)는 PCE 본문에서 못 맞춰도 자르지 않는다(DROP_MIN)
        by, order, pos = world([("だねどうもありがとう", ["だね。", "どうもありがとう。"], ["이거.", "정말 고맙습니다."])])
        new, _w, _m, _p = ac.refine("ねどうもありがとう", [(1, 0)], by, order, pos)
        self.assertEqual(new, [[1, 0]])

    def test_is_idempotent(self):
        by, order, pos = world([("おいきみたちてつづきはすんだか", ["おい きみたち。", "てつづきは すんだか？"], ["이봐 거기.", "출국 수속은 끝났나?"])])
        T = "てつづきはすんだか"
        once = ac.refine(T, [(1, 0)], by, order, pos)[0]
        twice = ac.refine(T, [tuple(r[:2]) for r in once], by, order, pos)[0]
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
