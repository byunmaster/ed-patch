"""제품 롬의 디버그 진입키 트램펄린 — 손인코딩 기계어 검산(원본 롬 없이 돈다)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import debugkey as d

# 명령 길이(오퍼코드 → 바이트 수) — 트램펄린이 쓰는 것만
LEN = {
    0xAD: 3,
    0x8D: 3,
    0x9C: 3,
    0xED: 3,
    0x29: 2,
    0xC9: 2,
    0x89: 2,
    0xA9: 2,
    0x38: 1,
    0x6B: 1,
    0x0D: 3,
    0x5C: 4,
    0xEE: 3,
    0x60: 1,
}
BRANCH = {0xD0, 0xF0, 0x90, 0xB0, 0x80}


def decode(b):
    i, ops = 0, []
    while i < len(b):
        n = 2 if b[i] in BRANCH else LEN[b[i]]
        ops.append((i, b[i], b[i + 1 : i + n]))
        i += n
    return ops


class Tramp(unittest.TestCase):
    def test_분기가_명령_경계에_떨어진다(self):
        for blob in (d.COUNT_BYTES, d.MENU_BYTES):
            ops = decode(blob)
            starts = {i for i, _, _ in ops}
            for i, op, arg in ops:
                if op in BRANCH:
                    rel = arg[0] - 256 if arg[0] > 127 else arg[0]
                    self.assertIn(i + 2 + rel, starts)

    def test_창_루프_자리는_JSR_스텁이_원래_명령을_대신한다(self):
        self.assertEqual(d.SITE_ORIG, bytes([0xAD, 0xFA, 0x05]))  # lda $05FA
        self.assertEqual(d.MENU_BYTES[-4:], bytes([0xAD, 0xFA, 0x05, 0x60]))  # 원래 명령 + rts
        self.assertEqual(d.SITE, 0x029B3F)

    def test_조이패드_자리는_원래_두_명령을_대신하고_rtl_로_끝난다(self):
        self.assertEqual(d.PAD_ORIG, bytes([0xAD, 0x19, 0x42, 0x8D, 0x18, 0x19]))  # lda $4219 / sta $1918
        self.assertEqual(d.COUNT_BYTES[:6], d.PAD_ORIG)
        self.assertEqual(d.COUNT_BYTES[-1], 0x6B)

    def test_메뉴_B_A_로_간다(self):
        jml = [(i, bytes(arg)) for i, op, arg in decode(d.MENU_BYTES) if op == 0x5C]
        targets = [a[0] | a[1] << 8 | a[2] << 16 for _, a in jml]
        self.assertEqual(targets, [d.MENU_B, d.MENU_A])

    def test_세는_시간은_NMI_프레임_60이다(self):
        self.assertEqual(d.FRAMES, 60)
        self.assertIn(bytes([0xC9, d.FRAMES]), d.COUNT_BYTES)
        self.assertIn(bytes([0xC9, d.FRAMES]), d.MENU_BYTES)

    def test_Select_와_L_R_정확히를_본다(self):
        t = d.COUNT_BYTES
        self.assertIn(bytes([0x29, 0x20]), t)  # Select
        self.assertIn(bytes([0x29, 0xBF, 0xC9, 0x30]), t)  # X 를 빼고 L+R
