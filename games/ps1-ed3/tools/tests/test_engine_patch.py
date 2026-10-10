"""엔진 패치(안 B 타일 합성)의 계약 — 원본 없이 도는 회귀.

손 인코딩은 디스어셈블이 멀쩡해 보여도 틀린다(로드 지연 · 지연 슬롯). 여기서 조립·검산이 매번 돌고, 사전조건(원본 워드·sha1)이 안 맞으면
**쓰지 않고 선다**는 것을 박는다. 훅의 동작(모델 대조)은 `test_tile_hook.py`.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine_patch
import tile_hook
import typeset


class TestEnginePatch(unittest.TestCase):
    def test_hook_assembles_verifies_and_fits(self):
        """실제로 넣는 훅(조사 포함)은 `verify` 를 통과하고 죽은 함수 자리(1092B) 안에 든다."""
        p = engine_patch.PATCH["ed3"]
        for with_josa in (False, True):
            words, _ = tile_hook.hooks_b("ed3", 24, with_josa=with_josa)
            self.assertLessEqual(4 * len(words), p["dead_len"])

    def test_data_fits_its_region(self):
        p = engine_patch.PATCH["ed3"]
        half = [0xE5, 0x150, 0x151, 1, 2, 4, 5]
        markers = [(0x7000 + i, 1, 2, 0) for i in range(tile_hook.N_MARK)]
        blob = tile_hook.data_blob(p, half, markers, list(range(1, 40)))
        self.assertLessEqual(len(blob), p["data_len"])

    def test_state_fields_do_not_overlap(self):
        """🔴 상태 배치 — CURP(4B)와 IDX(2B)가 겹쳐 현재 타일 포인터가 깨졌던 적이 있다(해석기 테스트가 잡았다)."""
        spans = {
            "POS": (tile_hook.OFF_POS, 2),
            "ZADV": (tile_hook.OFF_ZADV, 2),
            "CURP": (tile_hook.OFF_CURP, 4),
            "LAST": (tile_hook.OFF_LAST, 2),
            "IDX": (tile_hook.OFF_IDX, 2),
            "SAVE": (tile_hook.OFF_RA, 20),
            "OUTA": (tile_hook.OFF_OUTA, 20),
            "SPB": (tile_hook.OFF_SPB, 20),
            "HALF": (tile_hook.OFF_HALF, 2 * tile_hook.HALF_SLOTS),
            "MK": (tile_hook.OFF_MK, 8 * tile_hook.N_MARK),
            "LC": (tile_hook.OFF_LC, 2),
            "LIM": (tile_hook.OFF_LIM, 2),
        }
        used = sorted((a, a + n, k) for k, (a, n) in spans.items())
        for (a0, b0, k0), (a1, _b1, k1) in zip(used, used[1:]):
            self.assertLessEqual(b0, a1, f"{k0} 와 {k1} 이 겹친다")
        self.assertLessEqual(used[-1][1], tile_hook.OFF_BL)

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


class TestResultWindows(unittest.TestCase):
    """승리·패배 창 열 수 상수 패치 — 디스어셈블로 검산한다(손인코딩)."""

    def test_encoding_disassembles_to_addiu_a2_cols(self):
        import capstone

        md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
        word = struct.pack("<I", 0x24060000 | engine_patch.RESULT_COLS)
        (ins,) = list(md.disasm(word, 0x80070E50))
        self.assertEqual((ins.mnemonic, ins.op_str.replace(" ", "")), ("addiu", f"$a2,$zero,{engine_patch.RESULT_COLS:#x}"))

    def test_precondition_stops_on_foreign_bytes(self):
        exe = bytearray(engine_patch._off(0x80071134) + 8)
        with self.assertRaises(SystemExit):
            engine_patch.apply_result_windows(exe, "ed3")


class TestSquareWindow(unittest.TestCase):
    def test_encodings_disassemble(self):
        import capstone

        md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
        got = []
        for addr, _orig, new in engine_patch.SQUARE_WINDOW["ed3"]:
            (ins,) = list(md.disasm(struct.pack("<I", new), addr))
            got.append((ins.mnemonic, ins.op_str.replace(" ", "")))
        self.assertEqual(got, [("addiu", "$a0,$zero,0x70"), ("addiu", "$a2,$zero,6")])


class TestLineupWindow(unittest.TestCase):
    def test_encoding_disassembles(self):
        import capstone

        md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
        addr, _orig = engine_patch.LINEUP_WINDOW["ed3"]
        (ins,) = list(md.disasm(struct.pack("<I", 0x24060000 | engine_patch.LINEUP_COLS), addr))
        self.assertEqual((ins.mnemonic, ins.op_str.replace(" ", "")), ("addiu", "$a2,$zero,0x11"))
