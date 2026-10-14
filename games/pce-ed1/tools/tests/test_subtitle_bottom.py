"""오프닝 자막 세로 자리 — 한 줄은 두 줄 자막의 둘째 줄 높이(번역 규칙 2-14, 마스터 2026-10-15). 원본 없이 도는 부분."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import opening_sub as O


class SubtitleBottom(unittest.TestCase):
    def test_one_line_alignment_follows_layout(self):
        # 상단 배치 한 줄 = 위 맞춤(첫 줄 높이), 하단 배치 한 줄 = 두 줄 쪽 둘째 줄 높이(바닥) — 번역 규칙 2-14
        top = O.page_y_table([(0,), (0, 1), (0, 1, 2)], ["top"] * 3)
        self.assertEqual(top[0], top[1])
        self.assertEqual(top[1], top[2])
        bot = O.page_y_table([(0, 1), (0, 1, 2)], ["bottom"] * 2)
        self.assertEqual(bot[0], bot[1] + O.LINE_H)  # 하단 배치는 줄 수와 무관하게 마지막 줄 바닥 고정(한 줄 하단 쪽은 현재 없음 — page_y 가 한 바이트를 넘는다)

    def test_middle_layout_is_untouched(self):
        (one,) = O.page_y_table([(0,)], ["middle"])
        self.assertEqual(one, 64 + 120 - O.GLYPH_ROWS // 2)


class SubtitleCentered(unittest.TestCase):
    def test_line_is_centered_on_frame_center_within_tolerance(self):
        # 줄마다 가운데(2-14) — **글자 잉크**(줄 끝 「.」「,」「…」 제외)의 가운데가 프레임 가운데 ±0.5px(홀수 폭의 반 단위는 왼쪽 내림).
        #   전진 합으로 재던 옛 방식은 줄마다 −7~+1px 흔들렸다(별밤 캡처 실측, 마스터 10-15).
        origin = O.CENTER_X - 16 * O.SPR_PER_PAIR
        for t in ("역사가 되풀이되지 않도록.", "아주 먼 옛날… 아니", "국왕 아스엘의 죽음…", "그리고 10여 년의 세월이 흘렀다…"):
            lead, r = O.line_geom(t)
            m, _e = O.render_line(t.rstrip(O.TRAIL_PUNCT))
            cols = [i for i in range(m.shape[1]) if m[:, i].any()]
            ctr = origin + 16 * lead + r + (cols[0] + cols[-1]) / 2
            self.assertLessEqual(abs(ctr - O.CENTER_X), 0.5, t)

    def test_trailing_punct_is_excluded_from_width(self):
        self.assertEqual(O.line_geom("가나다라마바사.")[0], O.line_geom("가나다라마바사")[0])  # 끝 마침표는 여백(칸)을 안 바꾼다

    def test_strip_cells_plus_lead_fit_the_sprites(self):
        for t in ("가나다라마바사아자차카타파하", "역사가 되풀이되지 않도록."):
            lead, _r = O.line_geom(t)
            self.assertLessEqual(lead + len(O.strip_cells(t)), 2 * O.SPR_PER_PAIR, t)


if __name__ == "__main__":
    unittest.main()
