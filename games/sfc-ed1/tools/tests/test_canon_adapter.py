"""정본 검사 어댑터의 돌연변이 시험 — 줄 끝·자리 태그 때문에 전투·시스템 문구를 **하나도 못 재던** 구멍(md 실측 10-08)을 막는다.

어댑터가 내는 줄(`names_corpus.norm_*` 를 거친 것)로 정본 `canon.audit` 를 돌려, 맞는 문안은 **출현으로 잡히고**
(0 이면 눈이 먼 것이다) 일부러 틀린 문안은 **어긋남으로 잡히는지** 본다. 원본 롬 없이 돈다.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "shared"))
import canon  # noqa: E402
import names_corpus  # noqa: E402

JP = "<COLOR_C><D6><COLOR_POP>は\nしびれてしまった!!\n<END>"  # 전투 문구(정본 battle)
OK = "<E3>{D6}<E1>{은/는} 마비되고 말았다!!<E0>"
BAD = "<E3>{D6}<E1>{은/는} 저려 버렸다!!<E0>"


def audit(kr):
    item = ("seg:t@000000", names_corpus.norm_jp(JP), names_corpus.norm_kr(kr), "dialog")
    return canon.audit([item], "ed1")


class CanonAdapter(unittest.TestCase):
    def test_정규화(self):
        self.assertEqual(names_corpus.norm_jp(JP).replace("\n", ""), "{name}はしびれてしまった!!")
        self.assertEqual(names_corpus.norm_kr(OK).strip(), "{name}은(는) 마비되고 말았다!!")
        self.assertEqual(names_corpus.norm_jp("<DC>さがった。<END>").strip(), "{n}さがった。")

    def test_맞는_문안은_출현으로_잡힌다(self):
        r = audit(OK)
        self.assertEqual(len(r.hits), 1)  # 0 이면 검사기가 눈이 먼 것
        self.assertEqual(len(r.mismatches), 0)

    def test_틀린_문안은_어긋남으로_잡힌다(self):
        r = audit(BAD)
        self.assertEqual(len(r.mismatches), 1)


if __name__ == "__main__":
    unittest.main()
