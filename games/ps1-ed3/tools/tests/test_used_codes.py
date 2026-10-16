"""글리프 자리 계산 — 옮겨진 UI 문자열의 일본어 코드는 풀려야 한다(10-12).

🔴 밟은 함정: `used_codes` 가 UI 정본이 옮긴 214행의 코드를 안 풀어 「자리가 87자 모자란다」고 나왔다
   (풀면 69 가 남는다). 원본 없이 도는 합성 입력으로 지킨다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hangul_map


class TestExeUsedCodes(unittest.TestCase):
    def test_translated_ui_string_releases_its_codes(self):
        strings = [(0x100, [0x300, 0x301]), (0x200, [0x302])]
        self.assertEqual(hangul_map.exe_used_codes(strings, {0x100}), {0x302})

    def test_code_shared_with_an_untranslated_string_stays_used(self):
        strings = [(0x100, [0x300, 0x301]), (0x200, [0x301, 0x302])]
        self.assertEqual(hangul_map.exe_used_codes(strings, {0x100}), {0x301, 0x302})

    def test_nothing_translated_keeps_everything(self):
        strings = [(0x100, [0x300]), (0x200, [0x301])]
        self.assertEqual(hangul_map.exe_used_codes(strings, set()), {0x300, 0x301})


if __name__ == "__main__":
    unittest.main()
