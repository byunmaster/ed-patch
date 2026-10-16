"""음성 편집기 자료 — 시각 모델이 닫힌다(쪽 마감 = 타이머를 바이트 비율로 나눈 값, 마지막 쪽 끝 = 시작 지연 + 타이머)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voice_editor_data as D


class T(unittest.TestCase):
    def test_pages_weights_sum(self):
        txt, w = D.pages_of("가나다라마바 사아자차카타 갑을병정\f기억니은", "")
        self.assertEqual(len(txt), len(w))
        self.assertTrue(all(x > 0 for x in w))

    def test_untranslated_uses_jp_pages(self):
        txt, w = D.pages_of(None, "あいう\nえお\fかきく")
        self.assertEqual(len(txt), 2)
        self.assertEqual(w[0], 2 * 5 + 1 + 1)


if __name__ == "__main__":
    unittest.main()
