"""이름 검사 어댑터 — 줄 사이로 이어진 문장을 한 줄로도 내는가(원본 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import names_corpus as nc


class JoinedTest(unittest.TestCase):
    def test_sentence_continued_over_lines_is_joined(self):
        out = [("1:2:3", "あいう、", "가나다,", "dialog"), ("1:2:4", "えおか。", "라마바.", "dialog"), ("1:2:5", "きくけ。", "사아자.", "dialog")]
        ex = nc._joined(out)
        self.assertEqual(ex, [("1:2:3+1:2:4", "あいう、えおか。", "가나다, 라마바.", "dialog")])

    def test_complete_sentences_are_not_joined(self):
        out = [("1:2:3", "あいう。", "가나다.", "dialog"), ("1:2:4", "えおか。", "라마바.", "dialog")]
        self.assertEqual(nc._joined(out), [])

    def test_other_chunk_or_gap_is_not_joined(self):
        out = [("1:2:3", "あいう、", "가나다,", "dialog"), ("1:9:4", "えおか。", "라마바.", "dialog"), ("1:9:6", "きくけ、", "사아자,", "dialog"), ("1:9:8", "さし。", "차카.", "dialog")]
        self.assertEqual(nc._joined(out), [])


if __name__ == "__main__":
    unittest.main()
