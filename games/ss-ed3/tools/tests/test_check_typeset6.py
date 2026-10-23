"""조판 여섯 규칙 ① — 음성 자막은 접지 않는다(스텁이 18칸 버퍼에 직접 그림). 대사창은 그대로 접는다 (원본 없이 돈다)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_typeset6 as K

# 글자 17.5 + 마침표 0.5 = 정확히 18.0칸 (실측 10-21: 잘리지 않고 그려진다)
FULL = "여행하다 굶으면 길에서 쓰러진다고요."


class Fold(unittest.TestCase):
    def test_voice_line_of_18_cols_passes(self):
        self.assertEqual(K.check(FULL, 18, fold=False), [])

    def test_voice_line_over_18_cols_fails(self):
        self.assertEqual(K.check(FULL + "가", 18, fold=False), ["①"])  # 18.5칸

    def test_dialog_window_still_folds(self):
        # 같은 줄을 대사창(17칸)에서 보면 부호가 접힌다 — 대사창 규칙은 그대로다
        self.assertEqual(K.check(FULL, 17, fold=True), ["①"])

    def test_findings_uses_no_fold_for_voice_only(self):
        src = open(K.__file__, encoding="utf8").read()
        self.assertIn('fold=area != "음성 자막"', src)


if __name__ == "__main__":
    unittest.main()
