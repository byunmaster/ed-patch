"""지시사 목록기의 계약 — 원본 없이 도는 회귀.

🔴 이 도구는 **판정이 아니라 목록**이다. 그래서 회귀가 지키는 것도 둘뿐이다 —
**「저」가 지시사인 자리만 걸리나**(오탐), **부류를 원문대로 가르나**(위험한 `あの` 를
`その` 와 섞지 않나). 사람이 볼 목록이라 오탐이 늘면 아무도 안 본다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import list_demonstratives as ld


class TestKrHits(unittest.TestCase):
    def test_catches_demonstratives(self):
        for kr, want in (
            ("저 드래곤이란 게 저거야?", ["저 드래곤이란", "저거"]),
            ("쥬리오도 저래 봬도 사내다운 데가 있으니", ["저래"]),
            ("저쪽으로 가자.", ["저쪽"]),
            ("바로 저것이다", ["저것"]),
        ):
            self.assertEqual(ld.kr_hits(kr), want, kr)

    def test_ignores_words_that_merely_start_with_jeo(self):
        """🔴 오탐이 늘면 목록을 아무도 안 본다 — 「저」로 시작하는 낱말은 지시사가 아니다."""
        for kr in ("저녁에 만나자.", "저희가 하겠습니다.", "저울이 망가졌다.", "저택으로 가라."):
            self.assertEqual(ld.kr_hits(kr), [], kr)

    def test_ignores_near_and_mid_demonstratives(self):
        """「그」·「이」는 안 본다 — 원문이 무엇이든 대개 안전하다."""
        for kr in ("그 애라면 서쪽 들판에", "이 오르골 약속, 기억해?", "나와 그이도"):
            self.assertEqual(ld.kr_hits(kr), [], kr)

    def test_head_of_line_counts(self):
        self.assertEqual(ld.kr_hits("저 사람은 누구야?"), ["저 사람은"])


class TestClassify(unittest.TestCase):
    def test_far_original_is_the_dangerous_class(self):
        """⚠ `あの` 는 조응으로도 쓰여 **원문이 같아서 안심하고 지나가는** 부류다."""
        for jp in ("あの話はもう終わった。", "あれで男らしいところもある", "あそこに行こう"):
            self.assertEqual(ld.classify(jp), "ano", jp)

    def test_mid_original_is_first_order_candidate(self):
        for jp in ("その話はもう終わった。", "それが答えだ"):
            self.assertEqual(ld.classify(jp), "sono", jp)

    def test_no_demonstrative_or_near_is_made_up(self):
        """🔴 기계로 닫히는 유일한 부류 — 원문에 없던 지시를 우리가 만든 자리."""
        for jp in ("ドラゴンが来る。", "この話はもう終わった。", ""):
            self.assertEqual(ld.classify(jp), "made-up", jp)

    def test_far_wins_when_mixed(self):
        """한 줄에 둘이 섞이면 **위험한 쪽**으로 센다 — 놓치는 것보다 낫다."""
        self.assertEqual(ld.classify("あの人がそれを持っている"), "ano")


class TestKinds(unittest.TestCase):
    def test_order_is_risk_order(self):
        """출력 순서가 위험도 순이어야 사람이 위에서부터 본다."""
        self.assertEqual(ld.KINDS, ("made-up", "ano", "sono"))


if __name__ == "__main__":
    unittest.main()
