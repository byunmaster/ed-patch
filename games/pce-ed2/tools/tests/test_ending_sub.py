"""대관식 자막 쪽 — 마스터 10-16 화면 지적 중 쪽 모양·시각에 걸린 것."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ending_sub as e

class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = [p for p in e.build_pages() if p["lines"] != ["(청소)"]]

    def _page(self, first_line, after=0.0):
        return next(p for p in self.pages if p["t0"] >= after and p["lines"][0].startswith(first_line))

    def test_띠_안_짧은_문장은_한_줄이다(self):
        """마스터 10-16 「그림 있는 부분은 깨질 수 있으니 까만 부분만 한 줄로」."""
        for head in (
            "아그니쟈가 그런 말을요?",
            "인간들에게 미래를 맡긴다고.",
            "어째서 그렇게 슬픈 일이 일어난 걸까요.",
            "아마 아무도 나쁜 게 아닐 거야.",
            "처음에 사소한 오해가 있었을 뿐이야.",
            "아그니쟈는 마지막에 이런 말도 했어.",
            "앞으로도 힘이 되어 줄 거지?",
        ):
            self.assertEqual(self._page(head)["lines"], [head])

    def test_쪽마다_VRAM_블록이_모자라지_않다(self):
        for p in self.pages:
            self.assertGreaterEqual(len(p["blocks"]), (len(p["cells"]) + 1) // 2, p["lines"])

    def test_음성_뒤_0점5초_꼬리가_장면_전환을_넘지_않는다(self):
        """음성이 전환 앞에서 끝나는 쪽은 t1 + 0.5초 가 전환 앞이다(마스터 10-16 「0.5초 대기 때문에 다음 장면에 남은 것」). 음성이 전환을 넘어 이어지는 쪽(t1 > 전환)은 해당 없다."""
        for p in self.pages:
            for t in e.TRANSITIONS:
                if p["t0"] < t and p["t1"] < t:
                    self.assertLess(e.end_time(p["t1"]), t, (p["lines"], t))
        self.assertAlmostEqual(e.end_time(84.2), 84.43 - e.CUT_GUARD, places=3)  # 「우리가 힘내서…」(마스터 10-16 #6)

    def test_신디는_세_번째_드래곤_장면의_음성_시각이다(self):
        p = self._page("신디!")
        self.assertAlmostEqual(p["t0"], 259.25, places=2)
        self.assertGreater(p["t0"], 254.89)  # 포효 구간(254.5~255.9)이 아니다

    def test_하늘_배경_장면은_위_배치다(self):
        """마스터 10-16 「하늘장면은 다 올리는 게 일관성 있을 것 같아」 — 군중 인사 · 드래곤 · 레이시아 클로즈업 · 마지막 장면 전부 위(y16, 위 여백 16px)."""
        for head in ("모두,", "고마워.", "신디!", "레이시아!", "기대하고 있어.", "당신이라면 분명", "고마워, 레이시아.", "앞으로는 지상의 인간과", "새로운 세계가"):
            p = self._page(head, after=237.0)
            self.assertEqual(p["y0"], e.Y0_TOP, head)

    def test_군중_9_첫쪽_줄_나눔은_해_주신이_첫_줄이다(self):
        """마스터 「문안을 위로 올리는 게 낫지 않을까」 — 둘째 줄이 짧아져(90px) 머리 픽셀 차이 0 (시험 실측 10-16)."""
        p = self._page("그러고 보니 옛날에")
        self.assertEqual(p["lines"], ["그러고 보니 옛날에 아버지가 해 주신", "이야기가 있어."])
        self.assertEqual(p["y0"], e.Y0_TOP)

    def test_클로즈업_셋은_아래_배치다(self):
        """마스터 「클로즈업 3장면은 아래로」 — 플로라·란도 클로즈업은 머리에 글자가 얹혀 바닥 배치(한 줄은 둘째 줄 높이). 레이시아 「레이시아!」만 10-16 마스터 「이전 다음 자막이 다 위쪽이라」로 위."""
        for head in ("플로라,", "란도,"):
            self.assertGreater(self._page(head, after=237.0)["y0"], 150, head)

    def test_마지막_장면_두_쪽은_한_줄이다(self):
        """마스터 10-16 「두쪽 한줄 오케이」 — 위쪽 배치 폭 상한(244)으로 242px 줄도 한 줄."""
        self.assertEqual(self._page("당신이라면 분명 좋은 지도자가 될 거야.")["lines"], ["당신이라면 분명 좋은 지도자가 될 거야."])
        self.assertEqual(self._page("새로운 세계가 시작되는 거야.")["lines"], ["새로운 세계가 시작되는 거야."])

    def test_드레이크는_앞_장면에만_둔다(self):
        """마스터 10-16 「(나)로 하자」 — 앞 장면 「드레이크 씨도」, 띠 장면 「프래드 씨도 / 사실은…」."""
        self.assertEqual(self._page("드레이크 씨도")["lines"], ["드레이크 씨도"])
        self.assertEqual(self._page("프래드 씨도")["lines"], ["프래드 씨도", "사실은 좋은 분들인데"])
        self.assertFalse(any("드레이크 씨도 프래드" in " ".join(p["lines"]) for p in self.pages))

    def test_데모_음성에_맞춰_뜬다(self):
        self.assertAlmostEqual(self._page("하지만 그만큼")["t0"], 97.05, places=2)  # 「でも」 파형 97.09~97.43


if __name__ == "__main__":
    unittest.main()
