"""메시지 밖 바이트 보존 게이트 + 빈 행 제거 패치의 옵코드 피연산자 보호(11-22 씬 106 `14 07 01` → `14 07 18` 회귀)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_gap_bytes as G
import translate as T


class GapBytes(unittest.TestCase):
    # 씬 106 +0x854 꼴: 앞 글 `…。` `00`(종료) 뒤에 `14 07 01`(깃발 0x0107 세트) 그리고 글
    ORIG = bytes.fromhex("8142" "00" "140701" "82e282a0")

    def test_operand_change_is_forbidden(self):
        new = bytearray(self.ORIG)
        new[5] = 0x18  # `01` → `18` — 피연산자가 바뀐다
        o = bytes(self.ORIG)
        self.assertTrue(G.operand_tail_hit(o, 5, 5))
        self.assertEqual(G.classify(o, bytes(new), 5, 5), "?")

    def test_real_blank_row_is_allowed(self):
        # `…07 01` 뒤에 글 — 진짜 종료+개행(씬 0 꼴)은 E 갈래
        o = bytes.fromhex("89c6" "07" "01" "835a838a")
        n = bytearray(o)
        n[3] = 0x18
        self.assertEqual(G.classify(o, bytes(n), 3, 3), "E")
        self.assertFalse(G.operand_tail_hit(o, 3, 3))

    def test_blank_row_patch_skips_flag_operand_in_scene_106(self):
        import containers

        for c in containers.scan():
            for b in c["blocks"]:
                if b["id"] == 106:
                    self.assertEqual(T.blank_row_patches(b["data"]), [])
                    return
        self.skipTest("원본 없음")


if __name__ == "__main__":
    unittest.main()
