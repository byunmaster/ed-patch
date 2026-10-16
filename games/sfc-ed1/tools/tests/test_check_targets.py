"""check_targets 자신의 커버리지 — 본체 밖 목표를 넣으면 잡는다. 원본 롬 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_targets  # noqa: E402

LO, HI = 0x07A721, 0x0BFD04


class Targets(unittest.TestCase):
    def test_본체_안은_통과(self):
        self.assertEqual(check_targets.outside([0x07A721, 0x0A8000, 0x0BFD03], LO, HI), [])

    def test_본체_밖_목표를_잡는다(self):
        # 합성: 목록 밖(`$05` 뱅크 · `$1E` 뱅크 · 본체 끝 바로 뒤)을 하나씩 섞는다
        got = check_targets.outside([0x07A721, 0x05CDFF, 0x0A8000, 0x1ECA12, 0x0BFD04], LO, HI)
        self.assertEqual(got, [1, 3, 4])

    def test_반입한_본체_밖_구간은_안이다(self):
        extra = [(0x05CDAC, 0x05F26E)]
        self.assertEqual(check_targets.outside([0x05CDFF, 0x1ECA12], LO, HI, extra), [1])


if __name__ == "__main__":
    unittest.main()
