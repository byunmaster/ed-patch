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

    def test_scene_untranslated_outside_known_fragments_fails(self):
        """마스터 10-11: 씬 미번역 일본어는 정적 근거 목록(깨진 조각)에 있어야 경고로 통과 — 목록 밖은 실패."""
        self.assertEqual(run([("scn010:ab", "戻る", None, "dialog")]), 1)

    def test_scene_without_text_is_fine(self):
        self.assertEqual(run([("scn010:ab", "\n", None, "dialog")]), 0)


if __name__ == "__main__":
    unittest.main()
