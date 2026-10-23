"""조사 전수 검사 — 합성 명사 목록으로 받침 대조가 맞게 도는지 못 박는다(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import check_josa as j

N = {"슬러그", "란도", "마을", "사람", "대마도사 가이아"}  # 받침: 없음 · 없음 · ㄹ · ㅁ · 없음


def bad(t):
    return j.scan(t, N)[1]


class Scan(unittest.TestCase):
    def test_받침_없는_이름_뒤_겹받침_조사는_틀림(self):
        self.assertEqual(bad("슬러그이 왔다"), ["슬러그이"])
        self.assertEqual(bad("란도은 갔다"), ["란도은"])
        self.assertEqual(bad("란도을 불렀다"), ["란도을"])
        self.assertEqual(bad("란도과 슬러그"), ["란도과"])
        self.assertEqual(bad("란도으로 간다"), ["란도으로"])

    def test_받침_있는_이름_뒤_홑받침_조사는_틀림(self):
        self.assertEqual(bad("사람가 왔다"), ["사람가"])
        self.assertEqual(bad("사람는 갔다"), ["사람는"])
        self.assertEqual(bad("사람를 본다"), ["사람를"])
        self.assertEqual(bad("사람로 간다"), ["사람로"])  # ㅁ 받침은 '으로'

    def test_맞는_꼴은_통과(self):
        for t in ("슬러그가 왔다", "란도는 갔다.", "슬러그를 본다", "란도로 간다", "사람이 왔다", "사람은", "사람을", "사람과 란도", "사람으로"):
            self.assertEqual(bad(t), [], t)

    def test_ㄹ_받침은_로가_맞다(self):
        self.assertEqual(bad("마을로 간다"), [])
        self.assertEqual(bad("마을으로 간다"), ["마을으로"])
        self.assertEqual(bad("마을이 크다"), [])
        self.assertEqual(bad("마을가 크다"), ["마을가"])

    def test_여러_낱말_이름과_뜻_없는_어절은_안_잡는다(self):
        self.assertEqual(bad("대마도사 가이아는 웃었다"), [])
        self.assertEqual(bad("대마도사 가이아은 웃었다"), ["가이아은"])
        self.assertEqual(bad("란도가는 길"), [])  # 어간 '란도가' 는 목록에 없다
        self.assertEqual(bad("다녀온 란도 이야기"), [])


if __name__ == "__main__":
    unittest.main()
