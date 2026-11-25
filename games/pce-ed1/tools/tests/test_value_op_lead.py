"""메시지 앞 수치 출력(`1D 22`)이 줄에 이미 찍은 폭(4자리 × 8px)을 조판이 알아야 한다 — 씬 192 「(금액) Gold를 건네시겠습니까?」 끝 「?」 잘림(11-07)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import messages as M
import translate as T
import typeset


class Msg:
    def __init__(self, key, start):
        self.key, self.start, self.end, self.terminated, self.speaker, self.common, self.tokens = key, start, start + 4, True, None, None, []


class ValueOpLead(unittest.TestCase):
    def test_lead_is_four_digits(self):
        block = bytes([0x05, 0x1D, 0x22, 0x41, 0x42, 0x43, 0x44, 0x06])
        leads = T.continuation_leads(block, [Msg("k", 3)], {}, {})
        self.assertEqual(leads["k"], typeset.px(typeset.NUMCH * 4))
        self.assertEqual(leads["k"], 32)

    def test_other_ops_no_lead(self):
        block = bytes([0x05, 0x1D, 0xA8, 0x41, 0x42, 0x43, 0x44, 0x06])
        self.assertNotIn("k", T.continuation_leads(block, [Msg("k", 3)], {}, {}))


if __name__ == "__main__":
    unittest.main()
