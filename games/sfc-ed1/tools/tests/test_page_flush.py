"""쪽 첫 글자 플러시 트램펄린(빠름·멈춤에서 앞 쪽이 새 글자 타일에 덮여 보이던 것)의 기계어 모양 — 엔진 문맥이라 손으로 짠 바이트다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hook


class PageFlush(unittest.TestCase):
    def test_바이트와_분기_거리(self):
        b = hook.FLUSH_TRAMP_BYTES
        self.assertEqual(b[0:3], bytes([0xAD, 0x3B, 0x17]))  # LDA $173B
        self.assertEqual(b[3], 0xD0)  # BNE
        self.assertEqual(b[4], 3)  # JSR(3바이트) 를 건너뛰어 JMP 로 떨어진다
        self.assertEqual(b[5:8], bytes([0x20, 0xAD, 0xF1]))  # JSR $F1AD
        self.assertEqual(b[8:11], hook.FLUSH_SITE_ORIG)  # 원래 건너뛰던 곳으로 돌아간다
        self.assertEqual(len(b), 11)

    def test_자리_겹침(self):
        # 다른 트램펄린(FE52~FE7F)과 안 겹친다
        self.assertGreaterEqual(hook.FLUSH_TRAMPOLINE, 0x02FE80)
        self.assertEqual(hook.FLUSH_SITE_ORIG[0], 0x4C)


if __name__ == "__main__":
    unittest.main()
