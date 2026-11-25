"""쪽 끝 앞 개행이 줄 배치와 겹쳐 빈 창(`<05><05>`)을 만들지 않는다(11-06 $C83508 — 마스터 실플레이 빈 대사창 갈래)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import typeset as T


class EmptyPageTest(unittest.TestCase):
    def test_no_empty_window_from_trailing_newline(self):
        # 가짜 문장 — 세 줄째가 쪽 끝 개행과 겹쳐 빈 쪽이 끼던 꼴
        s = "당신들 같은 사내를 아가씨께\n가까이 붙이지 말라고 주인님께서\n단단히 이르셨습니다.\n<05>알았으면 냉큼 나가 주시겠습니까?"
        out = T.no_empty_window(s)
        self.assertNotIn("<05><05>", out)
        self.assertEqual(out.count("<05>"), 1)

    def test_kept_when_no_empty_page(self):
        out = T.no_empty_window("가나다.\n<05>라마바.")
        self.assertEqual(out, "가나다.\n<05>라마바.")


if __name__ == "__main__":
    unittest.main()
