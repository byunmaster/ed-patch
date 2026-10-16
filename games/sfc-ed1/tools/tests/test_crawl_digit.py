"""크롤 반각 숫자 간격 게이트 — 잉크 열 < 진행 폭."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: E402,F401,I001
import hook  # noqa: E402
import hook_vwf  # noqa: E402


class CrawlDigit(unittest.TestCase):
    def test_숫자_진행폭은_잉크_열보다_크다(self):
        hook.check_crawl_digit_gap()  # 어기면 SystemExit

    def test_진행폭은_5(self):
        self.assertEqual(hook_vwf.CRAWL_DIGIT_ADV, 5)


if __name__ == "__main__":
    unittest.main()
