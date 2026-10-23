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

    def test_data_fits_rel_25_to_27(self):
        data = S.build_data()
        self.assertLessEqual(len(data), S.DATA_MAX)
        self.assertEqual(len(data), S.HDR_BYTES + S.FIX_BYTES + (1 + len(S.SUBS)) * S.SUB_BYTES)

    def test_schedule_is_sorted_and_ends_with_the_static_band(self):
        ev = S.schedule_frames()
        self.assertEqual([n for _f, n in ev], [1, 2, 3, 4, 0])
        self.assertEqual(sorted(f for f, _n in ev), [f for f, _n in ev])
        data = S.build_data()
        for i, (fr, n) in enumerate(ev):
            self.assertEqual(data[i * 3 : i * 3 + 3], bytes((fr & 0xFF, fr >> 8, n)))
        self.assertEqual(data[len(ev) * 3 : len(ev) * 3 + 2], b"\x00\xff")  # 끝 표시(상위 FF)

    def test_we_never_touch_the_egg_tiles(self):
        # 🔴 달걀 그림 아랫부분 = 행 23 열 21~27(타일 $211~$217, 8줄 전부) — BAT 도 타일 데이터도 안 건드린다(마스터 10-17)
        self.assertNotIn(23, S.BAT_ROWS)
        self.assertGreater(S.FIRST_TILE, 0x217)
        self.assertLessEqual(S.FIRST_TILE + 128, 0x300)  # 스프라이트 패턴(0x384~) 앞
        self.assertEqual(S.SUB_TILE, S.FIX_TILE + 64)
        self.assertEqual(len(S.BAT_ROWS) * 32, 128)

    def test_tiles_follow_the_original_format_with_black_outline(self):
        tiles = S.band_tiles(S.SUBS[0][0])
        self.assertEqual(len(tiles), 64)
        for tb in tiles:
            self.assertEqual(len(tb), 32)
            self.assertEqual(tb[1:16:2], tb[16:32:2])  # 평면 1 = 평면 2 = 평면 3 = 글자
            self.assertEqual(tb[16:32:2], tb[17:32:2])
            for k in range(8):  # 글자 픽셀은 외곽선 픽셀이 아니다(평면 0 = 1)
                self.assertEqual(tb[2 * k + 1] & ~tb[2 * k], 0)
        fixed = S.band_tiles(None, fixed=True)
        for tb in fixed:  # 고정 문구는 외곽선 없음 — 평면 0 전부 1(원판 글씨 타일 규약)
            self.assertTrue(all(tb[i] == 0xFF for i in range(0, 16, 2)))
        self.assertTrue(any(tb[2 * k + 1] for tb in tiles for k in range(8)))

    def test_ink_rows_follow_the_m12_layout(self):
        import numpy as np

        def rows(mask_bytes, tile_row0):  # 마스크 바이트 → 잉크가 있는 화면 y 목록
            ys = set()
            for i, b in enumerate(mask_bytes):
                if b:
                    tr, rem = divmod(i, S.ROW_BYTES)
                    ys.add(8 * (tile_row0 + tr) - 1 + rem // 32)
            return ys

        fy = rows(S.fixed_bytes(), 24)
        self.assertEqual((min(fy), max(fy)), (191, 201))  # 원판 글씨 줄 그대로
        for text, _s in S.SUBS:
            raw = S.sub_bytes(text)
            wy, ey = rows(raw[: S.ROW_BYTES * 2], 26), rows(raw[S.ROW_BYTES * 2 :], 26)
            self.assertEqual(max(ey), 219)  # 외곽선 바닥 = 화면 아래 끝(231)에서 12px
            self.assertEqual((min(wy), max(wy)), (208, 218)) if text.startswith("3.00") else self.assertLessEqual(max(wy), 218)
            self.assertGreater(min(ey) - max(fy), 4)  # 고정 문구와 5px 이상 띄운다

    def test_every_subtitle_fits_the_band(self):
        for text, _s in S.SUBS:
            S.sub_bytes(text)  # 256px 를 넘으면 단언 실패 — 3번은 공백 6px 로 한 줄

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
