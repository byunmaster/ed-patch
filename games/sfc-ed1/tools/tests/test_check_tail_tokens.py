"""check_tail_tokens 자신의 커버리지 — 덤프를 넣으면 잡고 정상 꼴은 통과한다. 원본 롬 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_tail_tokens as c  # noqa: E402


class TailTokens(unittest.TestCase):
    def test_쪽_끝_열을_뽑는다(self):
        self.assertEqual(c.kr_runs("가나다.{D0:46}<E0>"), [["{D0:46}"]])
        self.assertEqual(c.kr_runs("가나{D0:44}님.<FF>다라.{D0:37}{D5:10}\n<E0>"), [[], ["{D0:37}", "{D5:10}"]])

    def test_덤프는_위반(self):
        jp = [[]]
        self.assertEqual(c.violations(jp, [["{D0:37}"]]), [0])
        self.assertEqual(c.violations([["{D0:46}"]], [["{D0:46}", "{D0:37}"]]), [0])

    def test_정상은_통과(self):
        self.assertEqual(c.violations([["{D5:10}"]], [["{D5:10}"]]), [])  # 원문도 같은 열로 끝난다
        self.assertEqual(c.violations([["{D5:04}", "{D5:05}"]], [["{D5:05}"]]), [])  # 어순 이동
        self.assertEqual(c.violations([[], []], [[]]), [])  # 쪽 수가 다르면 이 검사의 몫이 아니다

    def test_이름표가_글_뒤로_가면_위반(self):
        self.assertTrue(c.label_at_end("무슨 말이냐?<E3>{D0:40}<E1><E0>"))
        self.assertFalse(c.label_at_end("<E3>{D0:40}\n<E1>무슨 말이냐?<E0>"))
        self.assertFalse(c.label_at_end("하하.<FF><E3>{D0:40}\n<E1>그래.<E0>"))


if __name__ == "__main__":
    unittest.main()
