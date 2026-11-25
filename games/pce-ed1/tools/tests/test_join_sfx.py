"""동료 합류 효과음(`0C 26`) 패치 — 합성 블록으로 돈다(원본 없이)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import messages as M
import translate as T


def fake_block(after: bytes) -> bytes:
    """`1F 이름 04 …` 합류 문장 하나 + 뒤 바이트. 문장 열쇠는 호출하는 쪽이 JOIN_SFX_KEYS 에 맞춘다."""
    return b"\x1f\x83\x51\x04" + "が仲間に加わりました。".encode("cp932") + after


class JoinSfx(unittest.TestCase):
    def test_adds_sfx_before_flag_set(self):
        blk = fake_block(b"\x14\x9c\x00\x13\x00\x04\x00")
        msgs = M.parse(blk)
        old = T.JOIN_SFX_KEYS
        try:
            T.JOIN_SFX_KEYS = {m.key for m in msgs}
            p = T.join_sfx_patches(blk)
        finally:
            T.JOIN_SFX_KEYS = old
        self.assertEqual(len(p), 1)
        off, o, n = p[0]
        self.assertEqual(blk[off : off + 3], o)
        self.assertEqual(n, b"\x0c\x26" + o)

    def test_skips_when_already_has_sfx(self):
        blk = fake_block(b"\x0c\x26\x04\x00")
        msgs = M.parse(blk)
        old = T.JOIN_SFX_KEYS
        try:
            T.JOIN_SFX_KEYS = {m.key for m in msgs}
            self.assertEqual(T.join_sfx_patches(blk), [])
        finally:
            T.JOIN_SFX_KEYS = old


if __name__ == "__main__":
    unittest.main()
