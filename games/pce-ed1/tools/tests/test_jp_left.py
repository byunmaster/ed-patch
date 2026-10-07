"""화면 일본어 검사(`check_jp_left`) 자신의 커버리지 — 일부러 일본어를 넣으면 잡아야 한다(F7)."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_jp_left


def run(items):
    with mock.patch.object(check_jp_left.names_corpus, "pairs", return_value=items):
        with mock.patch("builtins.print"):
            return check_jp_left.main()


class JpLeft(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(
            run([("label:1", "戻る", "돌아가기", "slot"), ("label:2", "ＯＮ", None, "slot")]), 0
        )

    def test_ours_has_kana(self):
        self.assertEqual(run([("label:1", "戻る", "돌아가る", "slot")]), 1)

    def test_untranslated_kanji(self):
        self.assertEqual(run([("sysmsg:1", "戻る", None, "slot")]), 1)

    def test_scene_not_counted(self):
        self.assertEqual(run([("scn010:ab", "戻る", None, "dialog")]), 0)


if __name__ == "__main__":
    unittest.main()
