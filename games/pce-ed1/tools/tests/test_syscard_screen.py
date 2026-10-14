"""구형 시스템 카드 안내 화면 한글 띠(`syscard_screen.py`) — 자료 규격·훅 크기·좌표 (원본 없이 도는 부분)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import syscard_screen as S


class SyscardScreen(unittest.TestCase):
    def test_hook_and_tramp_fit_their_gaps(self):
        code, entry = S.build_code()
        self.assertLessEqual(len(code), S.CODE_MAX)
        self.assertEqual(entry, 0x6240)
        self.assertLessEqual(len(S.build_tramp()), 15)  # $4000~$5FFF 안 0 틈(이미지 +0x1845)

    def test_data_fits_rel_25_to_27_and_ends_with_zero(self):
        data = S.build_data()
        self.assertLessEqual(len(data), S.DATA_MAX)
        self.assertEqual(data[-1], 0)

    def test_text_fits_the_band_and_tiles_follow_the_original_format(self):
        tiles, bat, _w = S.build_tiles()
        self.assertLessEqual(len(tiles), len(S.TILE_SLOTS))
        for tb in tiles.values():
            self.assertEqual(len(tb), 32)
            self.assertTrue(all(tb[i] == 0xFF for i in range(0, 16, 2)))  # 평면 0 전부 1
            self.assertEqual(tb[1:16:2], tb[16:32:2])  # 평면 1~3 = 같은 글자 행
            self.assertEqual(tb[16:32:2], tb[17:32:2])
        for row in S.BAT_ROWS:
            self.assertEqual(len(bat[row]), 32)
            for w in bat[row]:
                self.assertTrue(w == S.BLANK_ENTRY or (w & 0xF000) == 0x1000 and (w & 0xFFF) in tiles)

    def test_original_gap_is_still_zero_before_patch(self):
        # 방어: 이미지 안 훅 자리가 원판 0 이어야 한다는 가정(원본이 있을 때만 확인 — 없으면 건너뜀).
        try:
            import common

            prog = b"".join(common.track_data(S.IPL_REL + i, 1) for i in range(24))
        except Exception:
            self.skipTest("원본 없음")
        self.assertEqual(prog[S.CALL_OFF : S.CALL_OFF + 3], S.CALL_ORIG)
        self.assertEqual(prog[S.TRAMP_OFF : S.TRAMP_OFF + 15], b"\0" * 15)
        self.assertEqual(prog[S.CODE_OFF : S.CODE_OFF + S.CODE_MAX], b"\0" * S.CODE_MAX)
        self.assertEqual(prog[S.DATA_OFF : S.DATA_OFF + S.DATA_MAX], b"\0" * S.DATA_MAX)


if __name__ == "__main__":
    unittest.main()
