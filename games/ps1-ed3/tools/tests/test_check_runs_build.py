"""게이트가 **실제 빌드 경로**를 돌리나 — 정적 검사만 초록이고 빌드가 서는 사고(10-18 md-ed2 발견)를 고정한다."""

import os
import unittest

GAME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCheckRunsBuild(unittest.TestCase):
    def test_check_sh_really_builds_and_fails_on_missing_output(self):
        """쓰기 직전에 돌려보내는 `--dry-run` 이 아니라 **실제로 굽고**, 낡은 이미지를 먼저 지우며, 실패·산출물 없음·미완이면 fail=1."""
        s = open(os.path.join(GAME, "check.sh"), encoding="utf-8").read()
        self.assertRegex(s, r'ED_BUILD_TAG=test-gate .*build\.py" --disc ed3 --test')
        self.assertFalse([x for x in s.splitlines() if "--dry-run" in x and not x.lstrip().startswith("#")])
        self.assertLess(s.index('rm -rf "$_gd"'), s.index("ED_BUILD_TAG=test-gate"))  # 낡은 산출물을 먼저 치운다
        for need in ('_brc" -ne 0', '-z "$_bin"', "*.failed", "*.part"):
            self.assertIn(need, s)
        self.assertGreaterEqual(s.count("fail=1"), 4)



if __name__ == "__main__":
    unittest.main()
