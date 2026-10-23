"""check_josa_names 자신의 커버리지 — 이름 뒤 틀린 조사를 넣으면 잡고 맞는 꼴은 통과한다. 원본 롬 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_josa_names as c  # noqa: E402

NM = {"아크담", "슬러그", "로우"}


class JosaNames(unittest.TestCase):
    def test_틀린_조사를_잡는다(self):
        self.assertEqual(c.wrong("아크담가 왔다", NM), ["아크담가→아크담이"])
        self.assertEqual(c.wrong("슬러그이 나타났다", NM), ["슬러그이→슬러그가"])
        self.assertEqual(c.wrong("아크담는 도망쳤다", NM), ["아크담는→아크담은"])
        self.assertEqual(c.wrong("로우을 불렀다", NM), ["로우을→로우를"])
        self.assertEqual(c.wrong("로우과 함께", NM), ["로우과→로우와"])

    def test_맞는_조사는_통과(self):
        for t in ("아크담이 왔다", "슬러그가 나타났다", "아크담은 도망쳤다", "로우를 불렀다", "로우와 함께", "아크담이옵니다"):
            self.assertEqual(c.wrong(t, NM), [], t)


if __name__ == "__main__":
    unittest.main()
