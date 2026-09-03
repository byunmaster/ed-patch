"""`mednafen_cfg.py` 와 그걸 쓰는 정본 둘(키·영상). **cfg 없이** 문자열로 돈다.

🔴 지키는 것 셋.

1. **없는 설정은 조용히 안 만든다.** mednafen 이 이름을 바꾸면(1.32 → 다음 판) 우리 표만
   낡는데, 없는 줄을 덧붙이면 cfg 엔 들어가고 mednafen 은 「unknown setting」으로 흘린다 —
   **아무도 모르는 채 안 듣는 설정**이 된다. 그래서 `missing` 으로 세어 화면에 띄운다.
2. **키와 영상이 같은 설정을 다투지 않는다.** 실행 직전에 둘을 잇달아 돌리므로 이름이
   겹치면 뒤에 도는 쪽이 이긴다 — 조용히.
3. **영상 정본에 CRT 후처리가 없다.** 「실기 규격」의 뜻이 흔들리면 검수 화면이 흐려진다
   (유저 확정 2026-09-02: 주사선·셰이더는 실기가 아니라 실기를 찍은 사진이다).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mednafen_cfg  # noqa: E402
import mednafen_keys  # noqa: E402
import mednafen_video  # noqa: E402

CFG = "ss.videoip 1\nss.stretch aspect_mult2\nss.scanlines 0\n"


class TestApply(unittest.TestCase):
    def test_counts_and_rewrite(self):
        text, changed, same, missing = mednafen_cfg.apply(
            CFG, {"ss.videoip": "0", "ss.scanlines": "0", "ss.nosuch": "1"}
        )
        self.assertEqual((changed, same, missing), (1, 1, 1))
        self.assertIn("ss.videoip 0\n", text)
        self.assertNotIn("ss.nosuch", text)  # 없는 줄을 새로 만들지 않는다

    def test_check_does_not_touch_text(self):
        text, changed, _, _ = mednafen_cfg.apply(CFG, {"ss.videoip": "0"}, verbose=True)
        self.assertEqual(changed, 1)
        self.assertEqual(text, CFG)

    def test_value_with_spaces(self):
        # 키 배치 값이 `keyboard 0x0 22` 처럼 공백을 낀다 — 줄 통째로 갈아야 한다.
        text, *_ = mednafen_cfg.apply("a.b keyboard 0x0 4\n", {"a.b": "keyboard 0x0 22"})
        self.assertEqual(text, "a.b keyboard 0x0 22\n")


class TestCanon(unittest.TestCase):
    def test_no_overlap(self):
        self.assertEqual(set(mednafen_keys.settings()) & set(mednafen_video.settings()), set())

    def test_no_crt_postprocessing(self):
        s = mednafen_video.settings()
        for mod in mednafen_video.MODULES:
            self.assertEqual(s[f"{mod}.scanlines"], "0")
            self.assertEqual(s[f"{mod}.shader"], "none")
            self.assertEqual(s[f"{mod}.special"], "none")
            self.assertEqual(s[f"{mod}.videoip"], "0")

    def test_aspect_is_corrected(self):
        # SFC 가 8:7 로 홀쭉했던 자리(2026-09-02). correct_aspect 가 있는 기종은 전부 1.
        s = mednafen_video.settings()
        for mod in ("psx", "ss", "snes", "md"):
            self.assertEqual(s[f"{mod}.correct_aspect"], "1")
            self.assertEqual(s[f"{mod}.stretch"], "aspect")
        for mod in ("psx", "ss", "pce"):
            self.assertEqual(s[f"{mod}.h_overscan"], "1")

    def test_module_filter(self):
        self.assertTrue(all(k.startswith("ss.") for k in mednafen_video.settings(["ss"])))


if __name__ == "__main__":
    unittest.main()
