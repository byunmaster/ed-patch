"""죽은 자료 회수(`systext.DEAD_DEBUG`)는 산 코드를 건드리지 않는다 — 11-06 횃불 프리징 회귀."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import systext


class DeadDebug(unittest.TestCase):
    def test_live_item_fail_handler_not_reclaimed(self):
        # 뱅크 0x70 `+1AED`~`+1B2E` 는 필드 아이템 「효과 없음」 출력 루틴(간접 호출)이다 — 비우면 그 위에 한글이 얹혀 CPU 가 문자열을 실행한다.
        for bank, off, ln, _h, _t in systext.DEAD_DEBUG:
            self.assertFalse(bank == 0x70 and off < 0x1B2E and off + ln > 0x1AED)

    def test_only_debug_text_listed(self):
        self.assertEqual([(b, o) for b, o, *_ in systext.DEAD_DEBUG], [(0x70, 0x0B20)])


if __name__ == "__main__":
    unittest.main()
