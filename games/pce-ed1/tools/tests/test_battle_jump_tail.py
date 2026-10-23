"""머리 + 점프 문구(「…の左の頭は」) — 원문 바이트로 단위가 잡히고, 번역을 쓰면 점프가 번역 한가운데로 안 떨어진다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle as B

A = B.LOAD_ADDR


def block() -> bytes:
    sj = lambda s: s.encode("cp932")  # noqa: E731
    head_len = 64 * 0  # 레코드 없는 합성 블록(records()==[] 이므로 시작 0)
    right = sj("の右の頭は") + b"\x01" + sj("インパスの呪文を唱えた。") + b"\x07"
    tail_at = 16
    pad = b"\x00" * tail_at
    left_at = tail_at + len(right) + 4
    # 왼쪽: 「の左」 + 0F → 오른쪽 문구의 「の頭は」(4바이트 뒤)
    left = sj("の左") + bytes([0x0F, (A + tail_at + 4) & 0xFF, (A + tail_at + 4) >> 8])
    return head_len and b"" or pad + right + b"\x00\x00\x00\x00" + left + b"\xff\xff\xff\xff\xff"


class JumpTail(unittest.TestCase):
    def test_머리_점프_문구를_한_문장으로_편_단위로_잡는다(self):
        d = block()
        base = B._msg_units(d)
        jt = B.jump_tail_units(d, base)
        self.assertEqual(len(jt), 1)
        self.assertEqual(B.render(jt[0]["body"]), "の左の頭は{01}インパスの呪文を唱えた。")
        self.assertIsNotNone(jt[0]["back"])


if __name__ == "__main__":
    unittest.main()
