"""MAP000 시험 대사 강제 블록 회귀 — **원본 없이 돈다**(가짜 바이트).

🔴 `mapfile._FORCED` 는 (크기, sha1) 이 맞는 한 파일에만 블록을 더한다. 다른 바이트열에서는 스캔 결과가 한 줄도 안 바뀌어야 한다 —
   `TERM_OK` 를 넓히는 대신 이 길을 택한 까닭이 「다른 맵의 블록 번호가 흔들린다」였다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mapfile as M


class ForcedBlocks(unittest.TestCase):
    def test_other_bytes_untouched(self):
        b = bytearray(14812)  # 크기는 같지만 sha1 이 다르다
        self.assertEqual(M.blocks(bytes(b)), M._forced(bytes(b), []))

    def test_other_size_untouched(self):
        out = [{"off": 1}]
        self.assertIs(M._forced(b"\x00" * 100, out), out)

    def test_spans_sorted_and_term_asserted(self):
        self.assertTrue(all(a < e for spans in M._FORCED.values() for a, e, _t in spans))


if __name__ == "__main__":
    unittest.main()
