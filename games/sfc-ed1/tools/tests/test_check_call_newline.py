"""호출 끝 개행 대조(`check_call_newline.compare`)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_call_newline as c


class CallNewline(unittest.TestCase):
    def test_같으면_통과(self):
        self.assertEqual(c.compare("가\n<RETURN>나", "다\n<FE>라"), [])
        self.assertEqual(c.compare("가<RETURN>나", "다<FE>라"), [])

    def test_우리만_개행이_빠지면_걸린다(self):
        self.assertEqual(c.compare("가\n<RETURN>나", "다<FE>라")[0][0], 0)

    def test_조각_수가_다르면_걸린다(self):
        self.assertEqual(c.compare("가<RETURN>나", "다")[0][0], -1)

    def test_복귀_뒤_개행은_쪽_첫머리가_아니다(self):
        import typeset

        self.assertEqual(typeset.return_newlines("가<RETURN>\n<RETURN>나"), frozenset({0}))
        _, bad = typeset.layout(typeset.expand("가\n<FE>\n<FE>나", {}, {}, frozenset({0})))
        self.assertEqual(bad, [])
        _, bad = typeset.layout(typeset.expand("가\n<FE>\n<FE>나", {}, {}))
        self.assertIn("② 쪽 첫머리 개행", bad)


if __name__ == "__main__":
    unittest.main()
