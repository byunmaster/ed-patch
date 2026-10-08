"""정본 검사 **돌연변이 시험** — 정본 battle·system 문구를 우리 줄에서 일부러 틀리게 바꾸면 `canon.audit` 가 잡나.

🔴 md 가 실측했다(10-08): 어댑터가 낸 줄 끝에 제어 태그가 붙어 정본의 줄 전체 대조에 안 걸리면 **검사기가 문구를
   하나도 못 재면서 「어긋남 0」** 이 뜬다. 0 이 「없다」가 아니라 「안 쟀다」일 수 있으니 **일부러 틀려 본다**.
⚠ 원본 디스크가 필요하다(어댑터가 이미지에서 줄을 읽는다) — 없으면 건너뛴다.
"""

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "..", "..", "..", "shared"))

import common  # noqa: E402


@unittest.skipUnless(os.path.exists(common.ORIG_BIN), "원본 디스크 없음")
class TestCanonMutation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import canon
        import names_corpus

        cls.canon = canon
        cls.items = list(names_corpus.pairs())

    def _by_title(self):
        out = {"ed1": [], "ed2": []}
        for it in self.items:
            out["ed2" if "ED2" in str(it[0]) else "ed1"].append(it)
        return out

    def test_모집단이_실제로_잡힌다(self):
        """출현 수가 0 이거나 터무니없이 작으면 검사기가 안 재고 있다는 뜻이다."""
        for title, items in self._by_title().items():
            r = self.canon.audit(items, title)
            self.assertGreater(len(r.hits), 100, f"{title}: 정본 문안 출현 {len(r.hits)}")

    def test_정본_문구를_틀리게_바꾸면_어긋남으로_잡힌다(self):
        for title, items in self._by_title().items():
            base = self.canon.audit(items, title)
            phrase_hits = [h for h in base.hits if h.category in ("battle", "system")]
            self.assertTrue(phrase_hits, f"{title}: battle·system 출현이 0")
            # 서로 다른 열 곳에서 정본 값을 망가뜨린다
            seen, targets = set(), []
            for h in phrase_hits:
                if h.where in seen or h.canon not in "".join(i[2] or "" for i in items if i[0] == h.where):
                    continue
                seen.add(h.where)
                targets.append(h)
                if len(targets) == 10:
                    break
            self.assertGreaterEqual(len(targets), 5, f"{title}: 시험할 줄이 모자란다")
            for h in targets:
                broken = []
                for it in items:
                    if it[0] == h.where:
                        it = (it[0], it[1], it[2].replace(h.canon, "ＸＸＸ", 1), *it[3:])
                    broken.append(it)
                r = self.canon.audit(broken, title)
                self.assertGreater(
                    len(r.mismatches),
                    len(base.mismatches),
                    f"{title} {h.where} 「{h.canon}」 를 망가뜨렸는데 어긋남이 안 늘었다 — 검사기가 이 줄을 못 잰다",
                )


if __name__ == "__main__":
    unittest.main()
