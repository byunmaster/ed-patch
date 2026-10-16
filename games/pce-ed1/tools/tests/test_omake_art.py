"""오마케 제목·간판 도안(`omake_art.py`) — 정본 텍스트의 꼴(원본 없이 도는 부분)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import omake_art as A


class OmakeArt(unittest.TestCase):
    def test_title_and_sign_texts_have_canvas_size(self):
        t = A.read_art(A.TITLE_TXT, 184, 80)
        s = A.read_art(A.SIGN_TXT, 34, 27)
        self.assertTrue(any("#" in r for r in t) and any("#" in r for r in s))

    def test_sign_text_is_v5_thickened_not_reshaped(self):
        # 굵게 한 안(v6-A)은 v5 모양에 오른쪽 1px 만 더한 것 — 줄마다 # 수가 줄지 않는다
        s = A.read_art(A.SIGN_TXT, 34, 27)
        self.assertGreater(sum(r.count("#") for r in s), 181)


if __name__ == "__main__":
    unittest.main()
