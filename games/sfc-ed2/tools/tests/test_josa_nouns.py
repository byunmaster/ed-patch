"""명사×조사 대조 검사기 — 합성 문안으로 잡는지 본다(정본 명사가 있는 환경에서만)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import common


@unittest.skipUnless(common.ORIG_ROM.exists(), "원본 롬 없음")
class JosaNouns(unittest.TestCase):
    def setUp(self):
        import check_josa_nouns

        self.m = check_josa_nouns

    def test_catches_wrong_particle(self):
        seen, bad = self.m.scan([("t1", "플로라이 왔다."), ("t2", "란도은 갔다."), ("t3", "란도를 만났다."), ("t4", "란도가 왔다.")], {})
        self.assertEqual({b[0] for b in bad}, {"t1", "t2"})

    def test_passes_right_and_skips_demonstrative(self):
        seen, bad = self.m.scan([("a", "플로라가 왔다."), ("b", "란도는 이 사람을 안다."), ("c", "란도\n이 사람"), ("d", "<E0:10>{이/가} 지키던")], {"E0:10": "가드"})
        self.assertEqual(bad, [])

    def test_dict_token_uses_expanded_name(self):
        _, bad = self.m.scan([("x", "<E0:10>이 지키던 곳")], {"E0:10": "가드"})
        self.assertEqual([b[0] for b in bad], ["x"])


if __name__ == "__main__":
    unittest.main()
