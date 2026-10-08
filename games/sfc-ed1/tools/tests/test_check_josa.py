import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_josa  # noqa: E402


class CheckJosa(unittest.TestCase):
    def axes(self, kr):
        return [a for a, _ in check_josa.scan(kr)]

    def test_받침_불일치를_잡는다(self):
        self.assertEqual(self.axes("검를 얻었다"), ["①"])
        self.assertEqual(self.axes("약을 얻었다"), [])
        self.assertEqual(self.axes("물약를."), ["①"])

    def test_단일_형태소는_넘긴다(self):
        self.assertEqual(self.axes("마을 사람"), [])

    def test_변수_뒤_고정_조사를_잡는다(self):
        self.assertEqual(self.axes("{D6}를 쓴다"), ["②"])
        self.assertEqual(self.axes("{D6}{을/를} 쓴다"), [])
        self.assertEqual(self.axes("{D6}의 검"), [])


if __name__ == "__main__":
    unittest.main()
