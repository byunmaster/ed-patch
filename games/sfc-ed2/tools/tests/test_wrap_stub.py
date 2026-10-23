"""낱말 단위 줄바꿈 스텁(`patches.WRAP_STUB`)을 디스어셈블해 구조를 검산한다 — 손으로 짠 기계어는 이렇게 읽어 본다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import dis65816
import patches


class WrapStub(unittest.TestCase):
    def _lines(self):
        d = bytearray(b"\xff" * 0x10000)  # 스텁은 뱅크 $C0 안 — 파일 오프셋 = 뱅크 내 주소
        a = patches.WRAP_STUB & 0xFFFF
        d[a : a + len(patches._WRAP)] = patches._WRAP
        return dis65816.dis(bytes(d), a, a + len(patches._WRAP), True, False)

    def test_hook_and_exits(self):
        t = "\n".join(self._lines())
        self.assertIn("cmp #$20", t)
        self.assertIn("lda $1B13", t)
        self.assertIn("jsr $AEB6", t)  # 줄바꿈 호출
        self.assertEqual(t.count("jmp $A96C"), 2)  # 공백이 아니거나 그대로 찍는 두 길
        self.assertTrue(t.rstrip().endswith("rts"))

    def test_hook_site(self):
        for a, old, new in patches.PATCHES:
            if a == 0xC0A894:
                self.assertEqual(old, bytes([0x4C, 0x6C, 0xA9]))
                self.assertEqual(new, bytes([0x4C, patches.WRAP_STUB & 0xFF, (patches.WRAP_STUB >> 8) & 0xFF]))
                return
        self.fail("후킹 자리가 없다")


if __name__ == "__main__":
    unittest.main()
