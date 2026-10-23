"""장면 패키지 전수 잔존 게이트 — 분모 분할·목록 꼴은 원본 없이, 「번역 안 된 이미지는 실패한다」는 원본이 있을 때만."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import package
import residual_gate as g


class Partition(unittest.TestCase):
    def test_본편과_제외_목록은_안_겹친다(self):
        book = {(r - 2) // 128 for r in package.CLEAN}
        sets = [book, g.BATTLE_TEST, g.UNDECIDED, g.NOT_ED2]
        for i, a in enumerate(sets):
            for b in sets[i + 1 :]:
                self.assertFalse(a & b)

    def test_최종_장면_21_이_본편에_있다(self):
        # 패키지 21 이 목록에서 빠져 일본어로 남았던 일(10-18)의 재발 방지
        self.assertIn(2690, package.CLEAN)
        self.assertNotIn(21, g.BATTLE_TEST | g.UNDECIDED | g.NOT_ED2)

    def test_알려진_목록에_원문이_없다(self):
        for k, c in g.known().items():
            rel, msg, line = (int(x) for x in k.split(":"))
            self.assertIn(rel, package.CLEAN)
            self.assertTrue(msg >= 0 and line >= 0)
            self.assertIn(c, {"행동", "기타"})


@unittest.skipUnless(common.ORIG_ISO.exists(), "원본이 없다")
class Detects(unittest.TestCase):
    def test_번역_안_된_원본_이미지는_실패한다(self):
        errs, now = g.evaluate(common.ORIG_ISO)
        self.assertTrue(any("알려진 목록 밖 잔존" in e for e in errs))
        self.assertGreater(len(now), 1000)  # 원본엔 일본어 줄이 수천 줄 있다


if __name__ == "__main__":
    unittest.main()
