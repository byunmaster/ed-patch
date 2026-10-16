"""자막 전용 반각 글꼴(네오둥근모) — 글꼴 태그 덧붙임과 전각 말줄임표 글리프."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import captions
import hangul


class FontTags(unittest.TestCase):
    def test_wraps_narrow_font_once(self):
        s = "<fd85><fe10>안녕.<fd80><06>"
        out = captions.font_tags(s)
        # 글꼴에 따라 피치가 갈린다 — 갈무리11 볼드 = 피치 14(`<fe0e>`), 그 밖(갈무리14·네오) = 16 그대로
        pitch = "<fe0e>" if captions.FONT_SRC in ("galmuri11bold", "galmuri11") else "<fe10>"
        self.assertEqual(out, f"<fd85><fd05>{pitch}안녕.<fd80><fd00><06>")
        self.assertEqual(captions.font_tags(out), out)  # 두 번 불러도 같다

    def test_plain_dialog_untouched(self):
        self.assertEqual(captions.font_tags("안녕."), "안녕.")


class DigitWiden(unittest.TestCase):
    def test_digit_runs_get_wider_pitch_only(self):
        out = captions.widen_digits("<fe0e>왕자는 6살. 16살<fd80>")
        self.assertEqual(out, "<fe0e>왕자는 <fe12>6<fe0e>살. <fe12>16<fe0e>살<fd80>")

    def test_tag_digits_untouched(self):
        self.assertEqual(captions.widen_digits("<fd85><fe0e>안녕"), "<fd85><fe0e>안녕")

    # 알려진 맞닿음 — 「?」 잉크 7열 = 전진 7. 숫자만 넓히라는 지시(마스터 10-13)라 그대로 두고 관리자에 알렸다.
    KNOWN_TOUCHING = {"?"}

    def test_narrow_ink_columns_below_advance(self):
        """반각 겹침 게이트 — 자막에 나오는 반각 글자는 **잉크 열 < 전진폭**(최소 1px 틈). 다음 글자의 테두리가
        오른쪽 끝 잉크를 먹는다(10-13 「10여」의 「0」). 전진 = 피치 14/2 (+ 숫자는 DIGIT_EXTRA)."""
        import json

        cap = json.load(open(Path(__file__).resolve().parents[2] / "textmap" / "captions.json", encoding="utf-8"))
        import re

        chars = {c for e in cap.values() for c in re.sub(r"<[^>]*>", "", e.get("ours", "")) if 0x20 < ord(c) < 0x80}
        for c in sorted(chars):
            g = hangul.neodgm_fill(c, 16, 16)
            cols = [x for x in range(16) if any(row[x] for row in g)]
            width = cols[-1] + 1  # 칸 0열부터 센 오른쪽 끝
            adv = 7 + (captions.DIGIT_EXTRA if c.isdigit() else 0)
            if c in self.KNOWN_TOUCHING:
                continue
            gap = 2 if c.isdigit() else 1  # 숫자는 눈에 보이는 틈 2열(공통 규칙 1-5), 그 밖은 최소 1열
            self.assertLessEqual(width + gap, adv, f"{c!r}: 잉크 {width}열 + 틈 {gap} > 전진 {adv}")


class EllipsisFull(unittest.TestCase):
    def test_three_square_dots_spread_over_cell(self):
        g = hangul.ellipsis_full(16)
        ink = [(x, y) for y, row in enumerate(g) for x, v in enumerate(row) if v]
        self.assertEqual(len(ink), 12)  # 2×2 점 셋
        self.assertEqual({y for _, y in ink}, {10, 11})  # 네오둥근모 마침표와 같은 행
        self.assertEqual(sorted({x for x, _ in ink}), [2, 3, 7, 8, 12, 13])


if __name__ == "__main__":
    unittest.main()
