"""게임이 전투 중 런타임에 쓰는 뱅크 0x68 영 칸(호출 스택 저장 버퍼 + 포인터)은 글리프 풀·코드 자리에서 빠져 있어야 하고 `Prog.put` 이 덮는 쓰기를 거절해야 한다
(10-24 「ＥＰ」 의 Ｅ 깨짐 — 512B 링 코드 끝 바이트가 포인터 자리에 앉아 포인터가 0x60 에서 시작, 풀 글리프 745 가 +0x14C3 이었다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout
import lzring


def overlap(a_off, a_len, b_off, b_len):
    return a_off < b_off + b_len and b_off < a_off + a_len


class ZeroPaddingBattleScratch(unittest.TestCase):
    def test_pool_avoids_scratch(self):
        for bank, off, ln in layout.ZERO_PADDING:
            for sb, so, sn, _lab in layout.GAME_SCRATCH:
                if bank == sb:
                    self.assertFalse(overlap(off, ln, so, sn), f"풀 칸 {off:#x}+{ln} 이 스택 저장 자리 {so:#x}+{sn} 과 겹친다")

    def test_fetch_code_avoids_scratch(self):
        n = len(lzring.fetch_code())
        for sb, so, sn, _lab in layout.GAME_SCRATCH:
            if lzring.FETCH_BANK == sb:
                self.assertFalse(overlap(lzring.FETCH_END - n, n, so, sn), "512B 링 복호 코드가 스택 저장 자리를 덮는다")

    def test_put_rejects_scratch(self):
        orig = bytearray(b"\xff" * (layout.NBANKS * layout.BANK))
        for b, o, n in layout.ZERO_PADDING:
            z = (b - layout.BANK0) * layout.BANK + o
            orig[z : z + n] = bytes(n)
        p = layout.Prog(orig=bytes(orig))
        with self.assertRaises(ValueError):
            p.put(0x68, 0x1470, b"\x00", "시험")
        with self.assertRaises(ValueError):
            p.put(0x68, 0x1563, b"\x60", "시험")


if __name__ == "__main__":
    unittest.main()
