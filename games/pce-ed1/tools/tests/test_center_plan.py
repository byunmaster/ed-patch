"""입장 배너·HUD 지명 칸 가운데 맞춤(번역 규칙 2-8, 마스터 11-05) — 쏠림이 반 칸(6px) 안인지."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import center_plan as C
import messages as M


class CenterTest(unittest.TestCase):
    def test_banner_nearest_center(self):
        """규칙 2-8(마스터 11-09 「최대한 가운데」): 가능한 앞 공백 조합 중 가운데에 가장 가까운 것, 같을 때만 왼쪽. 글자 코드(공백 포함) 7개·폭 96px 안."""
        rows = [(k, v["t"]) for k, v in M.load_translations(0).items() if v.get("raw")]
        self.assertGreater(len(rows), 40)
        for k, t in rows:
            name = t.strip(" " + C.HALF_MARK)
            if C.JOIN_MARK in t:  # 글자 뒤 반 칸을 앞 글자 변형 코드로 합친 이름(엘아스타 마을) — 코드 7개 안, 쏠림은 가능한 중 최근접
                self.assertLessEqual(len(t.replace(C.JOIN_MARK, "")), 7, t)
                self.assertLessEqual(abs(C.banner_shift(t)), 2.5, t)
                continue
            self.assertLessEqual(len(t), 7, t)
            feas = []
            for kk in range(4):
                for hh in range(4):
                    if 12 * kk + 4 * hh + C._w(name) <= 96 and kk + hh + len(name) <= 7:
                        feas.append((round(abs(12 * kk + 4 * hh + C._w(name) / 2 - C.BANNER_C), 3), 12 * kk + 4 * hh + C._w(name) / 2 - C.BANNER_C))
            best = min(feas)
            self.assertEqual((round(abs(C.banner_shift(t)), 3), C.banner_shift(t)), best, (k, t))

    def test_banner_spaced_forms(self):
        """입장 배너는 정본 일반 꼴(띄어쓰기, 성·섬 붙임)이다 — 안의 공백은 반 칸(4px) 표시."""
        ts = {v["t"].strip(" " + C.HALF_MARK) for v in M.load_translations(0).values() if v.get("raw")}
        for want in ("엘아스타" + C.JOIN_MARK + "마을", "쟈그리" + C.HALF_MARK + "폐광", "네리아" + C.HALF_MARK + "항구", "니르기드성"):
            self.assertIn(want, ts)
        self.assertFalse([t for t in ts if " " in t])  # 전각(12px) 공백이 이름 안에 없다

    def test_best_lead_rule(self):
        # 4글자(48px): 앞 1칸 → −2px(HUD), 5글자: 앞 1칸 → +4px
        self.assertEqual(C.best_lead("엘아스타", C.HUD_C, 2)[0], 1)
        self.assertAlmostEqual(C.best_lead("루디아성", C.BANNER_C, 3)[1], 3.5)

    def test_hud_nearest_center(self):
        # 규칙 2-8(마스터 11-09): HUD 지명도 가능한 위치 중 가장 가까운 쪽, 같을 때만 왼쪽
        for n in ("엘아스타", "루디아", "크루즈마을", "베르가광산", "쟈그리의폐광", "론도항구", "핀요새"):
            k, h, sh = C.best_lead_half(n, C.HUD_C, len(n) * 2)
            alts = [12 * kk + 8 * hh + C._w(n) / 2 - C.HUD_C for hh in (0, 1) for kk in range(0, (12 - len(n) * 2 - (2 if hh else 0)) // 2 + 1) if 12 - len(n) * 2 - (2 if hh else 0) >= 0]
            self.assertEqual(round(abs(sh), 3), min(round(abs(a), 3) for a in alts), n)

    def test_hud_half_clears_stale_column(self):
        # 시작 열을 $1C 로 밀면 앞 이름이 $1B 열에 남긴 BAT 항목이 새 이름 첫 타일을 한 번 더 그린다(「ㄴ네리아항구」 11-08) —
        # 코드가 BAT 행 24·25 의 $1B 열(VRAM $061B·$065B)을 패널 빈 칸($0145)으로 쓰는지
        import hud_half

        c = hud_half.code()
        self.assertLessEqual(len(c), hud_half.CODE_LEN)
        for needle in (b"\xa9\x1b", b"\xa9\x5b", b"\xa0\x45", b"\xa0\x06"):
            self.assertIn(needle, c)

    def test_card_packed_shift(self):
        """장 끝 카드 가운데(마스터 11-09): 「끝」은 잉크를 3px, 종장 제목은 2px 오른쪽으로 구운 전용 글자 — 칸 수가 늘지 않는다."""
        import font

        self.assertEqual(len(font._packed_cells("끝")), 2)
        self.assertEqual(len(font._packed_cells("종장  그리고 영웅들의 전설")), 13)
        self.assertEqual(font.PACKED_DX, {"종장  그리고 영웅들의 전설": 2, "끝": 3})


if __name__ == "__main__":
    unittest.main()
