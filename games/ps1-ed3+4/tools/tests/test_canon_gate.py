"""정본 검사가 **실제로 걸리는가** — 돌연변이 시험(md 실측 10-08: 어댑터 줄 끝 태그 때문에 정본 검사가 하나도 못 쟀는데 「어긋남 0」이었다).

「어긋남 0」은 「다 맞다」가 아니라 「못 쟀다」일 수 있다 — 정본의 문구 하나를 일부러 틀리게 바꿔 **실패하는지**를 박는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import glossary

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def _canon():
    return glossary._canon()


class TestCanonGateMutation(unittest.TestCase):
    JP = "ロードします。"
    KR = "로드합니다."

    def test_synthetic_exact_line_is_checked_and_a_wrong_text_fails(self):
        canon = _canon()
        self.assertEqual(canon.lookup(self.JP, "system", "ed3"), self.KR)
        ok = canon.audit([("ui:0x0", self.JP, self.KR, "slot")], "ed3")
        self.assertEqual((len(ok.hits), len(ok.mismatches)), (1, 0))
        bad = canon.audit([("ui:0x0", self.JP, "엉뚱한 문구", "slot")], "ed3")
        self.assertEqual(len(bad.mismatches), 1, "틀린 문구가 안 걸린다 — 정본 검사가 못 재고 있다")

    def test_trailing_newline_does_not_hide_the_line(self):
        """줄 끝 줄바꿈이 붙어도 걸려야 한다. (우리 어댑터 줄에는 줄바꿈 말고 제어 태그가 없다 — md 의 `%c` 류 구멍은 해당 없음, 실측 `ctl` 센 결과)"""
        canon = _canon()
        for tail in ("", "\n"):
            bad = canon.audit([("ui:0x0", self.JP + tail, "엉뚱한 문구" + tail, "slot")], "ed3")
            self.assertEqual(len(bad.mismatches), 1, repr(tail))

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "originals", "jp", "ps1-ed3")), "원본 필요")
    def test_real_adapter_pairs_are_measured_and_mutation_fails(self):
        """어댑터가 내는 실제 줄로 — 정본 문구와 겹치는 줄이 **0 이 아니고**, 하나를 틀리게 하면 걸린다."""
        import names_corpus as N

        canon = _canon()
        pairs = list(N._ui_pairs()) + list(N._exe_pairs())  # 씬 대사는 정본 범위 밖 — 안 푼다(빠르다)
        base = canon.audit(pairs, "ed3")
        self.assertGreaterEqual(len(base.hits), 5, "실제 줄이 정본에 거의 안 걸린다 — 어댑터 줄 모양을 의심")
        mutated = [(w, jp, ("엉뚱한 문구" if jp == self.JP else kr), g) for w, jp, kr, g in pairs]
        self.assertGreater(len(canon.audit(mutated, "ed3").mismatches), len(base.mismatches))


if __name__ == "__main__":
    unittest.main()
