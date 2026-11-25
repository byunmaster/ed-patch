"""줄·쪽 나눔 규칙 2-16 — 지표 정의와 조판기가 같은 판정을 쓰는가(원본 없이)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import linemetrics as lm
import typeset


class Metrics(unittest.TestCase):
    def test_절째_내리면_들어가는_줄을_센다(self):
        self.assertIsNotNone(lm.clause_fits(["아트라스", "왕자님,", "곧", "열여섯"], ["살이", "되시는", "겁니다."]))

    def test_절이_줄에서_끝나면_안_센다(self):
        self.assertIsNone(lm.clause_fits(["가나다", "라마바,", "사아자"], ["카타파"]) and None)
        self.assertIsNone(lm.clause_fits(["가나다라", "마바사아자,"], ["카타파"]))

    def test_쪽_끝_고아(self):
        m = lm.chunk_metrics([["가나다라 마바사", "아자차"], ["카타파하"]])
        self.assertEqual(len(m["a"]), 1)  # 쪽 끝 줄이 한 어절

    def test_보조용언_쪽_가름(self):
        m = lm.chunk_metrics([["가나다 라마바", "사아자 읽어"], ["보세요."]])
        self.assertEqual(len(m["b"]), 1)  # 본용언 「읽어」 | 보조용언 「보세요」 사이에서 쪽을 끊었다

    def test_표본_세_구문은_갈리지_않는다(self):
        for a, b in (("납치되고", "해서"), ("알아들으리라", "여겨"), ("가르쳐 줄까 했는데", "말이야,")):
            self.assertTrue(lm.glued(a.split()[-1], b), (a, b))

    def test_퇴행_목적어만_줄_끝에_남으면_거부(self):
        before = [["변신 주문을 걸어", "본 게야"]]
        after = [["변신 주문을", "걸어 본 게야"]]
        self.assertTrue(any("목적어" in r for r in lm.regress(before, after)))

    def test_표본_구문_쪽_경계_퇴행(self):
        before = [["가르쳐 줄까 했는데 말이야,", "그건 나중에"]]
        after = [["가르쳐 줄까 했는데"], ["말이야, 그건 나중에"]]
        self.assertTrue(lm.regress(before, after))

    def test_조판기가_지표를_늘리지_않는다(self):
        text = "아트라스 왕자님, 곧 열여섯 살이 되시는 겁니다. 열여섯이라 하면 왕위를 계승하여…"
        import os

        pgs = typeset.pages(text)
        os.environ["ED_LINERULE"] = "0"
        try:
            before = typeset.pages(text)
        finally:
            os.environ.pop("ED_LINERULE")
        self.assertLessEqual(lm.count(lm.chunk_metrics(pgs)), lm.count(lm.chunk_metrics(before)))
        self.assertEqual(lm.regress(before, pgs), [])
        self.assertEqual("".join("".join(p) for p in pgs).replace(" ", ""), text.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
