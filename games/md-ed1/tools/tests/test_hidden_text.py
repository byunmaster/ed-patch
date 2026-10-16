"""check_hidden_text — 구운 롬의 한글 코드는 걸러내고 일본어 런은 잡는다(원본 없이 도는 합성 검사)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_hidden_text as c

KR = {0x8A41, 0x8A42, 0x8A43, 0x8A44}


def sj(t: str) -> bytes:
    return t.encode("cp932")


class HiddenText(unittest.TestCase):
    def test_hangul_codes_are_not_japanese(self):
        data = b"\x00" + bytes.fromhex("8a418a428a438a44") + b"\x00"
        self.assertEqual(c._find_hidden(data, [], [], KR), [])

    def test_japanese_left_behind_is_caught(self):
        data = b"\x00" + sj("残りポイント") + b"\x00"
        self.assertEqual(len(c._find_hidden(data, [], [], KR)), 1)

    def test_mixed_run_is_caught(self):
        data = b"\x00" + bytes.fromhex("8a418a42") + sj("残り") + b"\x00"
        self.assertEqual(len(c._find_hidden(data, [], [], KR)), 1)

    def test_covered_and_known_are_skipped(self):
        data = sj("残りポイント")
        self.assertEqual(c._find_hidden(data, [(0, len(data))], [], KR), [])
        self.assertEqual(c._find_hidden(data, [], [(0, len(data))], KR), [])

    def test_overlap_only_is_still_hidden(self):
        """목록과 **겹치기만** 해서는 통과하지 않는다 — 스트림 앞쪽에 붙은 문장(이름 박힌 문장)도 걸린다(sfc 구멍 회귀)."""
        data = sj("ようこそおいでくださいました") + b"\x00"
        self.assertEqual(len(c._find_hidden(data, [(10, 20)], [], KR)), 1)


if __name__ == "__main__":
    unittest.main()
