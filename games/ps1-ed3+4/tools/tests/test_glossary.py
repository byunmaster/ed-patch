"""고유명사 정본의 **모양 계약** — 원본 없이 도는 회귀.

원본과의 대조는 `check_glossary.py` 가 게이트에서 한다. 여기서 보는 건 파일 자체의 계약이라
원본이 없는 트리(다른 워크트리·CI)에서도 돈다.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import glossary

DISCS = ("ed3", "ed4")


class TestGlossaryShape(unittest.TestCase):
    def test_files_exist_and_parse(self):
        for disc in DISCS:
            with open(glossary.path(disc), encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(doc["disc"], disc)
            self.assertTrue(doc["categories"])

    def test_kinds_are_known(self):
        for disc in DISCS:
            for kind in glossary.load(disc)["categories"]:
                self.assertIn(kind, glossary.KINDS, f"{disc}: 모르는 갈래 {kind}")

    def test_every_entry_is_translated(self):
        """빈 값을 남기지 않는다 — 빌드가 그 자리에 **원문을 그대로** 내보낸다."""
        for disc in DISCS:
            for kind, d in glossary.load(disc)["categories"].items():
                bad = [jp for jp, kr in d.items() if not kr or not kr.strip()]
                self.assertFalse(bad, f"{disc}/{kind}: 빈 표기 {bad[:5]}")

    def test_no_japanese_left_in_values(self):
        """우리 표기에 가나가 남아 있으면 옮기다 만 것이다."""
        for disc in DISCS:
            for kind, d in glossary.load(disc)["categories"].items():
                bad = [
                    f"{jp}→{kr}"
                    for jp, kr in d.items()
                    if any("぀" <= c <= "ヿ" and c != "・" for c in kr)
                ]
                self.assertFalse(bad, f"{disc}/{kind}: 가나가 남았다 {bad[:5]}")

    def test_no_duplicate_reading_within_kind(self):
        """🔴 한 갈래 안에서 두 원문이 같은 표기를 쓰면 **화면에서 구별이 안 된다.**

        ⚠ 갈래가 다르면 정상이다 — ED4 의 소환수는 몬스터이면서 마법 이름이다.
        """
        for disc in DISCS:
            for kind, d in glossary.load(disc)["categories"].items():
                seen = {}
                for jp, kr in d.items():
                    seen.setdefault(kr, []).append(jp)
                dup = {k: v for k, v in seen.items() if len(v) > 1}
                self.assertFalse(dup, f"{disc}/{kind}: 겹치는 표기 {list(dup.items())[:3]}")

    def test_evidence_points_at_real_entries(self):
        """근거는 정본에 있는 원문에만 붙는다 — 이름을 고치고 근거를 안 옮기면 여기서 운다."""
        for disc in DISCS:
            doc = glossary.load(disc)
            have = {jp for d in doc["categories"].values() for jp in d}
            stray = [jp for jp in doc.get("evidence", {}) if jp not in have]
            self.assertFalse(stray, f"{disc}: 갈 곳 없는 근거 {stray[:5]}")


if __name__ == "__main__":
    unittest.main()
