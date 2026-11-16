"""비모달 자막 쪽 자료 블롭 — 풀 중복 제거 왕복이 `gwin.make_window` 결과와 같다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gwin
import gwin_blob

PAGES = [
    {"speaker": "라이아스", "text": "안녕히 주무셨사옵니까,\n세리오스님.", "start": 0.0, "end": 2.5},
    {"speaker": "세리오스", "text": "잘 잤어, 할아범.", "start": 2.5, "end": 4.0},
    {"speaker": None, "text": "이제는\n달아날 수도 없사옵니다!!", "start": 4.0, "end": 6.0},
]


class TestBlob(unittest.TestCase):
    def test_roundtrip(self):
        blob = gwin_blob.pack(PAGES, lambda s: round(s * 60))
        out = gwin_blob.unpack(blob)
        self.assertEqual(len(out), len(PAGES))
        for pg, o in zip(PAGES, out, strict=True):
            tiles, bat = gwin.make_window(pg["speaker"], pg["text"])
            self.assertEqual(o["tiles"], tiles)
            text_bat = {k: v for k, v in bat.items() if (v & 0xFFF) >= gwin.TILE0}
            self.assertEqual(o["bat"], text_bat)
            self.assertEqual((o["start"], o["end"]), (round(pg["start"] * 60), round(pg["end"] * 60)))

    def test_dedup_smaller_than_raw(self):
        blob = gwin_blob.pack(PAGES + PAGES, lambda s: round(s * 60))  # 같은 쪽이 둘이면 풀은 한 벌
        raw = sum(len(gwin.make_window(p["speaker"], p["text"])[0]) for p in PAGES + PAGES)
        self.assertLess(len(blob), raw)


if __name__ == "__main__":
    unittest.main()
