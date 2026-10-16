"""데이터 선택 화면(뱅크 0x73) — 슬롯 줄의 글꼴 지정(`04` `06`) 보존 · 장 글자 표 · 자리표 쓰기 옮기기(원본 없이 돈다: 가짜 뱅크)."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import layout
import systext

ROW = bytes.fromhex("15 85 06 4c 14 1a 20 04 82 77 8f cd 06 20 04 1a 02 ac 1b 15 85 8e 9e 8a d4 14 1b 15 85 95 aa 14".replace(" ", ""))
EXTRA = {"Ｘ章": "Ｘ장", "時間": "시간", "分": "분", "序@장글자": "서"}


def _orig(bank73: bytes | None = None) -> bytes:
    """가짜 본 프로그램 — 0xFF 로 채우고(패딩 검사 통과) 0x00 칸만 0. `bank73` 이 있으면 그 뱅크를 갈아 끼운다."""
    orig = bytearray(b"\xff" * (layout.BANK * layout.NBANKS))
    for bank, off, ln in layout.ZERO_PADDING:
        a = (bank - layout.BANK0) * layout.BANK + off
        orig[a : a + ln] = bytes(ln)
    if bank73:
        a = (0x73 - layout.BANK0) * layout.BANK
        orig[a : a + layout.BANK] = bank73
    return bytes(orig)


class Row(unittest.TestCase):
    def _tr(self):
        with mock.patch.object(systext, "_extra", return_value=EXTRA):
            return systext.translate(ROW, "슬롯줄", set())

    def test_글꼴_지정_코드가_안_사라진다(self):
        plan = self._tr()
        self.assertIsNotNone(plan)
        out = systext.render(plan, font.GlyphTable())
        # 원문의 제어 바이트(04 · 06 · 14 · 15 85 · 1A · 1B · 02 AC)가 같은 순서로 남는다
        ctrl = lambda b: [x for x in b if x in (0x04, 0x06, 0x14, 0x1A, 0x1B)]
        self.assertEqual(ctrl(out), ctrl(ROW))

    def test_자리표_Ｘ_는_원문_바이트로_남고_길이가_같다(self):
        out = systext.render(self._tr(), font.GlyphTable())
        self.assertIn(b"\x82\x77", out)
        self.assertEqual(len(out), len(ROW))  # 한글 한 글자 = 한자 한 글자(2바이트)

    def test_자리표_쓰기는_새_문자열의_Ｘ_자리를_가리킨다(self):
        """코드가 장 글자를 덮어 쓰는 주소(`$6777` · `$6778`)가 새 문자열의 `82 77` 위치다."""
        raw_bank = bytearray(b"\xff" * layout.BANK)
        off = 0x076F
        raw_bank[off : off + len(ROW) + 1] = ROW + b"\x00"
        # 코드: STA $6777 · STA $6778 (원문 Ｘ 위치 = off + 8 · 9)
        for i, k in enumerate((8, 9)):
            a = 0x6000 + off + k
            raw_bank[0x100 + 3 * i : 0x100 + 3 * i + 3] = bytes([0x8D, a & 0xFF, a >> 8])
        prog = layout.Prog(_orig(bytes(raw_bank)))
        newb = systext.render(self._tr(), font.GlyphTable()) + b"\x00"
        systext.INTERIOR_WARN.clear()
        systext._remap_interior(prog, 0x73, off, ROW, newb[:-1], off)
        self.assertEqual(systext.INTERIOR_WARN, [])


class Chapter(unittest.TestCase):
    def test_장_글자_표는_글리프_또는_반각_숫자_한_칸이다(self):
        raw = bytes.fromhex("8f98 8250 8251 8252 8253 8f49 8f49".replace(" ", ""))
        bank = bytearray(b"\xff" * layout.BANK)
        bank[0x0761 : 0x0761 + 14] = raw
        prog = layout.Prog(_orig(bytes(bank)))
        with mock.patch.object(systext, "_extra", return_value=EXTRA):
            systext._chapter_table(prog, font.GlyphTable())
        out = prog.writes[(0x73, 0x0761)][0]
        self.assertEqual(len(out), 14)
        self.assertEqual(out[0], 0xF0)  # 序 → 서(글리프 코드 2바이트)
        self.assertEqual(out[2:10], raw[2:10])  # 전각 숫자 １~４ 는 그대로(마스터 10-16)
        self.assertEqual(out[10], 0xF0)  # 終 → 종(정본 키 47cacfb9a 이후 글리프로 바뀐다)
        self.assertNotEqual(out[10:12], raw[10:12])


if __name__ == "__main__":
    unittest.main()
