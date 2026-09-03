"""UI 문안 정본의 계약 — 원본 없이 도는 회귀.

원본과의 대조(지문·길이)는 `uitext.py --check` 가 게이트에서 한다. 여기서는 파일의 모양과
**이 게임에서만 통하는 규약**을 박는다.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import textenc
import uitext

DISCS = ("ed3", "ed4")


class TestUiText(unittest.TestCase):
    def test_shape(self):
        for disc in DISCS:
            p = uitext.canon_path(disc)
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(doc["disc"], disc)
            for k, v in doc["strings"].items():
                self.assertTrue(k.startswith("0x"), k)
                self.assertEqual(len(v["jp"]), 8, f"{k}: 지문은 sha1 앞 8자")
                self.assertTrue(v["kr"].strip(), k)

    def test_only_codes_the_game_has(self):
        """🔴 부호는 **전각만** 있다 — `.`·`,` 는 코드표에 없다.

        없는 글자를 쓰면 빌드가 그 줄을 통째로 건너뛴다(조용히 사라지는 게 아니라 알리지만,
        애초에 안 쓰는 게 맞다). 한글은 자리를 받으므로 검사에서 뺀다.
        """
        for disc in DISCS:
            if not os.path.exists(uitext.canon_path(disc)):
                continue
            have = set(textenc.charmap(disc).values()) | set(textenc.CONTROL.values())
            bad = set()
            for row in uitext.load(disc).values():
                for ch in row["kr"]:
                    if "가" <= ch <= "힣" or ch == " ":
                        continue
                    if ch not in have:
                        bad.add(ch)
            self.assertFalse(bad, f"{disc}: 코드표에 없는 글자 {sorted(bad)}")

    def test_no_ascii_punctuation(self):
        """반각 마침표·쉼표는 이 게임에 없다 — 「。」를 쓴다."""
        for disc in DISCS:
            if not os.path.exists(uitext.canon_path(disc)):
                continue
            bad = [
                (hex(o), r["kr"])
                for o, r in uitext.load(disc).items()
                if any(c in r["kr"] for c in ".,!?")
            ]
            self.assertFalse(bad, f"{disc}: 반각 부호 {bad[:3]}")


if __name__ == "__main__":
    unittest.main()
