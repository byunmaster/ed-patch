"""오마케 한글 훅(`omake_font.py`) — 어셈 크기·진입점·타일 왕복·글리프 블록 (원본 없이 도는 부분)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import font
import omake_font as O


def _extras():
    ex = json.loads(
        (common.GAME_DIR / "script" / "sys" / "extras.json").read_text(encoding="utf-8")
    )
    return {k: v for k, v in ex.items() if not k.startswith("_")}


class OmakeFont(unittest.TestCase):
    def test_hook_fits_pocket_and_entry_points_are_ordered(self):
        code, ohook, oinit = O._assemble()
        self.assertLessEqual(len(code), O.CODE_ROOM)
        self.assertEqual(ohook, O.CODE_ADDR)
        self.assertTrue(ohook < oinit < O.CODE_ADDR + len(code))
        self.assertEqual(code[:2], b"\xa5\xf9")  # LDA $F9 — 리드부터 본다
        self.assertTrue(code.endswith(b"\x4c\x4d\x40"))  # OINIT 끝 = JMP $404D(모듈 입구 원래 호출)

    def test_tile_codec_roundtrip(self):
        px = [[(x * 3 + y * 5) % 16 for x in range(8)] for y in range(8)]
        self.assertEqual(O._tile_decode(O._tile_encode(px), 0), px)

    def test_cells_are_assigned_by_order_and_decode_back(self):
        O._CELLS.clear()
        enc = O.encode_item("가 나")  # 가(12) + 공백(6) + 나(12) = 30px → 칸 3개
        self.assertEqual(len(enc), 6)
        self.assertEqual(len(O._CELLS), 3)
        for i in range(0, 6, 2):
            idx = (enc[i] - O.LEADS[0]) * font.PER_LEAD + enc[i + 1] - font.TRAIL0
            self.assertEqual(list(O._CELLS.values())[idx], idx)
        # 같은 칸은 하나로 합친다
        O.encode_item("가 나")
        self.assertEqual(len(O._CELLS), 3)

    def test_half_space_is_shorter_than_full_space(self):
        # 공백 둘 = 12px: 「가 나 다」는 48px = 4칸 — 전각 공백(5칸)보다 한 칸 짧다
        self.assertEqual(len(O.encode_item("가 나 다")), 2 * 4)
        self.assertEqual(O.px_width("가 나 다"), 48)

    def test_wrap_keeps_lines_within_cap_and_respects_explicit_breaks(self):
        text = "아주 긴 문장을 어절 단위로 나누어 서너 줄에 담는다\n둘째 문단"
        lines = O.wrap_words(text)
        self.assertTrue(all(O.px_width(ln) <= 156 for ln in lines))
        self.assertEqual(lines[-1], "둘째 문단")
        self.assertEqual(" ".join(lines[:-1]), text.split("\n")[0])

    def test_dex_descriptions_fit_four_lines(self):
        dex = json.loads(
            (common.GAME_DIR / "script" / "sys" / "dex.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(dex["desc"]), O.DEX_COUNT)
        for i, t in enumerate(dex["desc"]):
            lines = O.dex_lines(i, t)
            self.assertLessEqual(len(lines), O.DEX_MAX_LINES, t)
            self.assertTrue(all(O.px_width(ln) <= 156 for ln in lines), t)

    def test_dex_sentences_are_split_by_newline(self):
        # 두 문장 이상인 설명은 문장 경계마다 개행으로 나뉜다(마스터 10-14) — 문장 끝(. ! ?) 뒤에 공백이 남지 않는다.
        dex = json.loads(
            (common.GAME_DIR / "script" / "sys" / "dex.json").read_text(encoding="utf-8")
        )["desc"]
        for t in dex:
            self.assertNotRegex(t, r"[.!?] ", t)
        self.assertEqual(sum("\n" in t for t in dex), 21)  # 두 문장 이상인 21건

    def test_ligature_is_used_only_by_the_turtle_record(self):
        dex = json.loads(
            (common.GAME_DIR / "script" / "sys" / "dex.json").read_text(encoding="utf-8")
        )["desc"]
        used = [
            i for i, t in enumerate(dex) if any(O.LIGATURE in ln for ln in O.dex_lines(i, t))
        ]
        self.assertEqual(used, [28])
        self.assertEqual(O.dex_lines(28, dex[28])[-1].count(O.LIGATURE), 1)
        self.assertEqual(O.px_width(O.dex_lines(28, dex[28])[-1]), 156)
        # 합자 글리프 = 「다」 + 12번째 열의 점 하나(다른 픽셀은 그대로)
        g, d = O._ligature_glyph(), font.glyph("다")
        diff = [i for i in range(24) if g[i] != d[i]]
        self.assertEqual(len(diff), 1)

    def test_block_size_and_codes_in_range(self):
        O._CELLS.clear()
        _code, _oh, _oi, block, n = O.build({}, _extras())
        self.assertEqual(len(block), O.GLYPH_SECTORS * common.USER)
        self.assertEqual(n, len(O._CELLS))
        self.assertLessEqual(n * O.STRIDE, len(block))

    def test_dex_pointer_table_follows_new_record_starts(self):
        # 원판 표는 화면 순서(순열)라 레코드 순서와 다르다 — 새 표도 같은 순열에 새 시작 값이어야 한다(안 쓰면 이름이 엉뚱한 바이트에서 읽힌다).
        dex = json.loads(
            (common.GAME_DIR / "script" / "sys" / "dex.json").read_text(encoding="utf-8")
        )["desc"]
        new, starts = O._dex_build(dex)
        tab = O.dex_pointer_table(dex)
        self.assertEqual(len(tab), 2 * O.DEX_COUNT)
        ptrs = [int.from_bytes(tab[i : i + 2], "little") for i in range(0, len(tab), 2)]
        self.assertEqual(sorted(ptrs), sorted(O.DEX_PTR_BASE + s for s in starts))
        for p in ptrs:
            self.assertEqual(new[p - O.DEX_PTR_BASE - O.DEX_OFF], 0x1F)


if __name__ == "__main__":
    unittest.main()
