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
    0x5C: 4,
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
        ops = decode(d.TRAMP_BYTES)
        starts = {i for i, _, _ in ops}
        for i, op, arg in ops:
            if op in BRANCH:
                rel = arg[0] - 256 if arg[0] > 127 else arg[0]
                self.assertIn(i + 2 + rel, starts)

    def test_다섯_바이트_자리를_JML_로_빼고_원래_명령을_대신한다(self):
        self.assertEqual(d.SITE_ORIG, bytes([0xAD, 0x45, 0x11, 0x89, 0x2F]))  # lda $1145 / bit #$2F
        t = d.TRAMP_BYTES
        self.assertEqual(t[-9:-4], d.SITE_ORIG)  # 원래 명령을 대신 실행한 뒤
        self.assertEqual(t[-4:], bytes([0x5C, 0x2C, 0x88, 0x00]))  # $00:882C 로 돌아간다
        self.assertEqual(d.BACK, 0x00882C)

    def test_메뉴_B_A_로_간다(self):
        t = d.TRAMP_BYTES
        jml = [(i, bytes(arg)) for i, op, arg in decode(t) if op == 0x5C]
        targets = [a[0] | a[1] << 8 | a[2] << 16 for _, a in jml]
        self.assertEqual(targets, [d.MENU_B, d.MENU_A, d.BACK])

    def test_세는_시간은_프레임_카운터이고_60프레임이다(self):
        self.assertEqual((d.FRAME_CTR, d.FRAMES), (0x05EF, 60))
        self.assertIn(bytes([0xC9, d.FRAMES]), d.TRAMP_BYTES)

    def test_트램펄린이_뱅크_끝의_빈_자리에_든다(self):
        self.assertLessEqual((d.TRAMP & 0xFFFF) + len(d.TRAMP_BYTES), 0x10000)


if __name__ == "__main__":
    unittest.main()
