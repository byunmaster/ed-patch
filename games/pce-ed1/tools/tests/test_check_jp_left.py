"""화면 일본어 게이트 — 깨진 조각 목록(정적 근거)만 경고, 목록 밖 미번역 일본어는 실패."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_jp_left as C


class JpLeft(unittest.TestCase):
    def _run(self, rows, known):
        C.names_corpus.pairs = lambda: rows
        C.known_fragments = lambda: known
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = C.main()
        return rc, buf.getvalue()

    def test_목록에_있는_깨진_조각은_경고만(self):
        rc, out = self._run([("scn001:aa", "ぉ鴻ｧｩ", None)], {"scn001:aa": "6502 기계어 영역"})
        self.assertEqual(rc, 0)
        self.assertIn("깨진 조각 경고 1줄", out)

    def test_목록_밖_미번역_일본어는_실패(self):
        rc, out = self._run([("scn002:bb", "おはようございます。", None)], {})
        self.assertEqual(rc, 1)
        self.assertIn("scn002:bb", out)

    def test_글_없는_메시지는_센_줄에만(self):
        rc, out = self._run([("scn002:cc", "\n", None), ("scn002:dd", "", None)], {})
        self.assertEqual(rc, 0)
        self.assertIn("글 없는 메시지 2줄", out)

    def test_번역된_씬_줄은_안_본다(self):
        rc, _ = self._run([("scn002:ee", "おはよう", "안녕")], {})
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
