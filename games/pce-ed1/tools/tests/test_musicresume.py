"""음악 이어 재생(`musicresume.py`) — 자리·호출 계약. 소리 판정은 에뮬(CD 호출 로그)·마스터 귀."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import musicresume as mr
import splitload
import winmask


class MusicResume(unittest.TestCase):
    def test_fits_in_bank73_tail_after_winmask(self):
        self.assertLessEqual(len(mr.code()), mr.CODE_LEN)
        self.assertGreaterEqual(
            mr.OFF, winmask.TAIL_OFF + winmask.TOTAL_LEN
        )  # winmask 와 안 겹친다
        self.assertLessEqual(mr.OFF + mr.CODE_LEN, 0x2000)

    def test_far_call_shape(self):
        for name in ("savepos", "replay"):
            b = mr.far_call(name)
            self.assertEqual(b[:3], b"\x20\xd8\x4f")  # JSR $4FD8
            self.assertEqual(b[3], mr.BANK - 0x68 - 1)
            addr = int.from_bytes(b[4:6], "little")
            self.assertTrue(mr.ORG <= addr < mr.ORG + mr.CODE_LEN)

    def test_load_hook_site_and_shape(self):
        # 원판 LOAD 성공 꼬리 `JSR $7D55 · JSR $4240` 6B 를 먼 호출 6B 로 갈아 끼운다(뒤따르는 CLA·CLC·RTS 는 그대로)
        self.assertEqual(len(mr.LOAD_SITE_ORIG), len(mr.far_call("loadhook")))
        self.assertEqual(mr.LOAD_SITE_ORIG[:3], b"\x20\x55\x7d")
        self.assertEqual(mr.LOAD_SITE_ORIG[3:], b"\x20\x40\x42")
        code = mr.code()
        off = mr.far_addr("loadhook") - mr.ORG
        self.assertEqual(code[off : off + 3], b"\x20\x18\xe0")  # JSR $E018(CD_PAUSE) 로 시작

    def test_buffer_is_ten_contiguous_bytes_and_passed_in_fa_fb(self):
        lab = mr._final().labels
        self.assertEqual(lab["buf7"] - lab["buf"], 7)
        self.assertEqual(lab["buf9"] - lab["buf"], 9)
        code = mr.code()
        buf = lab["buf"]
        # LDA #lo · STA $FA · LDA #hi · STA $FB (BIOS CD_SUBQ 는 10B 를 ($FA) 로 받는다)
        pat = bytes([0xA9, buf & 0xFF, 0x85, 0xFA, 0xA9, buf >> 8, 0x85, 0xFB])
        self.assertIn(pat, code)

    def test_splitload_still_fits(self):
        self.assertLessEqual(splitload.layout()["len"], splitload.ROOM)


if __name__ == "__main__":
    unittest.main()
