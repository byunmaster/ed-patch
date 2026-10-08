"""정본 검사(check_canon)가 md 어댑터의 줄에서 실제로 잡는가 — 돌연변이 시험.

2026-10-08: 어댑터가 낸 줄 끝에 제어태그(`<0a|끝>`)가 붙어 정본의 줄 전체 정규식(`^…$`)에 안 걸렸다. 정본 값이 바뀌었는데
「어긋남 0」이었다(눈먼 게이트). 어댑터 정규화(`names_corpus._t`)와 정본 audit 을 같이 태워, 정본 문구를 일부러 틀리게 하면
**실패하는지** 묶어 둔다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from shared import canon

import names_corpus as N


def audit(jp, ours):
    return canon.audit([("battle:000:x", N._t(jp), N._t(ours), "dialog")], "ed1")


class CanonGate(unittest.TestCase):
    def test_battle_phrase_with_end_tags_is_measured(self):
        good = audit("剣が空を切る音がした。<0a|끝>", "허공 베는 소리가 났다.<0a>")
        self.assertEqual((len(good.hits), len(good.mismatches)), (1, 0))

    def test_mutated_battle_phrase_fails(self):
        bad = audit("剣が空を切る音がした。<0a|끝>", "검이 허공을 가르는 소리가 났다.<0a>")
        self.assertEqual(len(bad.mismatches), 1)

    def test_system_phrase_with_josa_hook(self):
        # `<02><eb00>` = 이름 + 은/는 훅 → 정본의 병기 조사(은(는))로 풀려 같은 것으로 잰다
        ok = audit("<02>は気絶してしまった。<0a|끝>", "<02><eb00> 기절해 버렸다.<0a>")
        self.assertEqual((len(ok.hits), len(ok.mismatches)), (1, 0))
        bad = audit("<02>は気絶してしまった。<0a|끝>", "<02><eb00> 기절했다.<0a>")
        self.assertEqual(len(bad.mismatches), 1)

    def test_normalization_leaves_no_end_tags(self):
        for s in ("끝<0a|끝>", "끝<07>", "끝<01><00>"):
            self.assertNotIn("<", N._t(s).replace("\n", ""))


if __name__ == "__main__":
    unittest.main()
