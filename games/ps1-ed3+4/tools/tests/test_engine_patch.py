"""엔진 패치(공백 8px)의 계약 — 원본 없이 도는 회귀.

손 인코딩은 디스어셈블이 멀쩡해 보여도 틀린다(로드 지연 · 지연 슬롯). 여기서 조립·검산이
매번 돌고, 사전조건(원본 워드·sha1)이 안 맞으면 **쓰지 않고 선다**는 것을 박는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine_patch
import typeset


class TestEnginePatch(unittest.TestCase):
    def test_hooks_assemble_and_verify(self):
        words, labels = engine_patch.hooks("ed3", 0xE5, 8)
        p = engine_patch.PATCH["ed3"]
        self.assertLessEqual(4 * len(words), p["table_off"])  # 표를 침범하지 않는다
        # 틀 루틴은 본 훅 뒤에 — `lhu v1,0x14(fp)` 로 시작한다(원래 그 자리의 명령)
        k = (labels["framew"] - p["dead"]) // 4
        self.assertEqual(words[k], p["frame_edge_orig"][0])
        # 막대 루틴 둘은 같은 꼬리(`sh v1,0x2e(fp)`)로 나간다
        self.assertEqual(words[(labels["bar_out"] - p["dead"]) // 4 + 1], p["frame_bar_orig"][1])
        # 본 훅의 끝은 폰트 베이스 복원 — `lui a1,0x800a` · `jr ra` · `addiu a1,a1,-0x1e90`
        self.assertEqual(words[k - 3], 0x3C05800A)
        self.assertEqual(words[k - 2], 0x03E00008)
        self.assertEqual(words[k - 1], 0x24A5E170)

    def test_frame_stays_24_columns(self):
        """격자는 32칸이지만 틀은 24칸 — 유저 실측: 틀이 화면 오른쪽을 뚫었다."""
        self.assertEqual(engine_patch.FRAME_COLS, 24)
        self.assertEqual(engine_patch.asm("lhu v1, 0x14(fp)", 0)[0][0], 0x97C30014)
        self.assertEqual(engine_patch.asm("addiu v1, v0, 0xc\nsh v1, 0x2e(fp)", 0)[0], [0x2443000C, 0xA7C3002E])

    def test_cols_matches_typeset(self):
        """격자 열 수는 조판 상한과 같은 값이어야 한다 — 어긋나면 조판은 통과하고 화면이 잘린다."""
        self.assertEqual(engine_patch.COLS, typeset.COLS["ed3"])

    def test_verify_catches_load_delay(self):
        words, _ = engine_patch.asm("lw t0, 0(a0)\naddiu t1, t0, 1\njr ra\nnop", 0x80010000)
        with self.assertRaises(AssertionError):
            engine_patch.verify(words, 0x80010000)

    def test_verify_catches_branch_in_delay_slot(self):
        words, _ = engine_patch.asm("jr ra\nj 0x80010000\nnop", 0x80010000)
        with self.assertRaises(AssertionError):
            engine_patch.verify(words, 0x80010000)

    def test_asm_encodings(self):
        """디스어셈블로 읽은 원본 워드를 그대로 낸다 — 인코더가 틀리면 여기서 선다."""
        cases = {
            "lui a1, 0x800a": 0x3C05800A,
            "addiu a1, a1, -0x1e90": 0x24A5E170,
            "lw v0, 0xc(fp)": 0x8FC2000C,
            "addiu a2, zero, 0x18": 0x24060018,
            "sh v1, 8(v0)": 0xA4430008,
            "div zero, t4, t3": 0x018B001A,
            "jr ra": 0x03E00008,
        }
        for src, want in cases.items():
            self.assertEqual(engine_patch.asm(src, 0)[0][0], want, src)

    def test_apply_refuses_foreign_exe(self):
        """사전조건 — 원본이 아니면 한 바이트도 안 쓴다."""
        exe = bytearray(0xAF000)
        with self.assertRaises(SystemExit):
            engine_patch.apply(exe, "ed3", {" ": 0xE5})
        self.assertEqual(exe, bytearray(0xAF000))

    def test_no_patch_for_ed4_yet(self):
        self.assertIsNone(engine_patch.apply(bytearray(16), "ed4", {" ": 1}))


if __name__ == "__main__":
    unittest.main()
