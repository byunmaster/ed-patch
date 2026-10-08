"""정본 검사 돌연변이 시험 — **검사기가 일부러 틀린 줄을 정말 잡는가**(md 실측 10-08: 어댑터 줄 끝의 제어 태그 때문에 정본 검사가
전투·시스템 문구를 하나도 못 재고 「어긋남 0」을 냈다). 원본 파생물이 필요하다(없으면 건너뛴다 — 원본 없이 도는 CI 에선 못 돈다).

① 정본에 걸린 전투·시스템 줄의 우리 줄을 틀리게 바꾸면 어긋남으로 뜬다  ② 원문에 정본 조각이 든 줄 대비 걸린 줄 비율이 낮지 않다(분모 감시)."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import canon
import names_corpus

HANGUL = re.compile("[가-힣]")


def _pairs():
    return [p for p in names_corpus.pairs() if not p[0].startswith("scn")]


class CanonMutation(unittest.TestCase):
    def setUp(self):
        self.pairs = _pairs()
        if not self.pairs:
            self.skipTest("원본 파생물이 없다")

    def test_wrong_line_is_caught(self):
        base = canon.audit(self.pairs, "ed1")
        self.assertEqual(base.mismatches, [], "시험 전제 — 지금 어긋남 0")
        phrase = [h for h in base.hits if h.category in ("battle", "system")]
        self.assertGreater(len(phrase), 100)
        by_where = {p[0]: p for p in self.pairs}
        for h in phrase[:: max(1, len(phrase) // 25)]:  # 고루 25개
            where, jp, kr, *rest = by_where[h.where]
            m = list(
                HANGUL.finditer(kr)
            )[
                -1
            ]  # 마지막 한글 — 앞쪽은 이름 자리표(`{name}`)일 수 있어 아무 글이나 통과한다(이름 검사 몫)
            bad = kr[: m.start()] + "뷁" + kr[m.end() :]
            mutated = [(where, jp, bad, *rest) if p[0] == where else p for p in self.pairs]
            r = canon.audit(mutated, "ed1")
            self.assertTrue(
                any(x.where == where for x in r.mismatches), f"못 잡았다: {where} {kr!r}"
            )

    def test_coverage_is_not_a_fraction(self):
        flat = lambda s: re.sub(r"\s+", "", s or "")
        cats = canon.load("ed1")["categories"]
        lits = [
            flat(max(canon._SLOT.split(k)[::2], key=len))
            for c in canon.PHRASES
            for k in cats.get(c, {})
        ]
        lits = [x for x in lits if len(x) >= 4]
        phr = [p for p in self.pairs if p[0].startswith(("battle:", "sysmsg:"))]
        loose = {p[0] for p in phr if any(x in flat(p[1]) for x in lits)}
        hit = {h.where for h in canon.audit(phr, "ed1").hits}
        self.assertGreaterEqual(
            len(hit & loose), 0.8 * len(loose), f"느슨 {len(loose)} 중 엄격 {len(hit & loose)}"
        )


if __name__ == "__main__":
    unittest.main()
