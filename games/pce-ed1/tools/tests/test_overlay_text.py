"""씬 54 코드 오버레이 인라인 대사(`overlay_text`) — 제자리 교체 계약(같은 길이 · 종료 `0A` 유지 · 원문 검증 · 넘치면 죽음). 원판이 있으면 실제 오버레이로 전수."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import font
import overlay_text as O


def _table():
    import glyphdyn
    import translate

    chars = glyphdyn.forced_chars() | (translate.all_glyph_chars() & set(font._order_canon()))
    return font.build_table(chars)[0]


class OverlayText(unittest.TestCase):
    def test_every_string_fits_and_keeps_terminator(self):
        data = O.load()
        self.assertEqual(len(data), 12)
        tab = _table()
        for off, v in data.items():
            new = font.encode(v["t"], tab, msg=True)
            self.assertLessEqual(len(new) + 1, v["jp_len"], (off, v["t"]))  # +1 = 끝 줄바꿈
            for line in v["t"].split("\n"):
                import typeset

                self.assertLessEqual(typeset.px(line), 156, (off, line))  # 13칸 틀

    def test_apply_in_place_on_synthetic_overlay(self):
        tab = _table()
        data = O.load()
        # 원문 바이트는 저장소에 없다 — 원판 오버레이가 있으면 그것으로, 없으면 계약 시험은 건너뛴다
        try:
            import zone_image

            ov = bytearray(zone_image.overlay())
        except Exception:
            self.skipTest("원판 없음")
        out = O.apply(bytes(ov), tab)
        self.assertEqual(len(out), len(ov))
        for off, v in data.items():
            end = off + v["jp_len"]
            self.assertEqual(out[end], 0x0A)
            self.assertEqual(out[off : off + 2], font.encode(v["t"], tab, msg=True)[:2])
        self.assertEqual(O.jp_left(out), [])

    def test_mismatch_raises(self):
        with self.assertRaises(O.OverlayTextError):
            O.apply(bytes(4000), _table())

    def test_jp_left_flags_kana_run(self):
        self.assertTrue(O.jp_left(b"\x00" + "ここでは".encode("cp932") + b"\x0a"))


if __name__ == "__main__":
    unittest.main()
