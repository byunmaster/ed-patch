"""check_residual_jp — 12자↑ 가나·한자 런은 잡고, 한글 코드·11자·알려진 자리는 안 잡는다(원본·빌드 없이 도는 합성 검사)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_residual_jp as c

KR = {0x8A41, 0x8A42}


def sj(t: str) -> bytes:
    return t.encode("cp932")


class ResidualJp(unittest.TestCase):
    def test_twelve_chars_are_caught(self):
        data = b"\x00" * 10 + sj("あいうえおかきくけこさし") + b"\x00"
        self.assertEqual(c.find_runs(data, KR), [(10, 12)])

    def test_eleven_chars_are_not(self):
        self.assertEqual(c.find_runs(sj("あいうえおかきくけこ") + sj("さ")[:0], KR, min_run=12), [])

    def test_hangul_code_breaks_the_run(self):
        data = sj("あいうえおか") + bytes.fromhex("8a41") + sj("きくけこさし")
        self.assertEqual(c.find_runs(data, KR), [])

    def test_unknown_run_is_flagged_known_is_not(self):
        known = c.KNOWN[0]
        self.assertEqual(c.unknown([(known[0], known[1], (known[2] - known[1]) // 2)]), [])
        self.assertEqual(c.unknown([("script:3", 0x100, 14)]), [("script:3", 0x100, 14)])

    def test_regression_old_state_is_caught(self):
        """번역을 되돌린 옛 상태(대본 블록에 원문 문장이 그대로) — 게이트가 실제로 잡는다."""
        block = b"\x1e" + sj("セリオス") + b"\x04" + sj("よくぞここまでたどりついたな") + b"\x00"
        runs = c.find_runs(block, KR)
        self.assertEqual(len(c.unknown([("script:7", o, n) for o, n in runs])), 1)

    def test_run_starting_before_a_known_range_is_flagged(self):
        """알려진 구간과 **겹치기만** 해서는 통과하지 않는다 — 구간 앞에 일본어가 붙으면 구간 밖이라 잡힌다(sfc-ed2 구멍 회귀)."""
        w, s, e, _ = c.KNOWN[0]
        n = (e - s) // 2
        self.assertEqual(c.unknown([(w, s - 2 * 3, n + 3)]), [(w, s - 2 * 3, n + 3)])
        self.assertEqual(c.unknown([(w, s, n + 3)]), [(w, s, n + 3)])

    def test_short_sentence_in_block_is_caught(self):
        block = b"\x00" + sj("メタルスチームが現れた") + b"\x00"
        self.assertEqual(c.find_runs(block, KR, c.MIN_RUN_BLOCK), [(1, 11)])


if __name__ == "__main__":
    unittest.main()
