"""디코드 통로 — 모르는 코드를 **조용히 지우지 않는다**(체크리스트 4-C)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import textenc


class TestDecode(unittest.TestCase):
    def test_control_and_term(self):
        # 🔴 0x01 은 **쉼표(、)**다 — 줄바꿈이 아니다(2026-09-07, 글리프 #1 을 그려 확인).
        #    이 테스트가 `\n` 을 기대하고 있어서 옛 오해가 굳어 있었다.
        s = textenc.decode([0x42, 0x01, 0x42, textenc.TERM, 0x42], "ed3")
        self.assertEqual(s, "い、い")

    def test_unknown_is_kept_visible(self):
        s = textenc.decode([0x42, 0x7FF], "ed3")
        self.assertIn("7ff", s)
        self.assertTrue(s.startswith("い"))

    def test_charmap_is_jis_ordered(self):
        """표의 구조 계약 — 코드가 커지면 JIS 코드도 커진다. 어기면 배정이 틀린 것이다."""
        m = textenc.charmap("ed3")
        kana = set(textenc.kana_map("ed3"))
        prev_code = prev_jis = None
        bad = []
        for code in sorted(m):
            if code in kana or code < 0x3F:
                continue
            try:
                j = int.from_bytes(m[code].encode("cp932"), "big")
            except UnicodeEncodeError:
                continue
            if prev_jis is not None and j < prev_jis:
                bad.append((prev_code, m[prev_code], code, m[code]))
            prev_code, prev_jis = code, j
        self.assertEqual(bad, [], f"JIS 순서 역전 {len(bad)}건")


if __name__ == "__main__":
    unittest.main()
