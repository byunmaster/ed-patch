"""내려앉은 배정(`lowered_map.json`)이 낡지 않았나 — **원본 없이 돈다**.

🔴 문안이 늘었는데 정본을 안 갱신하면 새 글자가 **본 글리프(한 행 높은 것)** 로 나간다. 빌드도 게이트도
통과하고 화면에서만 1px 높다(2026-10-01: 승리 문구 「승」 — 마스터 스크린샷). 그래서 문안이 쓰는 글자가
정본에 다 있는지 본다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hangul_map as H


class LoweredMap(unittest.TestCase):
    def test_every_char_is_assigned(self):
        missing = sorted(set(H.lowered_chars()) - set(H.load_low()))
        self.assertEqual(missing, [], f"`hangul_map.py --freeze-low` 로 덧붙인다: {''.join(missing)}")


if __name__ == "__main__":
    unittest.main()
