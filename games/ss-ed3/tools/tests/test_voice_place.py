"""음성 자막 배치 회귀 — **원본도 초안도 없이 돈다**(가짜 초안·타임라인을 만든다).

🔴 이 검사가 지키는 건 **자리 고르기**다. `delay` 는 「그 자리에 도착한 프레임」에서 재는데,
   자리를 한 칸 잘못 고르면 대기 밖으로 나가 자막이 엉뚱한 데서 뜬다. 바이트는 멀쩡하고
   빌드도 게이트도 통과하므로 **화면에서만 틀린다.**
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import voice_place as VP

DRAFT = """# V99 자막 초안 — 가짜

| 시각 | 화자 | 원문 | 우리 문안 |
| ---- | ---- | ---- | --------- |
| 0.0 | 크리스 | あ | 가나\\n다라 |
| 5.0 | ⚠ 쥬리오 | い | 마바 |
| 30.0 | 마을 노인 | う | 사아 |
"""

#   0.0초 자리 · 3.0초 자리(대기 600f = 10초) · 25.0초 자리(대기 300f)
TIMELINE = """     0.0초  0x1000  FF 42 00 63                ← 후킹 8B · 대기 6f(0.1초)
     0.1초  0x1010  FF 24 00 00                ← 후킹 8B · 대기 600f(10.0초)
    10.1초  0x1020  FF 07 00 00 00 00 00 00 00 ← 후킹 14B
    10.1초  0x1030  FF 24 00 01                ← 후킹 8B · 대기 300f(5.0초)
"""


class Place(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        os.makedirs(os.path.join(d, "timeline"))
        with open(os.path.join(d, "V99-draft.md"), "w", encoding="utf-8") as f:
            f.write(DRAFT)
        with open(os.path.join(d, "timeline", "V99.txt"), "w", encoding="utf-8") as f:
            f.write(TIMELINE)
        self.old = VP.DRAFT, VP.TIMELINE, VP.SCENES.get("V99")
        VP.DRAFT, VP.TIMELINE = d, os.path.join(d, "timeline")
        VP.SCENES["V99"] = ("MAP999", 0x1000)

    def tearDown(self):
        VP.DRAFT, VP.TIMELINE = self.old[0], self.old[1]
        VP.SCENES.pop("V99", None)
        self.tmp.cleanup()

    def test_skeleton_fills_speaker_and_duration(self):
        h = VP.skeleton("V99")
        self.assertEqual([x["who"] for x in h], ["크리스", "쥬리오", "마을 노인"])
        #   전역 인물만 번호가 붙는다 — 맵 이름표는 사람이 채운다
        self.assertEqual([x["speaker"] for x in h], [1, 0, None])
        #   표시 시간 = 다음 마디까지(간격 0.15) · 상한 6.0 · 마지막은 글자 수 어림
        self.assertEqual([x["dur"] for x in h], [4.8, 6.0, 1.4])
        self.assertEqual(h[0]["lines"], ["가나", "다라"])
        self.assertIn("_warn", h[1])  # ⚠ 는 초안에서 그대로 물려받는다
        self.assertNotIn("⚠", h[1]["who"])

    def test_place_picks_the_site_the_utterance_falls_in(self):
        #   t0 = 1000 프레임. 마디는 0.0 · 5.0 · 30.0 초
        frames = {"t0": 1000, "sites": {"0x1000": 1000, "0x1010": 1006, "0x1030": 1610}}
        h = VP.place("V99", {}, frames)
        self.assertEqual([x["off"] for x in h], [0x1000, 0x1010, 0x1030])
        #   0.0초 → 자리 그 자체(delay 0 은 아예 안 적는다)
        self.assertNotIn("delay", h[0])
        #   5.0초 = 1000 + round(5×59.83) = 1299 → 0x1010(1006) 안, delay 293
        self.assertEqual(h[1]["delay"], 293)
        self.assertEqual(h[1]["len"], 8)
        #   30.0초 = 2795 → 0x1030(1610) 안이지만 대기 300f 를 넘는다 → 할 일로 남긴다
        self.assertEqual(h[2]["delay"], 1185)
        self.assertIn("_todo", h[2])

    def test_place_reports_when_no_site_was_measured_before_the_line(self):
        h = VP.place("V99", {}, {"t0": 1000, "sites": {"0x1030": 1610}})
        self.assertIn("_todo", h[0])
        self.assertIsNone(h[0]["off"])

    def test_scene_table_covers_every_scene_and_has_no_duplicate_sites(self):
        #   자리는 커밋되는 곳이 여기뿐이다 — 표가 상하면 다시 찾아야 한다
        VP.SCENES.pop("V99", None)
        self.assertEqual(len(VP.SCENES), 20)
        self.assertEqual(len({(m, o) for m, o in VP.SCENES.values()}), 20)
        for name, (m, off) in VP.SCENES.items():
            self.assertRegex(name, r"^V\d\d$")
            self.assertRegex(m, r"^MAP\d{3}$")
            self.assertTrue(0 < off < 0x40000, f"{name}: 자리가 이상하다 {off:#x}")


if __name__ == "__main__":
    unittest.main()
