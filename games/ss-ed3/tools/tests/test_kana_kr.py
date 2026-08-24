"""가타카나 → 한글 음차 후보 회귀 — **원본 없이 돈다**.

이 파일이 지키는 건 「정답」이 아니라 **정답이 후보 안에 있는가**다. 고르는 건 정발
코퍼스이고(`glossary_probe.py`), 여기서 빠지면 코퍼스가 아무리 좋아도 못 찾는다.

실제 정발 ED3 표기로 못 박는다 — 각 항목이 **처음엔 후보에 없어서** 한 건씩 놓쳤다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kana_kr import candidates

# JP → 정발 ED3 실측 표기 (빈도는 `work/review/glossary_ed3.md`)
KNOWN = {
    "ジュリオ": "쥬리오",  # 896
    "クリス": "크리스",  # 594  ← `ク`=크 (쿠 아님)
    "ボルト": "볼트",  # 127  ← `ル` 받침
    "アルフ": "알프",  # 104  ← `ル` 받침 + `フ`=프
    "フィリー": "휘리",  # 110  ← `フィ`=휘 (피 아님)
    "デュルゼル": "듀르젤",  # 100  ← `ュ` 요음 + `ル` 두 갈래
    "ラグピック": "라그픽",  # 72   ← `ッ` 무시 + `ク` 받침
    "ルーレ": "르레",  # 71   ← 장음 무시 + `ル`=르
    "ダーツ": "다츠",  # 69
    "グース": "구스",  # 67
    "クリスチーナ": "크리스티나",  # 10   ← `チ`=티 (치 아님)
    "ジョアンナ": "죠안나",  # 40   ← `ン` 받침
    "モリスン": "모리슨",  # 54
    "テグラ": "테그라",  # 58   ← `グ`=그
}


class TestCandidates(unittest.TestCase):
    def test_정발_표기가_후보_안에_있다(self):
        missing = [(jp, kr) for jp, kr in KNOWN.items() if kr not in candidates(jp)]
        self.assertEqual(missing, [], f"후보에서 빠졌다: {missing}")

    def test_후보가_터무니없이_많지_않다(self):
        """코퍼스가 고르긴 하지만, 후보가 수백 개면 우연히 맞는 게 섞인다."""
        for jp in KNOWN:
            self.assertLessEqual(len(candidates(jp)), 96, jp)

    def test_받침_축약(self):
        """🔴 이걸 모르면 「보루토·아루후」가 나와 코퍼스에서 한 건도 안 걸린다."""
        self.assertIn("볼트", candidates("ボルト"))
        self.assertIn("반반", candidates("バンバン"))

    def test_장음은_무시한다(self):
        self.assertIn("로디", candidates("ローディ"))

    def test_요음은_한_음절(self):
        self.assertIn("샤라", candidates("シャーラ"))

    def test_후보에_빈_문자열이_없다(self):
        for jp in ("ー", "ッ", "ン"):
            self.assertNotIn("", candidates(jp))


if __name__ == "__main__":
    unittest.main()
