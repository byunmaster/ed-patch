"""카나 블록 — 상수(`textenc.DROPPED`)를 **닻으로 다시 유도**해 검산한다.

2026-09-03: 가타카나 탈락을 눈대중으로 「히라가나와 같겠지」로 채웠다가 주인공 이름이
「ジヤラオ」로 읽혔다. 빌드도 검사도 다 통과하고 **화면에서만** 드러나는 종류다.
그래서 값을 코드로 다시 계산해 본다(체크리스트 10 「박아 둔 상수를 그 코드로 검산」).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import textenc

# 실측 닻 — (코드, 글자). 골격 대조에서 확신이 높았던 것들과 이름 둘.
ANCHORS = {
    # ⚠ **읽어서 확인한 것만 닻이다.** 유도한 값을 닻으로 쓰면 검산이 자기 자신을 검산한다.
    "ed3": [
        # 히라가나 — 문장으로 확인(「なんで」「いうわけだ」「ごちそうを」「ジュリオの父」)
        (0x6C, "の"),
        (0x8C, "わ"),
        (0x8D, "を"),
        (0x8E, "ん"),
        # 가타카나 — 이름 둘에서(ジュリオ · クリス), 빈도 1·2위 이름이라 오정렬이 없다
        (0x98, "オ"),
        (0x9D, "ク"),
        (0xA6, "ジ"),
        (0xA7, "ス"),
        (0xD2, "ュ"),
        (0xD7, "リ"),
    ],
}
# 이름은 표가 통째로 맞아야 나온다 — 한 칸만 밀려도 깨진다.
NAMES = {"ed3": [([0xA6, 0xD2, 0xD7, 0x98], "ジュリオ"), ([0x9D, 0xD7, 0xA7], "クリス")]}


class TestKanaBlock(unittest.TestCase):
    def test_anchors(self):
        for disc, anchors in ANCHORS.items():
            m = textenc.kana_map(disc)
            for code, ch in anchors:
                self.assertEqual(m.get(code), ch, f"{disc} 0x{code:03X}")

    def test_dropped_is_derivable(self):
        """탈락 집합을 닻에서 **유도**했을 때 선언한 값과 같은가."""
        for disc, anchors in ANCHORS.items():
            full = textenc.JIS_HIRA + textenc.JIS_KATA
            declared = textenc.DROPPED[disc]["hira"] + textenc.DROPPED[disc]["kata"]
            kept = [c for c in full if c not in declared]
            for code, ch in anchors:
                self.assertEqual(
                    kept.index(ch) + textenc.KANA_BASE,
                    code,
                    f"{disc}: {ch} 의 자리가 안 맞는다 — 탈락 집합이 틀렸다",
                )

    def test_names_decode(self):
        for disc, cases in NAMES.items():
            for codes, want in cases:
                m = textenc.kana_map(disc)
                self.assertEqual("".join(m[c] for c in codes), want)

    def test_block_is_contiguous(self):
        """카나는 히라가나 → 가타카나로 **끊김 없이** 이어진다(JIS 4구 → 5구)."""
        for disc in textenc.DROPPED:
            m = textenc.kana_map(disc)
            codes = sorted(m)
            self.assertEqual(codes[0], textenc.KANA_BASE)
            self.assertEqual(codes, list(range(codes[0], codes[0] + len(codes))))


class TestKanaTail(unittest.TestCase):
    """🔴 **닻이 없는 꼬리**(ン 뒤)는 닻으로 못 잡는다.

    ED3 의 탈락 집합에 `ヴ` 가 빠져 있었는데, ヴ 는 ン 뒤라 위 닻이 **하나도 안 걸린다.**
    그래서 위 검사가 전부 통과한 채로 0xDD~0xDF 가 한 칸씩 밀려 **哀 가 「ヶ」로 읽혔다**
    (「可哀相」 → 「可ヶ相」, 2026-09-03). 잡아 준 건 **활자**다 — ED3·ED4 의 글리프가
    1,595자 비트까지 같아서 두 표를 겹쳐 보면 어긋난 자리가 드러난다
    (`solve_charmap_glyph.py`). 그 결과를 여기 박는다.
    """

    # 활자 로제타로 확정한 꼬리 (원본 없이 도는 회귀라 값으로 박는다)
    TAILS = {
        "ed3": {0xDB: "ワ", 0xDC: "ン", 0xDD: "ヵ", 0xDE: "ヶ"},
        "ed4": {0xDA: "ワ", 0xDB: "ヲ", 0xDC: "ン", 0xDD: "ヴ", 0xDE: "ヵ", 0xDF: "ヶ"},
    }

    def test_tails(self):
        for disc, want in self.TAILS.items():
            m = textenc.kana_map(disc)
            for code, ch in want.items():
                self.assertEqual(m.get(code), ch, f"{disc} 0x{code:03X}")

    def test_kana_ends_where_kanji_begins(self):
        """카나 마지막 코드 바로 다음이 첫 한자 `哀` 다 — 한 칸이라도 밀리면 여기가 운다."""
        for disc, first in (("ed3", 0xDF), ("ed4", 0xE0)):
            m = textenc.kana_map(disc)
            self.assertEqual(max(m), first - 1, f"{disc}: 카나가 끝나는 자리")
            self.assertEqual(textenc.charmap(disc).get(first), "哀", f"{disc}: 첫 한자")

    def test_discs_differ(self):
        """두 디스크의 탈락 집합은 **다르다** — 같다고 두면 ED4 가 통째로 밀린다."""
        self.assertNotEqual(textenc.DROPPED["ed3"], textenc.DROPPED["ed4"])


if __name__ == "__main__":
    unittest.main()
