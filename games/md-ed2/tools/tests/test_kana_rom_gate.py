"""롬 전체 잔존 게이트(`kana_gate.scan_rom`/`check_rom`) — 합성 롬이 아니라 런 탐지기만 본다(원본 불필요)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kana_gate


class RomRuns(unittest.TestCase):
    def test_kana_run_needs_four_chars(self):
        jp = "ひらがな".encode("cp932")  # 가나 4자
        short = "ひら".encode("cp932")
        pairs: set[bytes] = set()
        got = [h for h, _r, _a in kana_gate._runs("raw", b"\x00" + jp + b"\x00", pairs)]
        self.assertEqual(len(got), 1)
        self.assertEqual(
            [h for h, _r, _a in kana_gate._runs("raw", b"\x00" + short + b"\x00", pairs)], []
        )

    def test_halfwidth_only_in_text_areas(self):
        hw = bytes([0xB1, 0xB2, 0xB3, 0xB4, 0xB5])
        self.assertEqual([h for h, _r, _a in kana_gate._runs("raw", hw, set())], [])
        self.assertEqual(len([h for h, _r, _a in kana_gate._runs("battle", hw, set())]), 1)

    def test_kanji_run_skips_hangul_pairs(self):
        kanji = "炎騎士魔界僧雷娘毒".encode("cp932")  # 8자
        self.assertEqual(len(list(kana_gate._jp_runs(kanji, set()))), 1)
        pairs = {
            kanji[i : i + 2] for i in range(0, len(kanji), 2)
        }  # 한글 코드로 등록된 쌍은 한자가 아니다
        self.assertEqual(list(kana_gate._jp_runs(kanji, pairs)), [])

    def test_short_sentence_with_kanji_in_text_area(self):
        """가나가 한자 사이에 끊겨도(가나 연속 3자↓) 섞인 런 4자↑이면 잡는다 — 「…が現れた」 구멍."""
        s = b"\x00" + "鬼が現れた".encode("cp932") + b"\x00"  # 가나 3(が·れ·た) + 한자 2, 연속 가나는 2
        self.assertEqual(len([h for h, _r, _a in kana_gate._runs("battle", s, set())]), 1)
        self.assertEqual(len([h for h, _r, _a in kana_gate._runs("raw", s, set())]), 0)  # 코드 영역은 가나 연속만
        short = b"\x00" + "鬼が現".encode("cp932") + b"\x00"  # 3자 — 우연 오탐 방지로 안 잡는다
        self.assertEqual(list(kana_gate._runs("battle", short, set())), [])

    def test_known_text_prefix_does_not_hide_japanese(self):
        """알려진(번역된) 한글 앞에 일본어가 붙어도 겹침으로 통과하지 않는다 — 런은 우리 코드 쌍을 뺀 나머지 조각만 본다."""
        ko = "스".encode("cp932", "replace")
        pairs = {b"\x91\x91"}
        s = b"\x91\x91\x91\x91" + "メタルが現れた".encode("cp932") + b"\x91\x91"
        got = list(kana_gate._runs("battle", s, pairs))
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0][1].startswith("メタル".encode("cp932")))
        self.assertTrue(ko)


if __name__ == "__main__":
    unittest.main()
