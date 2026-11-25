"""이어 쓰는 블록의 끝 줄바꿈(`chain_break`) — **정본 이름과 통째로 같은 블록(지명 등)은 문장이 아니다**(마을 안 HUD 지명 0x0A, 10-24).

배경: 지명 「クルスの村」 의 조사 `の`(히라가나)를 `_PROSE` 가 문장으로 읽어 끝에 `\\n`(0x0A)을 붙였고, 엔진이 그 블록을 HUD 이름 버퍼로 복사해 길이가 11 이 되어
이름이 왼쪽으로 쏠리고 끝에 쓰레기 글자가 찍혔다. 가짜 문장(원문·정발 인용 아님)과 이 레포의 정본 이름 두 개만 쓴다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "shared"))

import typeset_scn as T


class ChainBreakNames(unittest.TestCase):
    def test_place_name_block_gets_no_newline(self):
        for jp, kr in (("クルスの村", "크루즈마을"), ("ラルファの砦", "랄파요새")):
            self.assertEqual(T.chain_break(jp, kr), kr, jp)

    def test_sentence_block_still_gets_newline(self):
        # 문장 부호가 있는 이어 쓰는 문장은 예전처럼 끝에 개행(다음 블록이 같은 줄 꼬리에 붙지 않게)
        self.assertEqual(T.chain_break("ありがとう。", "고마워."), "고마워.\n")

    def test_name_block_with_original_newline_is_kept(self):
        # 원문이 개행으로 끝나는 블록은 첫 규칙(원문 개행 되살림)이 먼저다 — 이름이어도 원문에 개행이 있으면 그대로
        self.assertEqual(T.chain_break("クルスの村\n", "크루즈마을"), "크루즈마을\n")


if __name__ == "__main__":
    unittest.main()
